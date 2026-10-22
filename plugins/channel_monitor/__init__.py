# =============================================================================
# AWBotNest V2 插件：频道监控转发（channel_monitor）
#
# 实时监控多个源频道/群，把新消息转发到各自的目标群。
# 支持：多条「源 → 目标」规则、相册整组转发、关键词/正则过滤、
#       启用时补最近 N 条历史、FloodWait 退避、断线去重。
#
# 用法（在任意会话里发命令，命令需为自己发出）：
#   .chmon            查看所有规则状态
#   .chmon test 1     第 1 条规则的连通性自检
#   .chmon pause 1    暂停第 1 条规则
#   .chmon resume 1   恢复第 1 条规则
#
# 与 channel_mover（历史全量搬运）的区别：那个是"拉"（遍历 ID 区间），
# 这个是"推"（on_message 事件驱动），两者互不影响、互不依赖。
# =============================================================================

import asyncio
import time

from ._core import (
    AlbumBuffer,
    apply_filters,
    build_link,
    compile_filters,
    compile_keywords,
    is_service_message,
    match_rules,
    normalize_rules,
    passes_keywords,
    render_status,
    resolve_peer,
    should_skip,
)
from ._sender import Paused, append_link, forward_album, forward_one, with_flood_retry

__plugin__ = {
    "name": "频道监控转发",
    "id": "channel_monitor",
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "实时监控多个源频道，把新消息转发到对应目标群，支持相册、关键词过滤、启用时补历史。",
    "tags": ["监控", "转发", "频道", "同步"],
    "scope": "user",
    "plugin_api_version": 2,
    "resources": {
        "timeout_seconds": 120,
        "max_concurrency": 8,
        "max_background_tasks": 32,
        "failure_threshold": 10,
        "recovery_seconds": 30,
    },
    "config_schema": {
        # ── 转发规则 ──
        "rules": {
            "type": "list", "default": [], "label": "转发规则",
            "section": "转发规则", "order": 1, "item_label": "规则",
            "help": "每一行是一条「源 → 目标」。账号必须已加入源频道和目标群。",
            "fields": {
                "source": {"type": "string", "label": "源频道",
                           "help": "@username、t.me/xxx、t.me/c/xxx、-100xxxxxxxxxx"},
                "target": {"type": "string", "label": "目标群", "help": "同上"},
                "enabled": {"type": "boolean", "label": "启用", "default": True},
            },
        },
        # ── 补历史 ──
        "backfill_enable": {
            "type": "boolean", "default": True, "label": "启用时补历史",
            "section": "补历史", "order": 11,
            "help": "插件启用/重载时，先把源频道最近的历史补过来，避免上线瞬间漏消息。",
        },
        "backfill_count": {
            "type": "number", "default": 20, "label": "补多少条",
            "min": 0, "max": 5000, "section": "补历史", "order": 12,
            "help": "由你自己设置补多少条。填 0 = 不补。从旧到新发，保证目标群时间顺序正确。",
        },
        # ── 内容 ──
        "copy_media": {
            "type": "boolean", "default": True, "label": "转发媒体（图片/视频/文件/语音/贴纸）",
            "section": "内容", "order": 21,
            "help": "关闭则只转发纯文字消息，带媒体的整条跳过（服务端转发无法剥离媒体）。",
        },
        "keep_albums": {
            "type": "boolean", "default": True, "label": "保持相册分组",
            "section": "内容", "order": 22,
            "help": "开=相册作为一组转发；关=拆成单条。",
        },
        "attach_source": {
            "type": "boolean", "default": False, "label": "附带原消息链接",
            "section": "内容", "order": 23,
            "help": "开=转发后在消息末尾追加一行 t.me/c 链接，方便回查源消息。",
        },
        # ── 过滤 ──
        "keywords": {
            "type": "text", "default": "", "label": "只转含这些词的消息",
            "section": "过滤规则", "order": 31,
            "help": "每行一个词，命中任一即转发。留空=全部转发。大小写不敏感。",
        },
        "drop_regex": {
            "type": "text", "default": "", "label": "丢弃正则（命中则跳过）",
            "section": "过滤规则", "order": 32,
            "help": "每行一条 Python 正则。命中文字或文件名就跳过该消息。",
        },
        "replace_regex": {
            "type": "text", "default": "", "label": "替换正则",
            "section": "过滤规则", "order": 33,
            "help": "格式：原正则|替换内容，每行一条。例：广告|***",
        },
        "skip_service": {
            "type": "boolean", "default": True, "label": "跳过入群/退群等系统消息",
            "section": "过滤规则", "order": 34,
        },
        # ── 速率 ──
        "album_window": {
            "type": "slider", "default": 0.8, "label": "相册合并窗口(秒)",
            "min": 0.3, "max": 3.0, "step": 0.1, "section": "速率控制", "order": 41,
            "help": "Telethon 把相册成员逐条推送。等这么多秒没有新成员就整组发出。相册被拆散就调大。",
        },
        "flood_wait_max": {
            "type": "number", "default": 300, "label": "FloodWait 上限(秒)",
            "min": 10, "max": 3600, "section": "速率控制", "order": 42,
            "help": "触发限流时最多等这么久，超过则暂停该规则并通知，用 resume 恢复。",
        },
        # ── 命令 ──
        "command": {
            "type": "string", "default": "/chmon", "label": "触发命令",
            "section": "命令", "order": 51,
            "help": "自己发出、以此开头的消息会触发。/chmon 与 .chmon 等价。",
        },
    },
}


# ── 运行时 ──────────────────────────────────────────────────────────────
_RT = None


def _bare(cmd: str) -> str:
    return (cmd or "").lstrip("/.").strip().lower() or "chmon"


def _attr(obj, name, default=None):
    """同时兼容 Telethon Event（字段在 .message 上）和裸 Message。"""
    v = getattr(obj, name, None)
    if v is None and hasattr(obj, "message"):
        v = getattr(obj.message, name, None)
    return default if v is None else v


def _file_name(obj):
    f = getattr(obj, "file", None)
    if f is None:
        return ""
    return getattr(f, "name", "") or ""


def _marked_id(entity) -> int:
    """把实体转成 Telegram 的带标记 ID（超级群/频道为 -100xxx）。"""
    eid = int(getattr(entity, "id", 0) or 0)
    if eid <= 0:
        return eid
    tname = type(entity).__name__
    if tname in ("Channel", "ChannelForbidden"):
        return int(f"-100{eid}")
    if tname in ("Chat", "ChatForbidden"):
        return -eid
    return eid


def _state_key(rule) -> str:
    return "cm_" + rule.key.replace("|", "_").replace("-", "m")


class _Slot:
    """单条规则的运行时状态。"""

    __slots__ = ("state", "queue", "worker", "buffer", "pending", "ready",
                 "paused", "last_persist")

    def __init__(self, window: float):
        self.state: dict = {"last_id": 0, "sent": 0, "skipped": 0, "failed": 0}
        self.queue = asyncio.Queue(maxsize=2000)
        self.worker = None
        self.buffer = AlbumBuffer(window)
        self.pending = []
        self.ready = False
        self.paused = False
        self.last_persist = 0.0


class _Runtime:
    def __init__(self, ctx, cfg, rules):
        self.ctx = ctx
        self.cfg = cfg
        self.rules = rules
        self.client = None
        self.tasks = []
        self.resolved = False
        window = float(cfg.get("album_window", 0.8) or 0.8)
        self.slots = {r.key: _Slot(window) for r in rules}
        self.by_chat = {}
        self.drops, self.replaces = compile_filters(
            cfg.get("drop_regex", ""), cfg.get("replace_regex", "")
        )
        self.keywords = compile_keywords(cfg.get("keywords", ""))

    def rebuild_index(self):
        idx = {}
        for r in self.rules:
            if r.usable:
                idx.setdefault(r.src_id, []).append(r)
        self.by_chat = idx

    def slot(self, rule) -> _Slot:
        return self.slots[rule.key]


async def _resolve_rules(rt) -> None:
    """把规则里的 @username / t.me 解析成真实 ID。"""
    if rt.client is None or rt.resolved:
        return
    for r in rt.rules:
        if not r.enabled or r.error:
            continue
        src = resolve_peer(r.source)
        dst = resolve_peer(r.target)
        if src is None or dst is None:
            r.error = "源或目标格式无法识别"
            rt.ctx.log.error("[监控] 规则 %s → %s：%s", r.source, r.target, r.error)
            continue
        try:
            se = await rt.client.get_entity(src)
            de = await rt.client.get_entity(dst)
            r.src_id = _marked_id(se)
            r.dst_id = _marked_id(de)
            r.src_title = getattr(se, "title", "") or getattr(se, "first_name", "") or r.source
            r.dst_title = getattr(de, "title", "") or getattr(de, "first_name", "") or r.target
        except Exception as exc:  # noqa: BLE001
            r.error = f"解析失败：{exc!r}"
            rt.ctx.log.error("[监控] 规则 %s → %s 解析失败: %r", r.source, r.target, exc)
    rt.resolved = True
    rt.rebuild_index()
    rt.ctx.log.info(
        "[监控] 规则就绪 %d/%d", len(rt.by_chat), len(rt.rules)
    )


async def _persist(rt, rule, slot) -> None:
    try:
        await rt.ctx.storage.set(_state_key(rule), dict(slot.state))
    except Exception as exc:  # noqa: BLE001
        rt.ctx.log.warning("[监控] 状态落盘失败: %r", exc)


# ── 过滤与入队 ──────────────────────────────────────────────────────────
class _Ref:
    """相册缓冲用的最小消息引用。"""

    __slots__ = ("id", "media_group_id")

    def __init__(self, msg_id: int, gid):
        self.id = msg_id
        self.media_group_id = gid


async def _accept(rt, rule, slot, obj, now: float) -> None:
    """过滤后决定：进相册缓冲 or 直接入队。"""
    msg_id = int(_attr(obj, "id", 0) or 0)
    if not msg_id:
        return

    if bool(rt.cfg.get("skip_service", True)) and is_service_message(obj):
        slot.state["skipped"] += 1
        return

    text = _attr(obj, "text", "") or ""
    fname = _file_name(obj)
    dropped, text = apply_filters(text, fname, rt.drops, rt.replaces)
    if dropped:
        slot.state["skipped"] += 1
        return
    if not passes_keywords(text, fname, rt.keywords):
        slot.state["skipped"] += 1
        return

    media = _attr(obj, "media", None)
    if not bool(rt.cfg.get("copy_media", True)) and media is not None:
        slot.state["skipped"] += 1
        return
    if not text.strip() and media is None:
        slot.state["skipped"] += 1
        return

    gid = _attr(obj, "media_group_id", None)
    if gid and bool(rt.cfg.get("keep_albums", True)):
        slot.buffer.add(_Ref(msg_id, gid), now)
        return

    await _enqueue(slot, [msg_id])


async def _enqueue(slot: _Slot, ids) -> None:
    ids = list(ids)
    item = {"ids": ids, "last_id": max(ids)}
    try:
        slot.queue.put_nowait(item)
    except asyncio.QueueFull:
        slot.state["failed"] += 1


# ── 发送 worker ─────────────────────────────────────────────────────────
async def _send_item(rt, rule, slot, item) -> None:
    client = rt.client
    if client is None:
        raise RuntimeError("没有可用的用户账号客户端")
    ids = item["ids"]
    max_wait = int(rt.cfg.get("flood_wait_max", 300) or 300)

    if len(ids) > 1:
        sent = await with_flood_retry(
            lambda: forward_album(client, rule.dst_id, ids, rule.src_id),
            max_wait, rt.ctx.log,
        )
    else:
        sent = await with_flood_retry(
            lambda: forward_one(client, rule.dst_id, ids[0], rule.src_id),
            max_wait, rt.ctx.log,
        )

    if bool(rt.cfg.get("attach_source", False)):
        await append_link(sent, build_link(rule.src_id, ids[-1]))

    slot.state["last_id"] = max(int(slot.state.get("last_id", 0) or 0), item["last_id"])
    slot.state["sent"] = int(slot.state.get("sent", 0) or 0) + 1

    now = time.monotonic()
    if slot.state["sent"] % 20 == 0 or now - slot.last_persist > 5:
        await _persist(rt, rule, slot)
        slot.last_persist = now


async def _worker(rt, rule, slot) -> None:
    while True:
        item = await slot.queue.get()
        try:
            await _send_item(rt, rule, slot, item)
        except asyncio.CancelledError:
            raise
        except Paused as exc:
            slot.paused = True
            slot.state["paused_reason"] = f"FloodWait {exc.seconds}s 超上限"
            await _persist(rt, rule, slot)
            rt.ctx.log.warning("[监控] 规则 %s 暂停: FloodWait %ss", rule.key, exc.seconds)
            try:
                await rt.ctx.notify(
                    f"⚠️ 规则已暂停：{rule.src_title or rule.source} → "
                    f"{rule.dst_title or rule.target}\n"
                    f"FloodWait {exc.seconds} 秒超过上限，发 .chmon resume "
                    f"{rule.index + 1} 恢复。",
                    category="频道监控", level="warning",
                )
            except Exception:  # noqa: BLE001 - 通知失败不影响暂停
                pass
            return
        except Exception as exc:  # noqa: BLE001
            slot.state["failed"] = int(slot.state.get("failed", 0) or 0) + 1
            rt.ctx.log.warning("[监控] 转发失败 %s: %r", item.get("ids"), exc)
        finally:
            try:
                slot.queue.task_done()
            except ValueError:
                pass


# ── 相册 flush ──────────────────────────────────────────────────────────
async def _flusher(rt) -> None:
    while True:
        await asyncio.sleep(0.2)
        now = time.monotonic()
        for rule in rt.rules:
            slot = rt.slots[rule.key]
            if not slot.ready or slot.paused:
                continue
            try:
                ready = slot.buffer.pop_ready(now)
            except Exception as exc:  # noqa: BLE001
                rt.ctx.log.warning("[监控] 相册缓冲异常: %r", exc)
                continue
            for items in ready:
                await _enqueue(slot, [m.id for m in items])


# ── 补历史 ──────────────────────────────────────────────────────────────
async def _backfill(rt, rule, slot) -> None:
    """先记 last_id=最新，再补最近 N 条，最后排空补期间到达的实时消息。

    顺序是硬要求：先设 last_id 再补，补的过程中到达的新消息 id > last_id，
    不会被去重误杀，也不会在补完后重复发一次。
    """
    client = rt.client
    if client is None:
        slot.ready = True
        return

    count = int(rt.cfg.get("backfill_count", 20) or 0)
    enabled = bool(rt.cfg.get("backfill_enable", True)) and count > 0
    prev = int(slot.state.get("last_id", 0) or 0)

    # 取一次源频道最新 ID。拿不到说明频道不可达，直接放过，不阻塞实时。
    newest_id = prev
    try:
        async for m in client.iter_messages(rule.src_id, limit=1):
            newest_id = max(newest_id, int(m.id))
            break
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        rule.error = f"读不到源频道：{exc!r}"
        rt.ctx.log.error("[监控] %s 读取源频道失败: %r", rule.key, exc)
        slot.ready = True
        return

    try:
        if enabled:
            msgs = []
            if prev == 0:
                # 首次启用：补最近 N 条（含最新），从旧到新
                async for m in client.iter_messages(rule.src_id, limit=count):
                    msgs.append(m)
                msgs.reverse()
                slot.state["last_id"] = newest_id
            else:
                # 已有进度：只补断档期间漏掉的（id > prev），避免重载后重复转发
                async for m in client.iter_messages(rule.src_id, limit=count):
                    if int(m.id) <= prev:
                        break
                    msgs.append(m)
                msgs.reverse()
                slot.state["last_id"] = max(newest_id, prev)
            for m in msgs:
                await _accept(rt, rule, slot, m, time.monotonic())
                await asyncio.sleep(0)
            rt.ctx.log.info("[监控] %s 补历史 %d 条", rule.key, len(msgs))
        else:
            # 不补：直接把进度推到最新，只接之后的新消息
            slot.state["last_id"] = max(newest_id, prev)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        rt.ctx.log.error("[监控] %s 补历史失败: %r", rule.key, exc)

    # 排空补历史期间到达的实时消息（按 id > last_id 去重）
    for obj in slot.pending:
        if should_skip(_attr(obj, "id", 0), slot.state.get("last_id", 0)):
            continue
        await _accept(rt, rule, slot, obj, time.monotonic())
    slot.pending.clear()
    slot.ready = True


# ── setup ───────────────────────────────────────────────────────────────
async def setup(ctx):
    global _RT
    cfg = ctx.config
    rules, warnings = normalize_rules(cfg.get("rules"))
    for w in warnings:
        ctx.log.warning("[监控] 规则配置：%s", w)

    rt = _Runtime(ctx, cfg, rules)
    _RT = rt

    users = getattr(ctx, "users", None) or []
    rt.client = users[0] if users else None
    if rt.client is not None:
        await _resolve_rules(rt)

    for rule in rules:
        slot = rt.slots[rule.key]
        try:
            st = await ctx.storage.get(_state_key(rule), None)
            if isinstance(st, dict) and st:
                slot.state.update(st)
                slot.paused = bool(st.get("paused_reason"))
        except Exception as exc:  # noqa: BLE001
            ctx.log.warning("[监控] 读取状态失败 %s: %r", rule.key, exc)

    # 消息事件
    @ctx.on_message(incoming=True)
    async def on_new_message(event):
        r = _RT
        if r is None or not r.rules:
            return

        if not r.resolved:
            # setup 时账号还没连上：用事件自带的 client 补解析
            if r.client is None:
                r.client = getattr(event, "client", None)
            await _resolve_rules(r)

        hits = match_rules(getattr(event, "chat_id", None), r.rules)
        if not hits:
            return

        now = time.monotonic()
        for rule in hits:
            slot = r.slots[rule.key]
            if slot.paused:
                continue
            if should_skip(_attr(event, "id", 0), slot.state.get("last_id", 0)):
                continue
            if not slot.ready:
                slot.pending.append(event)
                if len(slot.pending) > 500:
                    slot.pending.pop(0)
                continue
            try:
                await _accept(r, rule, slot, event, now)
            except Exception as exc:  # noqa: BLE001
                ctx.log.warning("[监控] 处理消息异常: %r", exc)

    # 命令
    @ctx.on_message(incoming=False, outgoing=True)
    async def on_command(event):
        r = _RT
        if r is None:
            return
        text = (event.text or "").strip()
        if not text:
            return
        bare = _bare(r.cfg.get("command", "/chmon"))
        head = text.split(maxsplit=1)[0].lower()
        if head not in (f"/{bare}", f".{bare}"):
            return

        parts = text.split()
        sub = parts[1].lower() if len(parts) >= 2 else ""

        if sub in ("", "status"):
            rows = []
            for rule in r.rules:
                slot = r.slots[rule.key]
                state_text = "运行中 ▶"
                if rule.error:
                    state_text = "配置错误 ⚠️"
                elif slot.paused:
                    state_text = "已暂停 ⏸"
                elif not slot.ready:
                    state_text = "补历史中 ⏳"
                rows.append({
                    "name": rule.src_title or rule.source,
                    "target": rule.dst_title or rule.target,
                    "last_id": slot.state.get("last_id"),
                    "sent": slot.state.get("sent", 0),
                    "skipped": slot.state.get("skipped", 0),
                    "failed": slot.state.get("failed", 0),
                    "error": rule.error,
                    "state": state_text,
                })
            return await event.reply(render_status(rows))

        if sub in ("test", "pause", "resume"):
            if len(parts) < 3 or not parts[2].isdigit():
                return await event.reply(f"用法：.{bare} {sub} <规则序号>")
            idx = int(parts[2]) - 1
            if idx < 0 or idx >= len(r.rules):
                return await event.reply(f"没有第 {idx + 1} 条规则，发 .{bare} 看列表。")
            rule = r.rules[idx]
            slot = r.slots[rule.key]

            if sub == "pause":
                slot.paused = True
                slot.state["paused_reason"] = "手动暂停"
                await _persist(r, rule, slot)
                return await event.reply(f"⏸ 已暂停第 {idx + 1} 条规则")

            if sub == "resume":
                slot.paused = False
                slot.state.pop("paused_reason", None)
                await _persist(r, rule, slot)
                if slot.worker is None or slot.worker.done():
                    slot.worker = ctx.create_task(
                        _worker(r, rule, slot), name=f"cm-worker-{idx + 1}"
                    )
                return await event.reply(f"▶ 已恢复第 {idx + 1} 条规则")

            # test
            if rule.error:
                return await event.reply(f"❌ 规则不可用：{rule.error}")
            client = r.client
            if client is None:
                return await event.reply("❌ 没有已连接的用户账号")
            try:
                ent = await client.get_entity(rule.src_id)
                title = getattr(ent, "title", "") or str(rule.src_id)
            except Exception as exc:  # noqa: BLE001
                return await event.reply(f"❌ 读不到源频道：{exc!r}")
            try:
                await client.send_message(
                    rule.dst_id,
                    f"📡 频道监控转发连通性测试\n源：{title}\n规则序号：{idx + 1}",
                )
            except Exception as exc:  # noqa: BLE001
                return await event.reply(f"❌ 发不到目标群：{exc!r}")
            return await event.reply(f"✅ 规则 {idx + 1} 正常\n源：{title}")

        usage = (
            f"用法：\n"
            f"  .{bare}            看状态\n"
            f"  .{bare} test 1     连通性自检\n"
            f"  .{bare} pause 1    暂停\n"
            f"  .{bare} resume 1   恢复"
        )
        return await event.reply(usage)

    # 每规则：一个 worker + 一次补历史
    for rule in rules:
        slot = rt.slots[rule.key]
        if not rule.usable:
            ctx.log.warning("[监控] 规则不可用，跳过：%s → %s (%s)",
                            rule.source, rule.target, rule.error)
            slot.ready = True
            continue
        if slot.paused:
            slot.ready = True
            continue
        slot.worker = ctx.create_task(_worker(rt, rule, slot), name=f"cm-worker-{rule.index + 1}")
        rt.tasks.append(ctx.create_task(
            _backfill(rt, rule, slot), name=f"cm-backfill-{rule.index + 1}"
        ))

    rt.tasks.append(ctx.create_task(_flusher(rt), name="cm-flusher"))

    ctx.log.info("[监控] 已加载 %d 条规则", len(rules))


async def teardown(ctx):
    global _RT
    rt = _RT
    if rt is None:
        return
    for rule in rt.rules:
        slot = rt.slots[rule.key]
        for items in slot.buffer.flush_all():
            ctx.log.info("[监控] 停用时丢弃未发相册 %d 条", len(items))
        if slot.worker is not None and not slot.worker.done():
            slot.worker.cancel()
        await _persist(rt, rule, slot)
    for task in rt.tasks:
        if task is not None and not task.done():
            task.cancel()
    _RT = None
