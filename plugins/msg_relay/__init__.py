# -*- coding: utf-8 -*-
# AWBotNest 插件：代发助手 (msg_relay)
# 检测主号草稿 → 自动用小号发送

import asyncio
import json
import time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "代发助手",
    "id": "msg_relay",
    "version": "1.2.0",
    "author": "凹凸曼",
    "description": "检测主号在群组的未发送草稿，自动用小号代发。你在群里打字就能发。",
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
            "help": "主号（被限制发言的那个）"
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
        "check_interval": {
            "type": "number", "default": 10, "label": "检测间隔(秒)",
            "section": "基本", "min": 5, "max": 60,
            "help": "每隔几秒检测一次草稿，越短响应越快但越耗资源（建议10秒以上）"
        },
        "notify_result": {
            "type": "boolean", "default": True, "label": "通知发送结果",
            "section": "基本",
            "help": "发送成功或失败时通知"
        },
        "status_info": {
            "type": "info", "label": "运行状态", "section": "状态"
        },
    },
}

_KV_LOGS = "msg_relay_logs"
_KV_STATUS = "msg_relay_status"
_client_ref = None
_client_info = {}
_running = False


def _log(ctx, msg: str):
    ts = datetime.now(TZ).strftime("%H:%M:%S")
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": ts, "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-50:])
    ctx.update_config({"status_info": f"最后: {msg[:30]}"})


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
    return apps[main_idx], (apps[fallback_idx] if fallback_idx < len(apps) else None), None


async def _send_with_fallback(ctx, chat_id, content):
    main_acc, fb_acc, err = await _get_accounts(ctx)
    if err:
        return {"ok": False, "error": err}
    if main_acc:
        try:
            await main_acc.send(chat_id, content)
            return {"ok": True, "account": "主号"}
        except Exception as e:
            if "USER_BANNED_IN_CHANNEL" not in str(e):
                return {"ok": False, "error": str(e)}
    if fb_acc:
        try:
            await fb_acc.send(chat_id, content)
            return {"ok": True, "account": "小号"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "没有可用账号"}


async def setup(ctx):
    global _client_ref, _running
    ctx.log.info("代发助手已加载")

    # 获取 client 引用
    @ctx.on_message(ctx.filters.text, group=999)
    async def _store_client(client, message):
        global _client_ref, _client_info
        try:
            me = await client.get_me()
            if not me:
                return
            # 判断这个客户端是哪个账号
            try:
                main_idx = int(ctx.config.get("main_account_index", 0))
            except (ValueError, TypeError):
                main_idx = 0
            apps = list(ctx.user_apps or [])
            # 通过 get_me 比对，判断当前client是否为主号
            is_main = False
            if main_idx < len(apps):
                try:
                    app_me = await apps[main_idx].get_me()
                    if app_me and app_me.id == me.id:
                        is_main = True
                except Exception:
                    pass
            # 只存储主号的客户端
            if is_main and _client_ref is None:
                _client_ref = client
                _client_info = {
                    "id": me.id, "name": me.first_name or "",
                    "phone": me.phone_number or "", "username": me.username or "",
                }
                ctx.update_config({"status_info": f"✅ 主号: {me.first_name} | {me.phone_number or me.id}"})
                _log(ctx, f"✅ 已连接主号: {me.first_name}")
        except Exception:
            pass

    # 账号信息 API
    @ctx.on_api("/get_accounts_info", methods=["GET"])
    async def _api_accounts_info(req):
        apps = list(ctx.user_apps or [])
        result = []
        for i, app in enumerate(apps):
            info = {"index": i, "label": f"第{i+1}个账号"}
            try:
                if hasattr(app, 'get_me'):
                    me = await app.get_me()
                    if me:
                        info["name"] = me.first_name or ""
                        info["phone"] = me.phone_number or ""
                        info["id"] = me.id
            except Exception:
                pass
            result.append(info)
        return {"accounts": result}

    # 日志 API
    @ctx.on_api("/get_logs", methods=["GET"])
    async def _api_get_logs(req):
        return {"logs": ctx.kv.get(_KV_LOGS, [])}

    # 定时检测草稿
    async def _draft_check():
        global _client_ref, _running
        if _running:
            return
        _running = True
        try:
            # 尝试从 ctx.user_apps 获取主号客户端
            apps = list(ctx.user_apps or [])
            cli = None
            try:
                main_idx = int(ctx.config.get("main_account_index", 0))
            except (ValueError, TypeError):
                main_idx = 0
            if main_idx < len(apps) and hasattr(apps[main_idx], 'get_dialogs'):
                cli = apps[main_idx]
            if not cli:
                cli = _client_ref
            if not cli:
                return

            drafts_found = 0
            async for d in cli.get_dialogs(limit=30):
                if d.chat.type not in ("group", "supergroup", "channel"):
                    continue
                try:
                    if not (hasattr(d.raw, 'draft') and d.raw.draft):
                        continue
                    if not (hasattr(d.raw.draft, 'message') and d.raw.draft.message):
                        continue
                    content = d.raw.draft.message
                    title = d.chat.title or "未知"
                    _log(ctx, f"📝 {title}: {content[:30]}...")

                    result = await _send_with_fallback(ctx, d.chat.id, content)
                    if result["ok"]:
                        who = result.get("account", "小号")
                        try:
                            from pyrogram.raw.functions.messages import SaveDraft
                            peer = await cli.resolve_peer(d.chat.id)
                            await cli.invoke(SaveDraft(peer=peer, message=''))
                        except Exception:
                            pass
                        _log(ctx, f"✅ {title}: 已通过{who}发送")
                        if ctx.config.get("notify_result", True):
                            await ctx.notify(f"📨 {title}\n✅ 已通过{who}发送\n📝 {content[:80]}")
                        drafts_found += 1
                    else:
                        _log(ctx, f"❌ {title}: {result.get('error','')}")
                    if drafts_found >= 3:
                        break
                except Exception:
                    pass

        except Exception as e:
            _log(ctx, f"❌ {e}")
        finally:
            _running = False

    interval = int(ctx.config.get("check_interval", 5) or 5)
    ctx.schedule(_draft_check, "interval", seconds=interval, id="代发助手-草稿检测")
    _log(ctx, f"🚀 启动完成，间隔{interval}秒")

    @ctx.on_message(ctx.filters.text & ~ctx.filters.outgoing & ctx.filters.private, group=0)
    async def _help_handler(client, message):
        text = (message.text or "").strip()
        if text in (".help", "/help", "帮助"):
            await message.reply(
                "📦 <b>代发助手 (草稿模式)</b>\n\n"
                "你在群里打字发不出去？插件自动检测草稿，用小号代发。\n\n"
                "📌 <b>用法：</b>\n"
                "  1. 打开任意群组\n"
                "  2. 正常打字，点发送\n"
                "  3. 发不出去 → Telegram 自动保存为草稿\n"
                "  4. 插件检测到草稿 → 用小号发到群里\n\n"
                "📌 <b>命令：</b>\n"
                "  .whoami  — 查看当前账号信息\n"
                "  .logs    — 查看最近日志\n\n"
                "⚙️ 可在插件配置中调整检测间隔和账号"
            )
            return

        if text == ".whoami":
            global _client_info
            apps = list(ctx.user_apps or [])
            lines = ["📋 <b>账号信息</b>\n"]
            for i, app in enumerate(apps):
                info = f"第{i+1}个账号 (index={i})"
                try:
                    if hasattr(app, 'get_me'):
                        me = await app.get_me()
                        if me:
                            info += f": {me.first_name or ''} ({me.phone_number or me.id})"
                except Exception:
                    pass
                lines.append(f"  {info}")
            lines.append(f"\n在配置中选择:\n主号 = 第1个账号 (index=0)\n备用号 = 第2个账号 (index=1)")
            await message.reply("\n".join(lines))
            return

        if text == ".scan":
            _log(ctx, "🔍 手动触发草稿扫描...")
            asyncio.create_task(_draft_check())
            await message.reply("🔍 已开始扫描草稿，稍后查看 .logs")
            return

        if text == ".logs":
            if not ctx.kv:
                await message.reply("❌ KV不可用")
                return
            logs = ctx.kv.get(_KV_LOGS, [])
            if not logs:
                # 尝试检查是否有日志被写入
                test_key = f"{_KV_LOGS}_test"
                ctx.kv.set(test_key, "ok")
                test_val = ctx.kv.get(test_key, "")
                await message.reply(f"暂无日志 (KV测试: {test_val})")
                return
            lines = ["📋 <b>最近日志</b>\n"]
            for log in logs[-20:]:
                lines.append(f"[{log['t']}] {log['m']}")
            await message.reply("\n".join(lines))
            return

    ctx.log.info("代发助手已就绪")


async def teardown(ctx):
    global _client_ref, _running
    _client_ref = None
    _running = False