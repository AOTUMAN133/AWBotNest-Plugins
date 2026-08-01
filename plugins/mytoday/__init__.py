# -*- coding: utf-8 -*-
# AWBotNest 插件：历史上的今天 (mytoday)

import asyncio
import httpx
import json
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "历史上的今天",
    "id": "mytoday",
    "version": "1.0.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mytoday_v1.svg",
    "author": "凹凸曼",
    "description": "查看历史上的今天大事记。.jt 查看今天发生的历史事件，支持定时推送。",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["httpx"],
    "config_schema": {
        "count": {
            "type": "number", "default": 8, "label": "显示条数",
            "section": "基本", "min": 3, "max": 20, "order": 1,
            "help": "每次显示的历史事件数量"
        },
        "auto_push": {
            "type": "boolean", "default": False, "label": "定时推送",
            "section": "定时", "order": 1,
            "help": "开启后每天早上推送历史上的今天"
        },
        "push_hour": {
            "type": "number", "default": 8, "label": "推送时间(小时)",
            "section": "定时", "min": 0, "max": 23, "order": 2,
        },
        "push_minute": {
            "type": "number", "default": 30, "label": "推送时间(分钟)",
            "section": "定时", "min": 0, "max": 59, "order": 3,
        },
    },
}

_KV_LOGS = "mytoday_logs"
_WIKI_HEADERS = {
    "User-Agent": "AWBotNest/1.0 (MyToday Plugin; +https://github.com/AOTUMAN133/AWBotNest-Plugins)",
    "Accept": "application/json",
}


def _log(ctx, msg: str):
    ctx.log.info("[历史上的今天] %s", msg)
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-30:])


async def _today_events(count: int = 8) -> list:
    """从中文Wikipedia获取历史上的今天事件"""
    month = datetime.now(TZ).month
    day = datetime.now(TZ).day
    url = f"https://zh.wikipedia.org/api/rest_v1/feed/onthisday/events/{month:02d}/{day:02d}"
    async with httpx.AsyncClient(timeout=10, headers=_WIKI_HEADERS) as cli:
        r = await cli.get(url)
        if r.status_code != 200:
            return []
        data = r.json()
        events = data.get("events", [])
        return [{
            "year": e.get("year", "?"),
            "text": e.get("text", "?"),
        } for e in events[:count]]


def _format_events(items: list) -> str:
    """格式化历史事件列表"""
    if not items:
        return "❌ 暂无历史上的今天数据"
    today = datetime.now(TZ)
    lines = [f"📜 <b>历史上的今天</b>  {today.month}月{today.day}日\n"]
    for i, item in enumerate(items, 1):
        year = item["year"]
        text = item["text"]
        lines.append(f"<b>{i}.</b> [{year}年] {text[:120]}")
    lines.append(f"\n📖 来源: 维基百科")
    return "\n".join(lines)


async def setup(ctx):
    _log(ctx, "历史上的今天插件已加载")

    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # .jt — 查看历史上的今天
        if text == ".jt":
            await _show_today(ctx, client, message)
            return

    async def _show_today(ctx, client, message):
        msg = await message.reply(f"⏳ 正在查阅历史上的今天...")
        try:
            await message.delete()
        except Exception:
            pass

        try:
            count = ctx.config.get("count", 8)
            events = await _today_events(count)
            formatted = _format_events(events)
            await msg.edit(formatted)
        except Exception as e:
            await msg.edit(f"❌ 获取失败: {e}")
            _log(ctx, f"获取历史事件失败: {e}")

    # ── 定时推送 ──
    async def _push_today():
        try:
            events = await _today_events(8)
            formatted = _format_events(events)
            await ctx.send_message(formatted)
            _log(ctx, "定时推送历史上的今天完成")
        except Exception as e:
            _log(ctx, f"定时推送失败: {e}")

    if ctx.config.get("auto_push", False):
        hour = ctx.config.get("push_hour", 8)
        minute = ctx.config.get("push_minute", 30)
        ctx.schedule("today_push", _push_today, "cron", hour=hour, minute=minute)
        _log(ctx, f"已注册定时推送: 每天 {hour:02d}:{minute:02d}")

    @ctx.action("test_today")
    async def _test_today(req=None):
        events = await _today_events(5)
        return {"ok": True, "message": f"获取成功: {len(events)} 条，首条: {events[0]['year']}年-{events[0]['text'][:50]}" if events else "获取失败"}

    @ctx.action("view_logs")
    async def _view_logs(req=None):
        logs = ctx.kv.get(_KV_LOGS, [])
        if not logs:
            return {"ok": True, "message": "暂无日志"}
        lines = ["📋 最近日志:\n"]
        for log in logs[-15:]:
            lines.append(f"[{log['t']}] {log['m']}")
        return {"ok": True, "message": "\n".join(lines)}

    ctx.log.info("[历史上的今天] 已就绪")


async def teardown(ctx):
    ctx.log.info("[历史上的今天] 已卸载")