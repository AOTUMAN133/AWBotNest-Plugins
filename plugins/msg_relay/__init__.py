# -*- coding: utf-8 -*-
# AWBotNest 插件：代发助手 (msg_relay)
# 主号被限制群组发言时，自动用小号重发

import asyncio
import re

__plugin__ = {
    "name": "代发助手",
    "id": "msg_relay",
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "主号被限制群组发言时，自动用小号代发。用法：私聊发送 .s 消息内容",
    "scope": "user",
    "default_enabled": True,
    "config_schema": {
        "default_chat": {
            "type": "chat", "default": "", "label": "目标群组",
            "section": "基本", "chat_types": ["group", "supergroup"],
            "help": "消息将发送到此群组"
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
    },
}


async def _send_with_fallback(ctx, message, chat_id, content):
    """尝试用主号发送，失败时自动切换小号"""
    apps = list(ctx.user_apps or [])
    primary = apps[0] if apps else None
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
        except Exception as e:
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
        if text in (".help", ".s", "/help"):
            await message.reply(
                "📦 <b>代发助手</b>\n\n"
                "主号被限制群组发言时，自动用小号重发。\n\n"
                "📌 <b>用法：</b>\n"
                "  .s 消息内容  — 发到默认群组（先在配置中设置目标群组）\n"
                "  .s 群组名 消息内容  — 发到指定群组\n\n"
                "💡 插件会自动先用主号发送，被限制时切换小号"
            )
            return

        # 解析 .s 命令
        m = re.match(r"^\.s\s+(.+?)\s+(.+)$", text)
        if not m:
            m = re.match(r"^\.s\s+(.+)$", text)
            if m:
                target_name = None
                content = m.group(1)
            else:
                return
        else:
            target_name = m.group(1).strip()
            content = m.group(2).strip()

        if not content:
            await message.reply("❌ 消息内容不能为空")
            return

        # 获取目标群组
        chat_id = None
        if target_name:
            async for d in client.get_dialogs():
                if d.chat.title and target_name.lower() in d.chat.title.lower():
                    chat_id = d.chat.id
                    break
            if not chat_id:
                await message.reply(f"❌ 未找到群组「{target_name}」")
                return
        else:
            default_chat = ctx.config.get("default_chat", "")
            if default_chat:
                try:
                    chat_id = int(default_chat)
                except (ValueError, TypeError):
                    await message.reply("❌ 默认群组配置无效")
                    return
            else:
                await message.reply("❌ 请指定群组名或在配置中设置默认群组")
                return

        # 发送消息（自动主号→小号切换）
        result = await _send_with_fallback(ctx, message, chat_id, content)

        # 通知结果
        if ctx.config.get("notify_result", True):
            if result["ok"]:
                who = result.get("account", "小号")
                await message.reply(f"✅ 已通过{who}发送到群组")
            else:
                await message.reply(f"❌ {result.get('error', '发送失败')}")

    ctx.log.info("代发助手已就绪")


async def teardown(ctx):
    pass