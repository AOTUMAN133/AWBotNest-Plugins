# =============================================================================
# AWBotNest 插件：复读转发（fz）
#
# 由 /zf 或 .zf 触发：把你回复的那条消息，在当前会话里转发/复读 N 次。
#   回复某条消息 + /zf       —— 转发 1 次
#   回复某条消息 + /zf 5     —— 转发 5 次
# 支持配置复制搬运模式，打开后不显示「转发自」标注。
# =============================================================================

import asyncio

__plugin__ = {
    "name": "复读转发",
    "id": "fz",
    "version": "1.0.0",
    "author": "AOTUMAN133",
    "description": "回复一条消息再发 /zf [次数]，把它在当前会话转发/复读若干次。支持复制搬运模式。",
    "icon": "https://raw.githubusercontent.com/AWdress/AWBotNest-Plugins/main/plugins/icons/family_relay.png",
    "changelog": "v1.0.0 初始版本\n- 基于 zf 改造，增加复制搬运开关",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "copy_mode": {
            "type": "boolean", "default": False, "label": "复制搬运（不标注转发来源）",
            "cols": 3, "order": 1, "section": "功能开关",
            "help": "开=复制搬运，不带「转发自」标注；关=原生转发，显示转发来源。",
        },
        "command": {
            "type": "string", "default": ".zf", "label": "触发命令",
            "section": "命令", "order": 10, "help": "自己发出、以此开头的消息会触发。/zf 与 .zf 等价。",
        },
        "interval": {
            "type": "slider", "default": 0.3, "label": "每次间隔(秒)",
            "min": 0, "max": 5, "step": 0.1, "section": "重复限制", "order": 20,
            "help": "多次转发时每次之间的间隔，避免过快触发限流。",
        },
        "max_times": {
            "type": "number", "default": 50, "label": "最多次数",
            "min": 1, "max": 500, "section": "重复限制", "order": 21, "help": "单次命令允许的最大转发次数。",
        },
    },
}


def _bare(command: str) -> str:
    return (command or "").lstrip("/.").strip().lower() or "zf"


async def setup(ctx):
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=-15)
    async def forward_to_group(client, message):
        cfg = ctx.config
        bare = _bare(cfg.get("command", ".fz"))
        text = message.text or ""
        head = text.split(maxsplit=1)[0].lower() if text else ""
        if head not in (f"/{bare}", f".{bare}"):
            return

        reply = message.reply_to_message
        if not reply:
            return await message.edit("请先回复一条要转发的消息")

        # 解析次数
        parts = text.split()
        try:
            re_times = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 1
        except (IndexError, ValueError):
            re_times = 1
        re_times = max(1, min(re_times, int(cfg.get("max_times", 50) or 50)))

        interval = float(cfg.get("interval", 0.3) or 0)
        copy_mode = bool(cfg.get("copy_mode", False))

        for _ in range(re_times):
            try:
                if interval > 0:
                    await asyncio.sleep(interval)
                if copy_mode:
                    await reply.copy(reply.chat.id, message_thread_id=message.message_thread_id)
                else:
                    await reply.forward(reply.chat.id, message_thread_id=reply.message_thread_id)
            except Exception as e:  # noqa: BLE001 - 单次失败不中断整体
                ctx.log.debug("[复读转发] 单次失败: %r", e)

        try:
            await message.delete()
        except Exception:
            pass


async def teardown(ctx):
    pass