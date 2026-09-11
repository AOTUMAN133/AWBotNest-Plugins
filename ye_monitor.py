# -*- coding: utf-8 -*-
# =============================================================================
# AWBotNest V2 插件：小叶对话监控（ye_monitor）
#
# 从 PagerMaid 版移植，已按 AWBotNest V2 (Telethon) 规范迁移。
# 监控指定 TG 聊天窗口，识别关键词后自动回复。
# 支持精确/包含匹配、触发通知、去重。
#
# 用法（在目标聊天里用自己的账号发送）：
#     .yemon on              # 开启监控
#     .yemon off             # 关闭监控
#     .yemon target @name    # 设置监控对象（@username 或 chat_id）
#     .yemon keyword 777888  # 设置关键词
#     .yemon reply 同意      # 设置回复词
#     .yemon mode exact      # 精确匹配
#     .yemon mode contains   # 包含匹配（默认）
#     .yemon notify on/off   # 触发通知开关
#     .yemon cx              # 查看当前配置
#
# 也可以在插件设置页里可视化编辑全部配置（推荐）。
# =============================================================================

__plugin__ = {
    "name": "小叶对话监控",
    "id": "ye_monitor",
    "version": "2.0.2",
    "author": "AWdress",
    "description": "监控指定聊天窗口，识别关键词后自动回复。用法: .yemon on|cx",
    "scope": "user",
    "requirements": [],
    "plugin_api_version": 2,
    "resources": {
        "timeout_seconds": 120,
        "max_concurrency": 8,
        "max_background_tasks": 16,
        "failure_threshold": 5,
    },
    "config_schema": {
        "enable": {
            "type": "boolean", "default": False, "label": "启用监控",
            "cols": 3, "order": 1, "section": "功能开关",
            "help": "总开关。关闭后不监听任何消息。",
        },
        "notify_enabled": {
            "type": "boolean", "default": True, "label": "触发通知",
            "cols": 3, "order": 2, "section": "功能开关",
            "help": "触发回复时同时推送通知（平台 bot 会话）。",
        },
        "target_chat": {
            "type": "string", "default": "", "label": "监控对象",
            "order": 3, "section": "监控设置",
            "help": "对哪个会话监控。填 @username 或 chat_id（数字）。可用 .id 查看当前会话。",
        },
        "keyword": {
            "type": "string", "default": "777888", "label": "监听关键词",
            "order": 4, "section": "监控设置",
            "help": "消息里出现该关键词即触发。",
        },
        "reply_text": {
            "type": "string", "default": "同意", "label": "自动回复词",
            "order": 5, "section": "监控设置",
            "help": "触发后发送的回复内容。",
        },
        "reply_delay": {
            "type": "number", "default": 10, "label": "回复延迟(秒)",
            "min": 0, "max": 300, "order": 6, "section": "监控设置",
            "help": "监控到消息后延迟多少秒才回复。0=立即回复。",
        },
        "match_mode": {
            "type": "select", "default": "contains", "label": "匹配模式",
            "order": 7, "section": "监控设置",
            "options": {"contains": "包含匹配（含关键词即触发）",
                        "exact": "精确匹配（消息完全等于关键词）"},
            "help": "包含=消息里出现关键词；精确=整条消息等于关键词。",
        },
        "notify_chat": {
            "type": "string", "default": "", "label": "通知发送到",
            "order": 8, "section": "监控设置",
            "help": "留空=发送到平台 bot 会话；填 @username 或 chat_id 可指定。",
        },
    },
}

# 简易去重（最近 100 条指纹，存 ctx.storage 跨模块重启保留）
_MAX_RECENT = 100
_KV_FINGERPRINTS = "ye_monitor_recent_fingerprints"


def _make_fingerprint(chat_id, message_id, text):
    return f"{chat_id}:{message_id}:{text.strip()}"


def _match_keyword(text: str, keyword: str, mode: str) -> bool:
    if not text or not keyword:
        return False
    if mode == "exact":
        return text.strip() == keyword.strip()
    return keyword in text


async def _is_recent(ctx, fingerprint: str) -> bool:
    recent = await ctx.storage.get(_KV_FINGERPRINTS, []) or []
    if fingerprint in recent:
        return True
    recent.append(fingerprint)
    if len(recent) > _MAX_RECENT:
        recent.pop(0)
    await ctx.storage.set(_KV_FINGERPRINTS, recent)
    return False


def _target_match(chat, target: str) -> bool:
    """target 为纯数字 → 匹配 chat_id；否则匹配 @username（不区分大小写）。"""
    if not target:
        return False
    chat_id = getattr(chat, "id", None)
    if target.isdigit():
        return chat_id is not None and chat_id == int(target)
    username = getattr(chat, "username", None)
    username = username.lower() if username else ""
    return username == target.lower().lstrip("@")


def _chat_label(chat) -> str:
    title = getattr(chat, "title", "") or ""
    if title:
        return str(title)
    uname = getattr(chat, "username", "") or ""
    if uname:
        return f"@{uname}"
    return str(getattr(chat, "id", "?"))


async def setup(ctx):
    """注册监控 handler 和命令 handler（V2: Telethon 单事件参数）。"""

    # ── 监控 handler：只监听 target_chat 指定会话（V2 chats= 过滤，不监听所有频道）──
    target_cfg = str(ctx.config.get("target_chat", "") or "").strip()
    # chats= 接受: 数字 chat_id / @username 字符串; None=不限制(代码内仍做 _target_match 双保险)
    monitor_chats = None
    if target_cfg:
        monitor_chats = int(target_cfg) if target_cfg.isdigit() else target_cfg

    @ctx.on_message(incoming=True, chats=monitor_chats)
    async def _monitor(event):
        try:
            ctx.log.info("[小叶监控] 收到消息 chat_id=%s chat_username=%s text=%r",
                         getattr(event.chat, "id", None),
                         getattr(event.chat, "username", None),
                         (event.text or "")[:50])
            if not ctx.config.get("enable", False):
                ctx.log.info("[小叶监控] enable=False, 跳过")
                return
            target = str(ctx.config.get("target_chat", "") or "").strip()
            ctx.log.info("[小叶监控] target=%r 匹配=%s", target, _target_match(event.chat, target))
            if not target or not _target_match(event.chat, target):
                return

            text = (event.text or "").strip()
            keyword = str(ctx.config.get("keyword", "") or "").strip()
            mode = str(ctx.config.get("match_mode", "contains") or "contains")
            ctx.log.info("[小叶监控] keyword=%r mode=%s 命中=%s", keyword, mode, _match_keyword(text, keyword, mode))
            if not _match_keyword(text, keyword, mode):
                return

            fp = _make_fingerprint(event.chat_id, event.id, text)
            if await _is_recent(ctx, fp):
                ctx.log.info("[小叶监控] 去重命中, 跳过")
                return

            reply_text = str(ctx.config.get("reply_text", "") or "").strip()
            if not reply_text:
                return
            ctx.log.info("[小叶监控] 将回复: %r", reply_text)

            # 延迟回复（默认 10 秒，可配置）。去重已在上方完成，等待期间不重复触发。
            import asyncio as _asyncio
            delay = int(ctx.config.get("reply_delay", 10) or 10)
            if delay > 0:
                await _asyncio.sleep(delay)

            # 直接发送回复词（不回复引用原消息，避免暴露来源）
            try:
                await event.client.send_message(event.chat_id, reply_text)
            except Exception:
                pass

            # 触发通知
            if ctx.config.get("notify_enabled", True):
                preview = text if len(text) <= 300 else text[:300] + "…"
                notify_text = (
                    "🎯 小叶监控已触发\n\n"
                    f"聊天: {_chat_label(event.chat)}\n"
                    f"关键词: {keyword}\n"
                    f"回复词: {reply_text}\n"
                    f"原消息:\n{preview}"
                )
                notify_chat = str(ctx.config.get("notify_chat", "") or "").strip()
                try:
                    if notify_chat:
                        target_id = int(notify_chat) if notify_chat.isdigit() else notify_chat
                        await event.client.send_message(target_id, notify_text)
                    else:
                        await ctx.notify(notify_text, level="info", category="小叶监控")
                except Exception:
                    pass  # 通知失败不阻塞主流程
        except Exception as e:
            ctx.log.error("[小叶监控] 处理异常: %r", e)

    # ── 命令 handler：.yemon 系列子命令 + 工具命令，单 handler 分发 ──
    @ctx.on_message(outgoing=True)
    async def _cmd(event):
        text = (event.text or "").strip()
        parts = text.split()
        if not parts:
            return
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd == ".yemon":
            sub = args[0].lower() if args else ""
            if not sub or sub == "cx":
                await event.edit(
                    "当前配置：\n"
                    f"enabled = {ctx.config.get('enable', False)}\n"
                    f"target_chat = {ctx.config.get('target_chat', '')}\n"
                    f"keyword = {ctx.config.get('keyword', '')}\n"
                    f"reply_text = {ctx.config.get('reply_text', '')}\n"
                    f"match_mode = {ctx.config.get('match_mode', 'contains')}\n"
                    f"notify = {ctx.config.get('notify_enabled', True)}"
                )
                return

            if sub == "on":
                ctx.update_config({"enable": True})
                await event.edit("✅ 小叶监控已开启")
                return
            if sub == "off":
                ctx.update_config({"enable": False})
                await event.edit("✅ 小叶监控已关闭")
                return

            if sub == "target":
                if len(args) < 2:
                    await event.edit("❌ 用法: .yemon target <@username|chat_id>")
                    return
                val = " ".join(args[1:]).strip()
                ctx.update_config({"target_chat": val})
                await event.edit(f"✅ 监控对象已设置为: {val}")
                return

            if sub == "keyword":
                if len(args) < 2:
                    await event.edit("❌ 用法: .yemon keyword <关键词>")
                    return
                val = " ".join(args[1:]).strip()
                ctx.update_config({"keyword": val})
                await event.edit(f"✅ 监听关键词已设置为: {val}")
                return

            if sub == "reply":
                if len(args) < 2:
                    await event.edit("❌ 用法: .yemon reply <回复词>")
                    return
                val = " ".join(args[1:]).strip()
                ctx.update_config({"reply_text": val})
                await event.edit(f"✅ 自动回复词已设置为: {val}")
                return

            if sub == "mode":
                if len(args) < 2:
                    await event.edit("❌ 用法: .yemon mode contains|exact")
                    return
                mode = args[1].strip().lower()
                if mode not in ("contains", "exact"):
                    await event.edit("❌ mode 仅支持: contains 或 exact")
                    return
                ctx.update_config({"match_mode": mode})
                await event.edit(f"✅ 匹配模式已设置为: {mode}")
                return

            if sub == "notify":
                if len(args) < 2:
                    await event.edit("❌ 用法: .yemon notify on|off")
                    return
                val = args[1].strip().lower()
                if val not in ("on", "off"):
                    await event.edit("❌ notify 仅支持: on 或 off")
                    return
                ctx.update_config({"notify_enabled": val == "on"})
                await event.edit(f"✅ 触发通知已设置为: {val}")
                return

            await event.edit(
                "用法:\n"
                ".yemon on|off\n"
                ".yemon target <@username|chat_id>\n"
                ".yemon keyword <关键词>\n"
                ".yemon reply <回复词>\n"
                ".yemon mode contains|exact\n"
                ".yemon notify on|off\n"
                ".yemon cx"
            )
            return

        # ── 工具命令 ──
        if cmd in (".id", ".currentid"):
            chat = event.chat
            await event.edit(
                "当前对话信息:\n"
                f"chat.id: {chat.id}\n"
                f"chat.type: {getattr(chat, 'type', 'N/A')}\n"
                f"chat.title: {_chat_label(chat)}\n\n"
                f"✅ 请使用: .yemon target {chat.id}"
            )
            return

        if cmd == ".chatid":
            if len(args) < 1:
                await event.edit("❌ 用法: .chatid @username")
                return
            target = args[0].strip()
            if not target.startswith("@"):
                await event.edit("❌ 请提供 @username 格式")
                return
            try:
                user = await event.client.get_entity(target)
                chat = await event.client.get_entity(user.id)
                await event.edit(
                    f"私聊 chat_id 信息:\n"
                    f"目标: {target}\n"
                    f"chat.id: {chat.id}\n"
                    f"chat.type: {getattr(chat, 'type', 'N/A')}\n"
                    f"chat.title: {_chat_label(chat)}\n\n"
                    f"✅ 请使用: .yemon target {chat.id}"
                )
            except Exception as e:
                await event.edit(f"❌ 获取失败: {str(e)}")
            return

        if cmd == ".yetest":
            await event.edit(
                "✅ 脚本运行正常\n\n"
                f"当前监控配置:\n"
                f"enabled = {ctx.config.get('enable', False)}\n"
                f"target_chat = {ctx.config.get('target_chat', '')}\n"
                f"keyword = {ctx.config.get('keyword', '')}\n"
                f"reply_text = {ctx.config.get('reply_text', '')}\n"
                f"match_mode = {ctx.config.get('match_mode', 'contains')}\n"
                f"notify = {ctx.config.get('notify_enabled', True)}\n\n"
                "监听器状态: 已注册"
            )
            return


async def teardown(ctx):
    pass