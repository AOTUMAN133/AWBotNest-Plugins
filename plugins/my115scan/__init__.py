# -*- coding: utf-8 -*-
# AWBotNest 插件：115历史扫描 (my115scan)

import asyncio
import re
import time
from datetime import datetime, timezone, timedelta
from collections import deque

# 复用 my115 的 TMDB/Emby 模块
from . import _tmdb
from ._tmdb import TmdbApi, get_emby_tmdb_ids, emby_has_tmdb_id

__plugin__ = {
    "name": "115历史扫描",
    "id": "my115scan",
    "version": "0.1.0",
    "author": "凹凸曼",
    "description": "扫描指定频道的历史消息，识别115链接→TMDB识别→Emby查重→缺失转发到CMS入库。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "source_chat": {
            "type": "number", "default": 0, "label": "来源频道ID",
            "section": "扫描", "help": "扫描哪个频道的历史消息", "order": 1
        },
        "cms_bot_username": {
            "type": "string", "default": "", "label": "CMS机器人用户名",
            "section": "转发", "help": "转发给哪个机器人入库", "order": 2
        },
        "delay": {
            "type": "number", "default": 2, "label": "每条间隔(秒)",
            "section": "速度", "min": 1, "max": 30, "help": "处理每条消息的间隔", "order": 3
        },
        "batch_size": {
            "type": "number", "default": 200, "label": "每批拉取条数",
            "section": "速度", "min": 50, "max": 1000, "help": "每次从API拉取多少条消息", "order": 4
        },
        "_status": {
            "type": "info", "label": "状态",
            "section": "状态"
        },
        "start_scan": {
            "type": "action", "label": "▶ 开始扫描",
            "section": "状态", "action": "start_scan", "danger": True
        },
        "stop_scan": {
            "type": "action", "label": "⏹ 停止扫描",
            "section": "状态", "action": "stop_scan", "danger": True
        },
        "reset_scan": {
            "type": "action", "label": "🔄 重置进度",
            "section": "状态", "action": "reset_scan", "danger": True
        },
    },
}

# 115链接正则
_LINK_PATTERN = re.compile(
    r"https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s)\]】]+", re.IGNORECASE
)

_LOG_QUEUE = deque(maxlen=200)

def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


async def _send_links(client, cfg, links, ctx):
    """转发115链接到CMS机器人"""
    cms = cfg.get("cms_bot_username", "").strip()
    if not cms:
        return
    text = "\n".join(links)
    try:
        await client.send_message(cms, text)
    except Exception as e:
        ctx.log.warning("[115扫描] 转发失败: %r", e)


async def setup(ctx):
    ctx.update_config({"_status": "就绪"})

    @ctx.action("start_scan")
    async def _start(req=None):
        cfg = ctx.config
        src = int(cfg.get("source_chat", 0) or 0)
        if not src:
            return {"ok": False, "message": "未设置来源频道"}
        if not cfg.get("cms_bot_username", "").strip():
            return {"ok": False, "message": "未设置CMS机器人"}
        ctx.kv.set("my115scan_stop", False)
        ctx.update_config({"_status": "扫描中…"})
        asyncio.create_task(_do_scan(ctx, src))
        return {"ok": True, "message": "开始扫描"}

    @ctx.action("stop_scan")
    async def _stop(req=None):
        ctx.kv.set("my115scan_stop", True)
        ctx.update_config({"_status": "已停止"})
        return {"ok": True, "message": "已停止"}

    @ctx.action("reset_scan")
    async def _reset(req=None):
        ctx.kv.set("my115scan_stop", True)
        ctx.kv.set("my115scan_last_id", 0)
        ctx.kv.set("my115scan_total", 0)
        ctx.kv.set("my115scan_forwarded", 0)
        ctx.update_config({"_status": "已重置"})
        return {"ok": True, "message": "进度已重置"}

    # 状态推送
    async def status_pusher():
        total = int(ctx.kv.get("my115scan_total", 0) or 0)
        fwd = int(ctx.kv.get("my115scan_forwarded", 0) or 0)
        last = int(ctx.kv.get("my115scan_last_id", 0) or 0)
        ctx.update_config({"_status": f"已扫描{total}条, 转发{fwd}条, 最后ID={last}"})

    ctx.schedule(status_pusher, "interval", seconds=10, id="my115scan_status")


async def _do_scan(ctx, src):
    """执行扫描任务"""
    try:
        apps = list(ctx.user_apps or [])
        if not apps:
            ctx.log.error("[115扫描] 没有可用用户账号")
            ctx.update_config({"_status": "失败：无可用账号"})
            return
        client = apps[0]

        cfg = ctx.config
        delay = int(cfg.get("delay", 2) or 2)
        batch = int(cfg.get("batch_size", 200) or 200)
        last_id = int(ctx.kv.get("my115scan_last_id", 0) or 0)
        total = int(ctx.kv.get("my115scan_total", 0) or 0)
        forwarded = int(ctx.kv.get("my115scan_forwarded", 0) or 0)

        # 初始化 TMDB
        tmdb_key = cfg.get("tmdb_api_key", "")
        tmdb_lang = cfg.get("tmdb_language", "zh-CN")
        api = TmdbApi(tmdb_key, tmdb_lang) if tmdb_key else None

        ctx.log.info("[115扫描] 开始: 来源%s, 每批%s条, 间隔%s秒", src, batch, delay)

        offset = 0
        while True:
            if ctx.kv.get("my115scan_stop", False):
                ctx.log.info("[115扫描] 收到停止信号")
                break

            # 拉一批消息
            ids = []
            async for m in client.get_chat_history(src, limit=batch, offset_id=offset):
                ids.append(m.id)
            if not ids:
                break
            if last_id:
                ids = [mid for mid in ids if mid > last_id]
                if not ids:
                    break
            offset = ids[-1]

            # 逐条处理
            for mid in reversed(ids):  # 从旧到新
                if ctx.kv.get("my115scan_stop", False):
                    break
                try:
                    msg = await client.get_messages(src, mid)
                    if not msg:
                        continue
                    text = (msg.text or msg.caption or "").strip()
                    if not text:
                        continue
                    links = list(_LINK_PATTERN.finditer(text))
                    if not links:
                        continue
                    links = [m.group(0) for m in links]
                    total += 1

                    # 提取TMDB ID
                    tmdb_id = None
                    tmdb_match = re.search(r"TMDB[：:\s]*(\d+)", text, re.IGNORECASE)
                    if tmdb_match:
                        tmdb_id = int(tmdb_match.group(1))

                    if not tmdb_id and api:
                        # 搜索TMDB
                        title_match = re.search(r"[\u4e00-\u9fff\w\s\-:：]+", text)
                        if title_match:
                            title = title_match.group(0).strip()
                            results = await api.multi_search(title)
                            if results:
                                tmdb_id = results[0].get("id")

                    if tmdb_id:
                        # Emby查重
                        emby_url = cfg.get("emby_url", "")
                        emby_key = cfg.get("emby_api_key", "")
                        has = False
                        if emby_url and emby_key:
                            try:
                                has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id)
                            except Exception:
                                pass
                        if not has:
                            # 转发到CMS
                            await _send_links(client, cfg, links, ctx)
                            forwarded += 1
                            ctx.log.info("[115扫描] ✅ 转发 TMDB%s: %s", tmdb_id, text[:30])
                    else:
                        ctx.log.info("[115扫描] 未识别 %s", text[:30])

                except Exception as e:
                    ctx.log.warning("[115扫描] 消息%s处理异常: %r", mid, e)

                await asyncio.sleep(delay)

            # 保存进度
            ctx.kv.set("my115scan_last_id", ids[-1])
            ctx.kv.set("my115scan_total", total)
            ctx.kv.set("my115scan_forwarded", forwarded)
            ctx.log.info("[115扫描] 进度: 扫描%s条, 转发%s条", total, forwarded)

            if len(ids) < batch:
                break

        ctx.kv.set("my115scan_last_id", ids[-1] if ids else 0)
        ctx.kv.set("my115scan_total", total)
        ctx.kv.set("my115scan_forwarded", forwarded)
        ctx.update_config({"_status": f"完成: 扫描{total}条, 转发{forwarded}条"})
        ctx.log.info("[115扫描] ✅ 完成, 扫描%s条, 转发%s条", total, forwarded)

    except Exception as e:
        ctx.log.error("[115扫描] 异常: %r", e)
        ctx.update_config({"_status": f"异常: {e}"})


async def teardown(ctx):
    pass