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
    "description": "主号被限制群组发言时，自动用小号代发。私聊发消息自动转发到最近活跃的群组。",
    "scope": "user",
    "default_enabled": True,
    "config_schema": {
        "main_account_index": {
            "type": "select", "default": "0", "label": "主号（大号）",
            "section": "账号设置",
            "options": [
                {"value": "0", "label": "第1个账号"},
                {"value": "1", "label": "第2个账号"},
            ],
            "help": "选择哪个账号是主号（被限制的那个）"
        },
        "fallback_account_index": {
            "type": "select", "default": "1", "label": "备用号（小号）",
            "section": "账号设置",
            "options": [
                {"value": "0", "label": "第1个账号"},
                {"value": "1", "label": "第2个账号"},
            ],
            "help": "主号被限制时用哪个账号代发"
        },
        "notify_result": {
            "type": "boolean", "default": True, "label": "通知发送结果",
            "section": "基本",
            "help": "发送成功或失败时通知"
        },
        "cmd_prefix": {
            "type": "string", "default": "//", "label": "跳过前缀",
            "section": "基本",
            "help": "以此前缀开头的消息不转发"
        },
    },
}

_KV_LAST_CHAT = "msg_relay_last_chat"


async def _get_accounts(ctx):
    apps = list(ctx.user_apps or [])
    if not apps:
        return None, None, "没有可用的用户账号"
    try:
        main_idx = int(ctx.config.get("main_account_index", 0))
        fallback_idx = int(ctx.config.get("fallback_account_index", 1))
    except (ValueError, TypeError):
        main_idx, fallback_idx = 0, 1
    if main_idx >= len(apps): main_idx = 0
    if fallback_idx >= len(apps): fallback_idx = 1 if len(apps) > 1 else 0
    if main_idx == fallback_idx:
        fallback_idx = 1 if len(apps) > 1 else 0
    main_acc = apps[main_idx]
    fb_acc = apps[fallback_idx] if fallback_idx < len(apps) else None
    return main_acc, fb_acc, None


async def _send_with_fallback(ctx, chat_id, content):
    main_acc, fb_acc, err = await _get_accounts(ctx)
    if err:
        return {"ok": False, "error": err}
    if main_acc:
        try:
            await main_acc.send(chat_id, content)
            return {"ok": True, "account": "主号"}
        except Exception as e:
            err_str = str(e)
            is_banned = "USER_BANNED_IN_CHANNEL" in err_str or "user is restricted" in err_str.lower()
            if not is_banned:
                return {"ok": False, "error": f"主号发送失败: {e}"}
    if fb_acc:
        try:
            await fb_acc.send(chat_id, content)
            return {"ok": True, "account": "小号"}
        except Exception as e:
            return {"ok": False, "error": f"小号也发送失败: {e}"}
    return {"ok": False, "error": "没有可用的备用账号"}


async def setup(ctx):
    ctx.log.info("代发助手已加载")

    # 跟踪最近活跃的群组
    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=999)
    async def _track_chat(client, message):
        ctx.kv.set(_KV_LAST_CHAT, message.chat.id)

    @ctx.on_message(ctx.filters.text & ~ctx.filters.outgoing & ctx.filters.private, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # 帮助
        if text in (".help", "/help", "帮助"):
            last_chat = ctx.kv.get(_KV_LAST_CHAT, 0)
            last_info = f"chat_id={last_chat}" if last_chat else "暂无"
            await message.reply(
                "📦 <b>代发助手</b>\n\n"
                "私聊中直接发消息，自动转发到最近活跃的群组。\n"
                "主号被限制时自动切换小号发送。\n\n"
                f"📌 <b>当前配置：</b>\n"
                f"  最近活跃群组: {last_info}\n\n"
                f"📌 <b>用法：</b>\n"
                f"  直接发消息 → 转发到最近活跃的群组\n"
                f"  .s 群组名 消息 → 发到指定群组\n"
                f"  {ctx.config.get('cmd_prefix', '//')}消息 → 不转发\n\n"
                f"💡 在插件配置中设置主号和备用号"
            )
            return

        # 跳过前缀
        prefix = ctx.config.get("cmd_prefix", "//")
        if text.startswith(prefix):
            return

        # .s 群组名 消息 → 指定群组
        m = re.match(r"^\.s\s+(.+?)\s+(.+)$", text)
        if m:
            target_name = m.group(1).strip()
            content = m.group(2).strip()
            chat_id = None
            async for d in client.get_dialogs():
                if d.chat.title and target_name.lower() in d.chat.title.lower():
                    chat_id = d.chat.id
                    break
            if not chat_id:
                await message.reply(f"❌ 未找到群组「{target_name}」")
                return
            result = await _send_with_fallback(ctx, chat_id, content)
            if ctx.config.get("notify_result", True):
                if result["ok"]:
                    await message.reply(f"✅ 已通过{result['account']}发送到「{target_name}」")
                else:
                    await message.reply(f"❌ {result['error']}")
            return

        # 直接发消息 → 转发到最近活跃的群组
        last_chat = ctx.kv.get(_KV_LAST_CHAT, 0)
        if not last_chat:
            await message.reply("❌ 还没有活跃的群组，请先在群组中发言或使用 .s 群组名 消息")
            return

        result = await _send_with_fallback(ctx, last_chat, text)
        if ctx.config.get("notify_result", True):
            if result["ok"]:
                await message.reply(f"✅ 已通过{result['account']}发送")
            else:
                await message.reply(f"❌ {result['error']}")

    ctx.log.info("代发助手已就绪")


async def teardown(ctx):
    pass