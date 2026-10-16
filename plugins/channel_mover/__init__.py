# =============================================================================
# AWBotNest V2 插件：频道全量搬运（channel_mover）
#
# 把源频道/群组的历史消息，从最早一条开始匀速搬到目标群。
# 支持文字、图片、视频、文件、贴纸、语音、相册（media group）。
# 断点续传、进度查询、随时停止。
#
# 用法（在自己账号的任意会话里发命令，命令需为自己发出）：
#   /chcopy <源> <目标>          开始搬运（自动从最早开始）
#   /chcopy status               查看进度
#   /chcopy stop                 停止当前任务
#   /chcopy resume               从断点继续
#   /chcopy reset                清除进度重新开始
#
# 源/目标可写 @username、t.me/username、t.me/c/xxx、-100xxxxxxxxxx。
#
# 框架：AWBotNest V2 用 kurigram（import 名为 pyrogram）。
# 搬运用 pyrogram 的 copy_message / copy_media_group（服务端复制，
# 不需要下载再上传，省磁盘也不损伤画质）。
# =============================================================================

import asyncio

from ._core import (
    apply_filters,
    build_progress_text,
    compile_filters,
    group_albums,
    is_finished,
    is_service_message,
    next_id_after,
    resolve_peer,
    trailing_open_album,
)

__plugin__ = {
    "name": "频道全量搬运",
    "id": "channel_mover",
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "把源频道/群的历史消息从最早开始匀速搬到目标群，支持媒体与相册、断点续传、进度查询。",
    "tags": ["搬运", "频道", "历史", "同步"],
    "scope": "user",
    "plugin_api_version": 2,
    "resources": {
        "timeout_seconds": 3600,
        "max_concurrency": 1,
        "max_background_tasks": 4,
        "failure_threshold": 10,
        "recovery_seconds": 30,
    },
    "config_schema": {
        # ── 速率控制 ──
        "send_interval": {
            "type": "slider", "default": 1.0, "label": "每条间隔(秒)",
            "min": 0.2, "max": 30, "step": 0.1, "section": "速率控制", "order": 1,
            "help": "匀速搬运的节奏。Telegram 用户账号建议不低于 1 秒，过快会触发 FloodWait。",
        },
        "batch_size": {
            "type": "number", "default": 50, "label": "每批拉取条数",
            "min": 10, "max": 100, "section": "速率控制", "order": 2,
            "help": "每次向 Telegram 拉取多少条历史。pyrogram 单次上限 100。",
        },
        "flood_wait_max": {
            "type": "number", "default": 300, "label": "FloodWait 最长等待(秒)",
            "min": 10, "max": 3600, "section": "速率控制", "order": 3,
            "help": "触发限流时的等待上限，超过则暂停任务，发 resume 继续。",
        },
        # ── 内容选择 ──
        "copy_media": {
            "type": "boolean", "default": True, "label": "搬运媒体（图片/视频/文件/语音/贴纸）",
            "section": "内容选择", "order": 10,
            "help": "关闭则只搬文字消息，媒体跳过并计数。",
        },
        "keep_albums": {
            "type": "boolean", "default": True, "label": "保持相册分组",
            "section": "内容选择", "order": 11,
            "help": "开=同一相册作为一组发送；关=相册拆成单条。",
        },
        "send_mode": {
            "type": "select", "default": "copy", "label": "发送方式",
            "options": [
                {"value": "copy", "label": "复制（不带转发来源，最干净）"},
                {"value": "forward", "label": "原生转发（带「转发自」标注）"},
            ],
            "section": "内容选择", "order": 12,
            "help": "复制模式不显示来源；原生转发会显示「转发自 源频道」。",
        },
        "keep_replies": {
            "type": "boolean", "default": True, "label": "保留回复关系",
            "section": "内容选择", "order": 13,
            "help": "源消息是回复某条的，在目标群也回复对应消息（需该条已搬运）。",
        },
        # ── 过滤规则 ──
        "drop_regex": {
            "type": "text", "default": "", "label": "丢弃正则（命中则跳过）",
            "section": "过滤规则", "order": 20,
            "help": "每行一条 Python 正则。命中文字或文件名就跳过该消息。留空不过滤。",
        },
        "replace_regex": {
            "type": "text", "default": "", "label": "替换正则",
            "section": "过滤规则", "order": 21,
            "help": "格式：原正则|替换内容，每行一条。例：广告|***",
        },
        "skip_service": {
            "type": "boolean", "default": True, "label": "跳过入群/退群等系统消息",
            "section": "过滤规则", "order": 22,
        },
        # ── 命令 ──
        "command": {
            "type": "string", "default": "/chcopy", "label": "触发命令",
            "section": "命令", "order": 30, "help": "自己发出、以此开头的消息会触发。/chcopy 与 .chcopy 等价。",
        },
    },
}

# ── 插件级共享状态（单账号单实例）───────────────────────────────────────
_TASKS = {}        # task_id -> asyncio.Task
_STOP_FLAGS = {}   # task_id -> bool


def _bare(cmd: str) -> str:
    return (cmd or "").lstrip("/.").strip().lower() or "chcopy"


async def setup(ctx):
    @ctx.on_message(incoming=False, outgoing=True)
    async def handler(event):
        cfg = ctx.config
        bare = _bare(cfg.get("command", "/chcopy"))
        text = (event.text or "").strip()
        if not text:
            return

        head = text.split(maxsplit=1)[0].lower()
        if head not in (f"/{bare}", f".{bare}"):
            return

        parts = text.split()
        sub = (parts[1].lower() if len(parts) >= 2 else "status")
        client = event.client
        task_id = str(event.sender_id or event.chat_id)
        key = f"task_{task_id}"

        # ── status ──
        if sub == "status":
            st = await ctx.storage.get(key, None)
            return await event.reply(f"📦 频道搬运\n{build_progress_text(st)}")

        # ── stop ──
        if sub == "stop":
            _STOP_FLAGS[task_id] = True
            task = _TASKS.get(task_id)
            if task and not task.done():
                task.cancel()
            return await event.reply("⏹ 已请求停止，进度已保存，发 resume 可续传。")

        # ── resume ──
        if sub in ("resume", "continue"):
            st = await ctx.storage.get(key, None)
            if not st:
                return await event.reply("没有可续传的任务")
            st.pop("paused_reason", None)
            await ctx.storage.set(key, st)
            _STOP_FLAGS[task_id] = False
            task = ctx.create_task(
                _run_copy(ctx, task_id, client, st["src"], st["dst"], st, cfg),
                name=f"channel_mover-{task_id}",
            )
            _TASKS[task_id] = task
            return await event.reply(f"▶ 已从断点继续\n{build_progress_text(st)}")

        # ── reset ──
        if sub == "reset":
            _STOP_FLAGS[task_id] = True
            task = _TASKS.get(task_id)
            if task and not task.done():
                task.cancel()
            await ctx.storage.set(key, None)
            return await event.reply("🗑 进度已清除，下次 /chcopy 从头开始。")

        # ── 新任务 ──
        if len(parts) < 3:
            cmd = cfg.get("command", "/chcopy")
            return await event.reply(
                "用法：\n"
                f"  {cmd} <源> <目标>   开始搬运\n"
                f"  {cmd} status        看进度\n"
                f"  {cmd} stop          停止\n"
                f"  {cmd} resume        断点续传\n"
                f"  {cmd} reset         清除进度\n\n"
                "源/目标支持 @username、t.me/xxx、t.me/c/xxx、-100xxxxxxxxxx"
            )

        if task_id in _TASKS and not _TASKS[task_id].done():
            return await event.reply("已有任务在跑，先 stop 或看 status。")

        src = resolve_peer(parts[1])
        dst = resolve_peer(parts[2])
        if not src or not dst:
            return await event.reply("源或目标解析失败，检查一下格式。")

        # 先确认两个会话都可达，避免起了任务才失败
        try:
            src_name, dst_name = await _peer_names(client, src, dst)
        except Exception as exc:  # noqa: BLE001
            return await event.reply(f"找不到频道/群：{exc!r}\n确认账号已加入且参数正确。")

        state = {
            "src": src, "dst": dst,
            "src_name": src_name, "dst_name": dst_name,
            "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
            "done": 0, "sent": 0, "skipped": 0, "failed": 0,
            "id_map": {}, "started": _now(), "updated": _now(),
            "finished": False,
        }
        await ctx.storage.set(key, state)
        _STOP_FLAGS[task_id] = False

        task = ctx.create_task(
            _run_copy(ctx, task_id, client, src, dst, state, cfg),
            name=f"channel_mover-{task_id}",
        )
        _TASKS[task_id] = task

        await event.reply(
            f"🚀 开始搬运\n"
            f"源：{src_name}\n"
            f"目标：{dst_name}\n"
            f"节奏：{cfg.get('send_interval', 1.0)} 秒/条\n\n"
            f"正在定位最早消息… 发 status 看进度。"
        )


# ── 主搬运循环 ──────────────────────────────────────────────────────────
async def _run_copy(ctx, task_id, client, src, dst, state, cfg):
    key = f"task_{task_id}"
    drops, replaces = compile_filters(
        cfg.get("drop_regex", ""), cfg.get("replace_regex", "")
    )
    interval = float(cfg.get("send_interval", 1.0) or 1.0)
    batch_size = max(10, min(100, int(cfg.get("batch_size", 50) or 50)))
    copy_media = bool(cfg.get("copy_media", True))
    keep_albums = bool(cfg.get("keep_albums", True))
    mode = cfg.get("send_mode", "copy")
    keep_replies = bool(cfg.get("keep_replies", True))
    skip_service = bool(cfg.get("skip_service", True))
    flood_max = int(cfg.get("flood_wait_max", 300) or 300)

    try:
        # 定位最早 / 最新消息 ID（只在首次跑）
        if not state.get("min_id"):
            oldest = await _get_extreme(client, src, reverse=True)
            state["min_id"] = oldest.id if oldest else 0
            state["next_id"] = state["min_id"]
        if not state.get("max_id"):
            newest = await _get_extreme(client, src, reverse=False)
            state["max_id"] = newest.id if newest else 0
            state["total"] = max(0, state["max_id"] - state["min_id"] + 1)
            await ctx.storage.set(key, state)

        ctx.log.info(
            "[搬运] %s → %s  ID %s..%s (约 %s 条)",
            state["src_name"], state["dst_name"],
            state["min_id"], state["max_id"], state["total"],
        )

        pending = []          # 跨批未完结相册
        while not _STOP_FLAGS.get(task_id):
            next_id = state.get("next_id", 0)
            if is_finished(next_id, state.get("max_id", 0)):
                state["finished"] = True
                state["finished_at"] = _now()
                await ctx.storage.set(key, state)
                await ctx.notify(
                    f"✅ 频道搬运完成\n{build_progress_text(state)}",
                    category="频道搬运", level="success",
                )
                return

            # 从 next_id 起取一批（get_chat_history 用 min_id，含边界）
            # 必须 reverse=True：否则它返回的是整个频道「最新」的 batch 条，
            # 而不是从 next_id 往后由旧到新的 batch 条。
            page = []
            async for msg in client.get_chat_history(
                src, limit=batch_size, min_id=next_id, reverse=True,
            ):
                page.append(msg)
                if len(page) >= batch_size:
                    break

            if not page:
                # 这一段 ID 全是已删除/服务消息，直接跳过
                state["next_id"] = next_id + batch_size
                await ctx.storage.set(key, state)
                continue

            merged = pending + page
            groups = group_albums(merged, keep_albums)
            open_album = trailing_open_album(groups)
            if open_album:
                groups = groups[:-1]
                pending = open_album
            else:
                pending = []

            for group in groups:
                if _STOP_FLAGS.get(task_id):
                    break
                try:
                    await _send_group(
                        ctx, client, group, dst, cfg, drops, replaces,
                        copy_media, mode, keep_replies, skip_service,
                        state.setdefault("id_map", {}),
                    )
                    state["sent"] += 1
                except Exception as exc:  # noqa: BLE001
                    if type(exc).__name__ == "FloodWait":
                        seconds = getattr(exc, "value", 0) or getattr(exc, "x", 0) or 0
                        seconds = int(seconds) if seconds else 0
                        ctx.log.warning("[搬运] FloodWait %ss", seconds)
                        if seconds > flood_max:
                            state["paused_reason"] = f"FloodWait {seconds}s 超上限"
                            await ctx.storage.set(key, state)
                            await ctx.notify(
                                f"⚠️ 搬运暂停：FloodWait {seconds} 秒超过上限 {flood_max}\n"
                                f"发 resume 可继续。",
                                category="频道搬运", level="warning",
                            )
                            return
                        await asyncio.sleep(seconds + 1)
                        continue
                    state["failed"] += 1
                    ctx.log.warning("[搬运] 消息 %s 失败: %r", group[0].id, exc)

                state["done"] += 1
                state["next_id"] = next_id_after(group)
                state["updated"] = _now()
                # 每 20 条落一次盘，崩了最多丢 20 条进度
                if state["done"] % 20 == 0 or state["done"] <= 3:
                    await ctx.storage.set(key, state)

                if interval > 0:
                    await asyncio.sleep(interval)

            await ctx.storage.set(key, state)

    except asyncio.CancelledError:
        await ctx.storage.set(key, state)
        raise
    except Exception as exc:  # noqa: BLE001
        ctx.log.exception("[搬运] 任务异常中止")
        state["paused_reason"] = f"{type(exc).__name__}: {exc}"
        await ctx.storage.set(key, state)
        await ctx.notify(
            f"❌ 搬运中断：{type(exc).__name__}\n发 resume 从断点续传。",
            category="频道搬运", level="error",
        )


async def _send_group(ctx, client, group, dst, cfg, drops, replaces,
                      copy_media, mode, keep_replies, skip_service, id_map):
    """把一组（单条或相册）发到目标。"""
    if skip_service and all(is_service_message(m) for m in group):
        return

    reply_to = None
    if keep_replies:
        src_reply = getattr(group[0], "reply_to_message_id", None)
        if src_reply and src_reply in id_map:
            reply_to = id_map[src_reply]

    # ── 相册 ──
    if len(group) > 1:
        if not copy_media:
            return
        # copy_media_group 按相册首条 message_id 整组复制
        await client.copy_media_group(
            chat_id=dst, from_chat_id=group[0].chat.id, message_id=group[0].id,
        )
        return

    msg = group[0]
    text = msg.text or msg.caption or ""
    file_name = ""
    doc = getattr(msg, "document", None)
    if doc is not None:
        file_name = getattr(doc, "file_name", "") or ""

    dropped, text = apply_filters(text, file_name, drops, replaces)
    if dropped:
        return

    has_media = msg.media is not None and not is_service_message(msg)
    if has_media and not copy_media:
        return
    if not has_media and not text.strip():
        return

    if mode == "forward" and not drops and not replaces:
        await client.forward_messages(
            chat_id=dst, from_chat_id=msg.chat.id, message_ids=[msg.id],
        )
    else:
        await client.copy_message(
            chat_id=dst, from_chat_id=msg.chat.id, message_id=msg.id,
            caption=text or None, reply_to_message_id=reply_to,
        )


# ── 工具 ────────────────────────────────────────────────────────────────
async def _get_extreme(client, peer, reverse: bool):
    """取最早（reverse=True）或最新（reverse=False）一条消息。"""
    async for msg in client.get_chat_history(peer, limit=1, reverse=reverse):
        return msg
    return None


async def _peer_names(client, src, dst):
    src_chat = await client.get_chat(src)
    dst_chat = await client.get_chat(dst)
    return (
        getattr(src_chat, "title", None) or str(src),
        getattr(dst_chat, "title", None) or str(dst),
    )


def _now() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).strftime("%m-%d %H:%M:%S")


async def teardown(ctx):
    for tid, task in list(_TASKS.items()):
        _STOP_FLAGS[tid] = True
        if not task.done():
            task.cancel()
    _TASKS.clear()
