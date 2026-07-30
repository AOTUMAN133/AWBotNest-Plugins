# -*- coding: utf-8 -*-
# AWBotNest 插件：用户监控 (usermonitor)

import asyncio, json, random, re, time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "用户监控",
    "id": "usermonitor",
    "version": "1.1.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/assets/icons/usermonitor.svg",
    "author": "凹凸曼",
    "description": "监控指定用户在指定群组的发言，自动回复。支持AI智能回复或固定回复。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
    "config_schema": {
        "monitor_enabled": {
            "type": "boolean", "default": False, "label": "开启监控",
            "section": "基本"
        },
        "use_ai": {
            "type": "boolean", "default": True, "label": "AI智能回复",
            "section": "基本", "help": "开启后使用AI自动生成回复，关闭则使用固定回复"
        },
        "monitor_config": {
            "type": "text", "default": "[]", "label": "监控规则(JSON)",
            "section": "基本", "help": "JSON数组，每条规则格式见文档"
        },
    },
}

_KV_STATE = "monitor_state"

_MONITOR_PROMPT = (
    "你是一个群聊监控助手。以下是一条用户消息，请根据上下文自然回复。\n"
    "回复要简短自然（20-50字），像真人聊天一样。\n"
    "不要自我介绍，不要加引号，不要用AI用语。\n"
    "直接输出回复内容。"
)


def _parse_ids(raw: str) -> list[int]:
    out = []
    for c in str(raw or "").replace("\n", ",").split(","):
        c = c.strip()
        if c:
            try:
                out.append(int(c))
            except ValueError:
                pass
    return out


async def setup(ctx):
    ctx.log.info("用户监控插件已加载")

    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=4)
    async def _monitor_handler(client, message):
        if not ctx.config.get("monitor_enabled", False):
            return
        raw = str(ctx.config.get("monitor_config", "[]") or "").strip()
        try:
            rules = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
        except Exception:
            return
        if not rules:
            return

        chat_id = message.chat.id
        sender_id = str(message.from_user.id) if message.from_user else ""
        if not sender_id:
            return
        text = (message.text or "").strip()
        if not text:
            return

        # 找匹配的规则
        rule = None
        for r in rules:
            r_chats = _parse_ids(r.get("chat_ids", ""))
            r_users = [str(x.strip()) for x in str(r.get("user_ids", "") or "").replace("，", ",").split(",") if x.strip()]
            if chat_id in r_chats and sender_id in r_users:
                rule = r
                break
        if not rule:
            return

        first_reply = str(rule.get("first_reply", "") or "").strip()
        triggers = rule.get("triggers", []) or []
        use_ai = ctx.config.get("use_ai", True)

        state = ctx.kv.get(_KV_STATE, {})
        key = f"{sender_id}:{chat_id}"
        st = state.get(key, {})

        # 检查是否超过重置时间
        reset_hours = int(rule.get("reset_hours", 0) or 0)
        if reset_hours > 0 and st:
            last_time = st.get("time", 0)
            if time.time() - last_time > reset_hours * 3600:
                st = {}
                state[key] = st

        if not st:
            if not first_reply and not use_ai:
                return
            await asyncio.sleep(random.uniform(2, 5))
            if use_ai:
                try:
                    reply = await ctx.ai.chat(f"{_MONITOR_PROMPT}\n\n消息: {text}")
                    reply = reply.strip()[:100]
                    if reply:
                        await client.send_message(chat_id, reply)
                except Exception as e:
                    if first_reply:
                        await client.send_message(chat_id, first_reply)
            else:
                await client.send_message(chat_id, first_reply)
            state[key] = {"stage": 1, "used": [], "time": time.time()}
            ctx.kv.set(_KV_STATE, state)
            return

        # 后续消息，检查关键词
        used = st.get("used", [])
        for ti, tr in enumerate(triggers):
            if ti in used:
                continue
            kws = str(tr.get("keywords", "") or tr.get("keyword", "") or "").strip()
            if not kws:
                continue
            kw_list = [k.strip() for k in kws.replace("，", ",").split(",") if k.strip()]
            matched_kw = None
            for kw in kw_list:
                if kw and kw in text:
                    matched_kw = kw
                    break
            if not matched_kw:
                continue
            replies_raw = str(tr.get("replies", "") or tr.get("reply", "") or "").strip()
            if not replies_raw:
                continue
            reply_list = [r.strip() for r in replies_raw.replace("，", ",").split(",") if r.strip()]
            if not reply_list:
                continue

            await asyncio.sleep(random.uniform(2, 5))
            if use_ai:
                try:
                    reply = await ctx.ai.chat(f"{_MONITOR_PROMPT}\n\n用户说: {text}\n回复提示: {random.choice(reply_list)}")
                    reply = reply.strip()[:100]
                    if reply:
                        await client.send_message(chat_id, reply)
                except Exception:
                    await client.send_message(chat_id, random.choice(reply_list))
            else:
                await client.send_message(chat_id, random.choice(reply_list))
            used.append(ti)
            state[key] = {"stage": st.get("stage", 1) + 1, "used": used, "time": time.time()}
            ctx.kv.set(_KV_STATE, state)
            return

    @ctx.on_api("/reset_monitor", methods=["POST"])
    async def _api_reset_monitor(req):
        body = req.json if hasattr(req, 'json') else {}
        if not body:
            body = {}
        sender_id = body.get("user_id", "")
        chat_id = body.get("chat_id", "")
        if not sender_id or not chat_id:
            return {"ok": False, "message": "需要user_id和chat_id"}
        state = ctx.kv.get(_KV_STATE, {})
        key = f"{sender_id}:{chat_id}"
        if key in state:
            del state[key]
            ctx.kv.set(_KV_STATE, state)
            return {"ok": True, "message": "已重置"}
        return {"ok": False, "message": "未找到该用户状态"}

    @ctx.action("reset_all")
    async def _reset_all(req=None):
        ctx.kv.set(_KV_STATE, {})
        return {"ok": True, "message": "所有监控状态已重置"}

    @ctx.on_api("/get_rules", methods=["GET"])
    async def _api_get_rules(req):
        raw = str(ctx.config.get("monitor_config", "[]") or "").strip()
        try:
            rules = json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, list) else [])
        except Exception:
            rules = []
        return {"ok": True, "rules": rules}

    @ctx.on_api("/save_rules", methods=["POST"])
    async def _api_save_rules(req):
        try:
            body = req.json if hasattr(req, 'json') else {}
            rules = body.get("rules", []) if isinstance(body, dict) else []
            ctx.update_config({"monitor_config": json.dumps(rules, ensure_ascii=False)})
            return {"ok": True, "message": "已保存"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    ctx.log.info("用户监控已就绪")


async def teardown(ctx):
    ctx.log.info("用户监控已卸载")