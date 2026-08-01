# -*- coding: utf-8 -*-
# AWBotNest 插件：热搜热点 (myhot)

import asyncio
import httpx
import json
import time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "热搜热点",
    "id": "myhot",
    "version": "1.1.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/myhot_v1.svg",
    "author": "凹凸曼",
    "description": "查看百度/微博热搜榜。.hot 查看热搜榜，.hot baidu 百度热搜，.hot weibo 微博热搜",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["httpx"],
    "config_schema": {
        "count": {
            "type": "number", "default": 10, "label": "显示条数",
            "section": "基本", "min": 5, "max": 30, "order": 1,
            "help": "每次热搜显示的条数"
        },
        "auto_push": {
            "type": "boolean", "default": False, "label": "定时推送热搜",
            "section": "定时", "order": 1,
            "help": "开启后每天定时推送热搜到群"
        },
        "push_hour": {
            "type": "number", "default": 9, "label": "推送时间(小时)",
            "section": "定时", "min": 0, "max": 23, "order": 2,
            "help": "每天几点推送热搜（0-23）"
        },
        "push_minute": {
            "type": "number", "default": 0, "label": "推送时间(分钟)",
            "section": "定时", "min": 0, "max": 59, "order": 3,
        },
    },
}

_KV_LOGS = "myhot_logs"
_BAIDU_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://top.baidu.com/",
}
_MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
}


def _log(ctx, msg: str):
    ctx.log.info("[热搜热点] %s", msg)
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-30:])


async def _baidu_hot(count: int = 10) -> list:
    """获取百度热搜榜"""
    async with httpx.AsyncClient(timeout=10, headers=_BAIDU_HEADERS) as cli:
        r = await cli.get("https://top.baidu.com/api/board?tab=realtime")
        if r.status_code != 200:
            return []
        data = r.json()
        items = data.get("data", {}).get("cards", [{}])[0].get("content", [])
        return [{
            "word": item.get("word", "?"),
            "hot_score": item.get("hotScore", 0),
            "desc": item.get("desc", ""),
            "url": item.get("appUrl", ""),
        } for item in items[:count]]


async def _weibo_hot(count: int = 10) -> list:
    """从 weibo.cn 获取微博热搜榜"""
    async with httpx.AsyncClient(timeout=10, headers=_MOBILE_HEADERS, follow_redirects=True) as cli:
        r = await cli.get("https://weibo.cn/")
        if r.status_code != 200:
            return []
        import re
        # 提取 <div class="c"><a href="...">话题</a></div> 中的话题
        items = re.findall(r'<div class="c"><a[^>]*>([^<]+)</a></div>', r.text)
        return [{"word": item.strip(), "hot_score": 0} for item in items[:count]]


def _format_hot_list(items: list, source: str) -> str:
    """格式化热搜列表"""
    if not items:
        return f"❌ 暂无{source}热搜数据"
    lines = [f"🔥 <b>{source}热搜榜</b>  {datetime.now(TZ).strftime('%m-%d %H:%M')}\n"]
    for i, item in enumerate(items, 1):
        word = item["word"]
        score = item.get("hot_score", 0)
        score = int(score) if score else 0
        score_str = f" {score//10000}万" if score > 10000 else f" {score}" if score else ""
        lines.append(f"<b>{i}.</b> {word}{score_str}")
    lines.append(f"\n🔄 来源: {source}")
    return "\n".join(lines)


async def setup(ctx):
    _log(ctx, "热搜热点插件已加载")

    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # .hot — 显示百度热搜
        if text == ".hot":
            await _show_hot(ctx, client, message, "baidu")
            return

        # .hot baidu — 百度热搜
        if text == ".hot baidu":
            await _show_hot(ctx, client, message, "baidu")
            return

        # .hot weibo — 微博热搜
        if text == ".hot weibo":
            await _show_hot(ctx, client, message, "weibo")
            return

    async def _show_hot(ctx, client, message, source: str):
        msg = await message.reply(f"⏳ 正在获取{source}热搜...")
        try:
            await message.delete()
        except Exception:
            pass

        try:
            if source == "baidu":
                count = ctx.config.get("count", 10)
                items = await _baidu_hot(count)
                formatted = _format_hot_list(items, "百度")
            else:
                count = ctx.config.get("count", 10)
                items = await _weibo_hot(count)
                formatted = _format_hot_list(items, "微博")
            await msg.edit(formatted)
        except Exception as e:
            await msg.edit(f"❌ 获取热搜失败: {e}")
            _log(ctx, f"获取{source}热搜失败: {e}")

    # ── 定时推送 ──
    async def _push_hot():
        try:
            items = await _baidu_hot(10)
            formatted = _format_hot_list(items, "百度")
            # 推送到所有群
            await ctx.send_message(formatted)
            _log(ctx, "定时推送热搜完成")
        except Exception as e:
            _log(ctx, f"定时推送热搜失败: {e}")

    if ctx.config.get("auto_push", False):
        hour = ctx.config.get("push_hour", 9)
        minute = ctx.config.get("push_minute", 0)
        ctx.schedule("hot_push", _push_hot, "cron", hour=hour, minute=minute)
        _log(ctx, f"已注册定时推送: 每天 {hour:02d}:{minute:02d}")

    @ctx.action("test_hot")
    async def _test_hot(req=None):
        items = await _baidu_hot(5)
        return {"ok": True, "message": f"百度热搜获取成功: {len(items)} 条，首条: {items[0]['word']}" if items else "获取失败"}

    @ctx.action("view_logs")
    async def _view_logs(req=None):
        logs = ctx.kv.get(_KV_LOGS, [])
        if not logs:
            return {"ok": True, "message": "暂无日志"}
        lines = ["📋 最近日志:\n"]
        for log in logs[-15:]:
            lines.append(f"[{log['t']}] {log['m']}")
        return {"ok": True, "message": "\n".join(lines)}

    ctx.log.info("[热搜热点] 已就绪")


async def teardown(ctx):
    ctx.log.info("[热搜热点] 已卸载")