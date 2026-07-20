# -*- coding: utf-8 -*-
# AWBotNest 插件：私聊拦截 (mypmcaptcha)

import asyncio
import random
import time
from datetime import datetime, timezone, timedelta
import pyrogram
from pyrogram.raw.functions.account import UpdateNotifySettings, ReportPeer
from pyrogram.raw.functions.contacts import Block
from pyrogram.raw.functions.folders import EditPeerFolders
from pyrogram.raw.functions.messages import DeleteHistory
from pyrogram.raw.types import InputNotifyPeer, InputPeerNotifySettings, InputFolderPeer, InputReportReasonSpam

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "私聊拦截",
    "id": "mypmcaptcha",
    "version": "1.0.2",
    "author": "凹凸曼",
    "description": "陌生人私聊时自动发送验证题，通过后放行，失败后执行屏蔽/举报等操作。",
    "scope": "user",
    "requirements": [],
    "config_schema": {
        "enabled": {
            "type": "boolean", "default": True, "label": "启用插件",
            "section": "基础", "help": "关闭后不拦截私聊"
        },
        "captcha_enabled": {
            "type": "boolean", "default": True, "label": "开启验证",
            "section": "验证", "help": "关闭后静默等待（不发验证题）"
        },
        "captcha_mode": {
            "type": "select", "default": "math", "label": "验证模式",
            "section": "验证",
            "options": {"math": "算术验证", "text": "关键词验证"}
        },
        "captcha_timeout": {
            "type": "number", "default": 30, "label": "超时(秒)",
            "section": "验证", "help": "0=不限时"
        },
        "captcha_tries": {
            "type": "number", "default": 3, "label": "最大尝试次数",
            "section": "验证", "help": "0=不限次"
        },
        "captcha_keyword": {
            "type": "string", "default": "我同意", "label": "关键词",
            "section": "验证", "help": "text模式要求对方回复的关键词"
        },
        "fail_actions": {
            "type": "string", "default": "屏蔽,举报", "label": "失败操作",
            "section": "操作", "help": "屏蔽=block, 删除对话=delete, 举报=report, 静音=mute, 归档=archive, 逗号分隔"
        },
        "pass_actions": {
            "type": "string", "default": "取消静音,取消归档", "label": "通过操作",
            "section": "操作", "help": "取消静音=unmute, 取消归档=unarchive, 白名单=wl, 逗号分隔"
        },
        "whitelist": {
            "type": "string", "default": "", "label": "白名单(用户ID逗号分隔)",
            "section": "白名单"
        },
        "_stats": {
            "type": "info", "label": "统计",
            "section": "统计"
        },
    },
}

DEFAULTS = {
    "enabled": True,
    "captcha_enabled": True,
    "captcha_mode": "math",
    "captcha_timeout": 30,
    "captcha_tries": 3,
    "captcha_keyword": "我同意",
    "fail_actions": "屏蔽,举报",
    "pass_actions": "取消静音,取消归档",
    "whitelist": "",
}

# 正在验证中的用户状态
# { user_id: {"question": str, "answer": str, "tries": int, "msg_id": int, "task": asyncio.Task} }
_pending = {}

# 验证记录（存 ctx.kv）
_KV_VERIFIED = "mypm_verified"
_KV_FAILED = "mypm_failed"
_KV_WHITELIST = "mypm_whitelist"


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _parse_ids(s: str) -> set:
    return set(int(x.strip()) for x in s.split(",") if x.strip().isdigit())


_ACTION_CN_TO_EN = {
    "屏蔽": "block", "删除": "delete", "删除对话": "delete",
    "举报": "report", "静音": "mute", "归档": "archive",
    "取消静音": "unmute", "取消归档": "unarchive", "白名单": "wl",
}

_ACTION_EN_TO_CN = {
    "block": "屏蔽", "delete": "删除对话", "report": "举报",
    "mute": "静音", "archive": "归档",
    "unmute": "取消静音", "unarchive": "取消归档", "wl": "白名单",
}


def _parse_actions(s: str) -> list:
    """解析操作配置，支持中文和英文，返回英文code列表"""
    items = [x.strip() for x in s.split(",") if x.strip()]
    result = []
    for item in items:
        lower = item.lower()
        if lower in _ACTION_CN_TO_EN:
            result.append(_ACTION_CN_TO_EN[lower])
        elif lower in _ACTION_EN_TO_CN:
            result.append(lower)
        else:
            result.append(item)
    return result


def _is_whitelisted(ctx, user_id: int) -> bool:
    raw = ctx.config.get("whitelist", "") or ctx.kv.get(_KV_WHITELIST, "") or ""
    return user_id in _parse_ids(raw)


def _add_whitelist(ctx, user_id: int):
    raw = ctx.config.get("whitelist", "") or ctx.kv.get(_KV_WHITELIST, "") or ""
    ids = _parse_ids(raw)
    ids.add(user_id)
    new = ",".join(str(x) for x in sorted(ids))
    ctx.kv.set(_KV_WHITELIST, new)
    ctx.update_config({"whitelist": new})


def _del_whitelist(ctx, user_id: int):
    raw = ctx.config.get("whitelist", "") or ctx.kv.get(_KV_WHITELIST, "") or ""
    ids = _parse_ids(raw)
    ids.discard(user_id)
    new = ",".join(str(x) for x in sorted(ids))
    ctx.kv.set(_KV_WHITELIST, new)
    ctx.update_config({"whitelist": new})


# ─── 数学题生成 ────────────────────────────────────────────────────────────────


def _gen_math_question() -> tuple:
    """生成简单数学题"""
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    op = random.choice(["+", "-"])
    if op == "+":
        ans = a + b
    else:
        if a < b:
            a, b = b, a
        ans = a - b
    return f"{a} {op} {b} = ?", str(ans)


# ─── 关键词题库 ────────────────────────────────────────────────────────────────

_QUESTIONS = [
    ("1+1等于几？", "2"),
    ("一年有几个月？", "12"),
    ("一周有几天？", "7"),
    ("太阳从哪边升起？", "东"),
    ("中国的首都是哪里？", "北京"),
    ("水的化学式是什么？", "H2O"),
    ("地球有几大洲？", "7"),
    ("一天有几个小时？", "24"),
    ("1米等于多少厘米？", "100"),
    ("2+3等于几？", "5"),
]


def _gen_text_question(keyword: str) -> tuple:
    """生成关键词验证题"""
    if keyword and keyword != "我同意":
        return (f"请回复以下关键词以证明你不是机器人：\n\n{keyword}", keyword)
    q, a = random.choice(_QUESTIONS)
    return (q, a)


# ─── 发送验证题 ────────────────────────────────────────────────────────────────


async def _send_captcha(client, cfg, user_id, ctx):
    """发送验证题给用户"""
    mode = cfg.get("captcha_mode", "math")
    timeout = int(cfg.get("captcha_timeout", 30) or 30)
    tries = int(cfg.get("captcha_tries", 3) or 3)
    keyword = cfg.get("captcha_keyword", "我同意")
    fail_acts = _parse_actions(cfg.get("fail_actions", "block,report"))
    pass_acts = _parse_actions(cfg.get("pass_actions", "unmute,unarchive"))

    mode_label = {"math": "算术验证", "text": "关键词验证"}.get(mode, mode)
    fail_label = {"block": "屏蔽", "delete": "删除对话", "report": "举报",
                   "mute": "静音", "archive": "归档"}

    if mode == "text":
        question, answer = _gen_text_question(keyword)
    else:
        question, answer = _gen_math_question()

    fail_str = "、".join(fail_label.get(a, a) for a in fail_acts) if fail_acts else "静音+归档"

    text = (
        f"🔒 人机验证\n\n"
        f"请回答以下问题：\n\n"
        f"{question}\n\n"
        f"⏱ 验证时间：{timeout if timeout > 0 else '不限'} 秒\n"
        f"🔢 剩余次数：{tries if tries > 0 else '不限'} 次\n"
        f"⚠️ 验证失败将会：{fail_str}"
    )

    try:
        msg = await client.send_message(user_id, text)
        msg_id = msg.id if hasattr(msg, 'id') else 0
    except Exception as e:
        ctx.log.warning("[人机验证] 发送验证题失败 %d: %r", user_id, e)
        return

    # 取消旧定时器
    old = _pending.get(user_id)
    if old:
        old.get("task", None) and old["task"].cancel()

    # 创建超时任务
    async def _timeout_task():
        if timeout <= 0:
            return
        await asyncio.sleep(timeout)
        st = _pending.get(user_id)
        if st and st.get("msg_id") == msg_id:
            await _fail(client, user_id, ctx, "timeout")

    task = asyncio.create_task(_timeout_task())

    _pending[user_id] = {
        "question": question,
        "answer": answer.lower().strip(),
        "tries": tries,
        "msg_id": msg_id,
        "task": task,
        "start": time.time(),
    }


# ─── 验证通过/失败 ─────────────────────────────────────────────────────────────


async def _pass(client, user_id, ctx):
    """验证通过"""
    _pending.pop(user_id, None)
    cfg = ctx.config
    pass_acts = _parse_actions(cfg.get("pass_actions", "unmute,unarchive"))

    for act in pass_acts:
        if act == "unmute":
            try:
                await client.invoke(pyrogram.raw.functions.account.UpdateNotifySettings(
                        peer=pyrogram.raw.types.InputNotifyPeer(peer=await client.resolve_peer(user_id)),
                        settings=pyrogram.raw.types.InputPeerNotifySettings(mute_until=0, show_previews=True, silent=False)))
            except Exception as e:
                ctx.log.warning("[人机验证] 取消静音失败 %d: %r", user_id, e)
        elif act == "unarchive":
            try:
                await client.invoke(pyrogram.raw.functions.folders.EditPeerFolders(
                        folder_peers=[pyrogram.raw.types.InputFolderPeer(
                            peer=await client.resolve_peer(user_id), folder_id=0)]))
            except Exception as e:
                ctx.log.warning("[人机验证] 取消归档失败 %d: %r", user_id, e)
        elif act == "wl":
            _add_whitelist(ctx, user_id)

    # 记录通过
    try:
        me = await client.get_me()
        my_name = me.first_name or str(me.id)
    except Exception:
        my_name = str(user_id)
    try:
        u = await client.get_users(user_id)
        name = u.first_name or str(user_id)
        uname = u.username or ""
    except Exception:
        name = str(user_id)
        uname = ""

    verified = _get_records(ctx, _KV_VERIFIED)
    entry = {"id": user_id, "name": name, "username": uname, "time": _now()}
    verified = [e for e in verified if e.get("id") != user_id] + [entry]
    ctx.kv.set(_KV_VERIFIED, verified)

    try:
        await client.send_message(user_id, "✅ 验证通过，欢迎！")
    except Exception:
        pass


async def _fail(client, user_id, ctx, reason: str):
    """验证失败"""
    _pending.pop(user_id, None)
    cfg = ctx.config
    fail_acts = _parse_actions(cfg.get("fail_actions", "block,report"))

    # 默认静音+归档
    try:
        peer = await client.resolve_peer(user_id)
        await client.call({
            '_': 'folders.editPeerFolders',
            'folder_peers': [{'_': 'inputFolderPeer', 'peer': peer, 'folder_id': 1}]
        })
    except Exception:
        pass
    try:
        peer = await client.resolve_peer(user_id)
        await client.call({
            '_': 'account.updateNotifySettings',
            'peer': {'_': 'inputNotifyPeer', 'peer': peer},
            'settings': {'_': 'inputPeerNotifySettings', 'mute_until': 2147483647,
                         'show_previews': False, 'silent': True}
        })
    except Exception:
        pass

    for act in fail_acts:
        if act == "block":
            try:
                await client.invoke(Block(id=await client.resolve_peer(user_id)))
                ctx.log.info("[人机验证] 已屏蔽 %d", user_id)
            except Exception as e:
                ctx.log.warning("[人机验证] 屏蔽失败 %d: %r", user_id, e)
        elif act == "delete":
            try:
                await client.invoke(pyrogram.raw.functions.messages.DeleteHistory(
                        peer=await client.resolve_peer(user_id),
                        revoke=True, max_id=0))
            except Exception as e:
                ctx.log.warning("[人机验证] 删除对话失败 %d: %r", user_id, e)
        elif act == "report":
            try:
                await client.invoke(pyrogram.raw.functions.account.ReportPeer(
                        peer=await client.resolve_peer(user_id),
                        reason=pyrogram.raw.types.InputReportReasonSpam(),
                        message="spam"))
            except Exception as e:
                ctx.log.warning("[人机验证] 举报失败 %d: %r", user_id, e)

    # 记录失败
    try:
        u = await client.get_users(user_id)
        name = u.first_name or str(user_id)
        uname = u.username or ""
    except Exception:
        name = str(user_id)
        uname = ""

    failed = _get_records(ctx, _KV_FAILED)
    entry = {"id": user_id, "name": name, "username": uname,
             "time": _now(), "reason": reason}
    failed = [e for e in failed if e.get("id") != user_id] + [entry]
    ctx.kv.set(_KV_FAILED, failed)

    try:
        rl = {"timeout": "⏰ 超时", "max_tries": "❌ 次数耗尽"}
        await client.send_message(user_id, f"❌ 验证失败（{rl.get(reason, reason)}）")
    except Exception:
        pass


def _get_records(ctx, key: str) -> list:
    raw = ctx.kv.get(key, [])
    if isinstance(raw, list):
        return raw
    return []


async def _update_stats(ctx):
    """更新统计信息"""
    verified = len(_get_records(ctx, _KV_VERIFIED))
    failed = len(_get_records(ctx, _KV_FAILED))
    pending = len(_pending)
    ctx.update_config({"_stats": f"✅通过{verified} ❌失败{failed} ⏳待验证{pending}"})


# ─── 消息处理器 ─────────────────────────────────────────────────────────────────


async def setup(ctx):
    # 定时更新统计
    async def _stats_pusher():
        await _update_stats(ctx)
    ctx.schedule(_stats_pusher, "interval", seconds=30, id="mypm_stats")

    @ctx.on_message(ctx.filters.private & ~ctx.filters.outgoing, group=6)
    async def _pm_handler(client, message):
        if not ctx.config.get("enabled", True):
            return
        user_id = message.from_user.id if message.from_user else 0
        if not user_id:
            return
        # 跳过机器人自己
        if message.from_user and (message.from_user.is_self or message.from_user.is_bot):
            return

        # 检查是否是命令消息
        text = (message.text or "").strip()
        if text.startswith("/") or text.startswith("."):
            return

        # 对方也在用同类插件，互发验证消息时跳过，避免死循环
        if "人机验证" in text or "验证题" in text or "🔒" in text:
            ctx.log.info("[私聊拦截] 对方也在用验证插件，跳过互发验证消息: %d", user_id)
            return

        # 白名单直接放行
        if _is_whitelisted(ctx, user_id):
            return

        # 已通过验证的放行
        verified = _get_records(ctx, _KV_VERIFIED)
        if any(v.get("id") == user_id for v in verified):
            return

        # 正在验证中，检查答案
        st = _pending.get(user_id)
        if st:
            st["tries"] -= 1
            if text.lower().strip() == st["answer"]:
                await _pass(client, user_id, ctx)
                await _update_stats(ctx)
            else:
                if st["tries"] <= 0:
                    await _fail(client, user_id, ctx, "max_tries")
                    await _update_stats(ctx)
                else:
                    remaining = st["tries"]
                    await client.send_message(
                        user_id,
                        f"❌ 答案错误，还剩 {remaining} 次机会"
                    )
            return

        # 首次消息，需要验证
        if not ctx.config.get("captcha_enabled", True):
            # 验证关闭，静默等待
            return

        # 静音+归档
        try:
            peer = await client.resolve_peer(user_id)
            await client.call({
                '_': 'folders.editPeerFolders',
                'folder_peers': [{'_': 'inputFolderPeer', 'peer': peer, 'folder_id': 1}]
            })
        except Exception:
            pass
        try:
            peer = await client.resolve_peer(user_id)
            await client.call({
                '_': 'account.updateNotifySettings',
                'peer': {'_': 'inputNotifyPeer', 'peer': peer},
                'settings': {'_': 'inputPeerNotifySettings', 'mute_until': 2147483647,
                             'show_previews': False, 'silent': True}
            })
        except Exception:
            pass

        await _send_captcha(client, ctx.config, user_id, ctx)
        await _update_stats(ctx)

    @ctx.on_api("/pass_user", methods=["POST"])
    async def _api_pass(req):
        import json
        data = json.loads(req.body) if hasattr(req, 'body') else (req or {})
        uid = int(data.get("user_id", 0))
        if not uid:
            return {"ok": False, "message": "需要user_id"}
        apps = list(ctx.user_apps or [])
        if apps:
            await _pass(apps[0], uid, ctx)
            await _update_stats(ctx)
        return {"ok": True, "message": "已通过"}

    @ctx.on_api("/fail_user", methods=["POST"])
    async def _api_fail(req):
        import json
        data = json.loads(req.body) if hasattr(req, 'body') else (req or {})
        uid = int(data.get("user_id", 0))
        if not uid:
            return {"ok": False, "message": "需要user_id"}
        apps = list(ctx.user_apps or [])
        if apps:
            await _fail(apps[0], uid, ctx, "manual")
            await _update_stats(ctx)
        return {"ok": True, "message": "已执行失败操作"}

    @ctx.on_api("/clear_verified", methods=["POST"])
    async def _api_clear_verified(req):
        ctx.kv.set(_KV_VERIFIED, [])
        await _update_stats(ctx)
        return {"ok": True, "message": "已清空通过记录"}

    @ctx.on_api("/clear_failed", methods=["POST"])
    async def _api_clear_failed(req):
        ctx.kv.set(_KV_FAILED, [])
        await _update_stats(ctx)
        return {"ok": True, "message": "已清空失败记录"}

    @ctx.on_api("/get_records", methods=["GET"])
    async def _api_get_records(req):
        return {
            "verified": _get_records(ctx, _KV_VERIFIED),
            "failed": _get_records(ctx, _KV_FAILED),
            "pending": len(_pending),
        }


async def teardown(ctx):
    # 取消所有待验证
    for uid, st in list(_pending.items()):
        if st.get("task"):
            st["task"].cancel()
    _pending.clear()