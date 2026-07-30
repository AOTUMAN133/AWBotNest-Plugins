# -*- coding: utf-8 -*-
# AWBotNest 插件：代发助手 (msg_relay)
# 主号被限制群组发言时，自动用小号代发

import asyncio
import re

__plugin__ = {
    "name": "代发助手",
    "id": "msg_relay",
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "主号被限制群组发言时，自动用小号代发。私聊中直接发消息即可转发到群组",
    "scope": "user",
    "default_enabled": True,
    "config_schema": {
        "default_chat": {
            "type": "chat", "default": "", "label": "目标群组",
            "section": "基本", "chat_types": ["group", "supergroup"],
            "help": "私聊消息将自动转发到此群组"
        },
        "retry_on_banned": {
            "type": "boolean", "default": True, "label": "被限制时自动切换小号",
            "section": "基本",
            "help": "主号发送失败时自动用小号重试"
        },
        "notify_result": {
            "type": "boolean", "default": True, "label": "通知发送结果",
            "section": "基本",
            "help": "发送成功或失败时在私聊中通知"
        },
        "cmd_prefix": {
            "type": "string", "default": "//", "label": "跳过前缀",
            "section": "基本",
            "help": "以此前缀开头的消息不会转发，用于发送普通私聊命令"
        },
    },
}


async def _send_with_fallback(ctx, chat_id, content):
    """尝试用主号发送，失败时自动切换小号"""
    apps = list(ctx.user_apps or [])
    if not apps:
        return {"ok": False, "error": "没有可用的用户账号"}
    primary = apps[0]
    fallbacks = apps[1:] if len(apps) > 1 else []

    # 尝试主号
    if primary:
        try:
            await primary.send(chat_id, content)
            return {"ok": True, "account": "主号"}
        except Exception as e:
            err_str = str(e)
            is_banned = "USER_BANNED_IN_CHANNEL" in err_str or "user is restricted" in err_str.lower()
            if not is_banned or not ctx.config.get("retry_on_banned", True):
                return {"ok": False, "error": f"主号发送失败: {e}"}

    # 主号被限制，尝试小号
    for fb in fallbacks:
        try:
            await fb.send(chat_id, content)
            return {"ok": True, "account": "小号"}
        except Exception:
            continue

    return {"ok": False, "error": "所有账号都无法发送"}


async def setup(ctx):
    ctx.log.info("代发助手已加载")

    @ctx.on_message(ctx.filters.text & ~ctx.filters.outgoing & ctx.filters.private, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # 帮助
        if text in (".help", "/help", "帮助"):
            await message.reply(
                "📦 <b>代发助手</b>\n\n"
                "私聊中直接发消息，自动转发到目标群组。\n"
                "主号被限制时自动切换小号发送。\n\n"
                "📌 <b>用法：</b>\n"
                "  直接发消息 → 转发到配置的群组\n"
                f"  <code>{ctx.config.get('cmd_prefix', '//')}</code>消息 → 跳过转发，普通私聊\n\n"
                "💡 在插件配置中设置目标群组"
            )
            return

        # 检查是否跳过转发（以配置的前缀开头）
        prefix = ctx.config.get("cmd_prefix", "//")
        if text.startswith(prefix):
            return

        # 获取目标群组
        default_chat = ctx.config.get("default_chat", "")
        if not default_chat:
            await message.reply("❌ 请先在插件配置中设置目标群组")
            return

        try:
            chat_id = int(default_chat)
        except (ValueError, TypeError):
            await message.reply("❌ 目标群组配置无效")
            return

        # 发送消息（自动主号→小号切换）
        result = await _send_with_fallback(ctx, chat_id, text)

        # 通知结果
        if ctx.config.get("notify_result", True):
            if result["ok"]:
                who = result.get("account", "小号")
                await message.reply(f"✅ 已通过{who}发送")
            else:
                await message.reply(f"❌ {result.get('error', '发送失败')}")

    ctx.log.info("代发助手已就绪")


async def teardown(ctx):
    pass