# -*- coding: utf-8 -*-
# AWBotNest 插件：115历史扫描 (my115scan)
# 基于 my115 改造，扫描历史消息走完整流程

import asyncio
import re
import time
from collections import deque
from datetime import datetime

from ._tmdb import TmdbApi, emby_has_tmdb_id, get_emby_tmdb_ids

__plugin__ = {
    "name": "115历史扫描",
    "id": "my115scan",
    "version": "0.3.1",
    "author": "凹凸曼",
    "description": "扫描指定频道的历史消息，识别115链接→TMDB→Emby查重→缺失转发到CMS入库。完整流程同my115。",
    "scope": "user",
    "default_enabled": False,
    "requirements": [],
    "config_schema": {
        "source_chat": {
            "type": "number", "default": 0, "label": "来源频道ID",
            "section": "扫描", "help": "扫描哪个频道的历史消息", "order": 1
        },
        "cms_bot_username": {
            "type": "string", "default": "", "label": "CMS机器人用户名",
            "section": "转发", "help": "转发给哪个机器人入库", "order": 2
        },
        "forward_label": {
            "type": "string", "default": "115 网盘", "label": "转发标签",
            "section": "转发", "help": "转发的消息前缀标签", "order": 3
        },
        "tmdb_api_key": {
            "type": "string", "default": "", "label": "TMDB API Key",
            "section": "TMDB", "help": "www.themoviedb.org 获取", "order": 4
        },
        "tmdb_language": {
            "type": "string", "default": "zh-CN", "label": "TMDB 语言",
            "section": "TMDB", "order": 5
        },
        "emby_url": {
            "type": "string", "default": "", "label": "Emby 地址",
            "section": "Emby", "help": "例如 http://192.168.1.1:8096", "order": 6
        },
        "emby_api_key": {
            "type": "string", "default": "", "label": "Emby API Key",
            "section": "Emby", "order": 7
        },
        "skip_emby_check": {
            "type": "boolean", "default": False, "label": "跳过Emby查重",
            "section": "Emby", "order": 8
        },
        "media_types": {
            "type": "select", "default": "all", "label": "媒体类型",
            "section": "过滤", "options": {"all": "全部", "movie": "仅电影", "tv": "仅剧集"}, "order": 9
        },
        "only_complete_series": {
            "type": "boolean", "default": False, "label": "剧集仅转存完结",
            "section": "过滤", "order": 10
        },
        "exclude_genres": {
            "type": "string", "default": "", "label": "排除类型",
            "section": "过滤", "help": "填TMDB类型名，逗号分隔", "order": 11
        },
        "dedup_hours": {
            "type": "number", "default": 24, "label": "去重冷却(小时)",
            "section": "过滤", "min": 0, "max": 720, "order": 12
        },
        "delay": {
            "type": "number", "default": 2, "label": "每条间隔(秒)",
            "section": "速度", "min": 1, "max": 30, "order": 13
        },
        "batch_size": {
            "type": "number", "default": 200, "label": "每批拉取条数",
            "section": "速度", "min": 50, "max": 1000, "order": 14
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

# ── 配置默认值 ──
DEFAULTS = {
    "source_chat": 0,
    "cms_bot_username": "",
    "forward_label": "115 网盘",
    "media_types": ["movie", "tv"],
    "only_complete_series": False,
    "tmdb_api_key": "",
    "tmdb_language": "zh-CN",
    "emby_url": "",
    "emby_api_key": "",
    "skip_emby_check": False,
    "exclude_genres": "",
    "dedup_hours": 24,
    "only_complete_series": False,
    "delay": 2,
    "batch_size": 200,
}

# 115分享链接
_LINK_PATTERN = re.compile(
    r"https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s)\]】]+", re.IGNORECASE
)

_COMPLETE_PATTERN = re.compile(r"完结|全\d+集|全集|全季", re.IGNORECASE)

_logs = deque(maxlen=200)


def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


def _extract_links(message) -> list[str]:
    text = message.text or message.caption or ""
    found = list(_LINK_PATTERN.finditer(text))
    if found:
        return [m.group(0) for m in found]
    ents = getattr(message, "entities", []) or []
    cap_ents = getattr(message, "caption_entities", []) or []
    links = []
    for e in ents + cap_ents:
        url = getattr(e, "url", None)
        if url and _LINK_PATTERN.match(url):
            links.append(url)
    return links


def _extract_tmdb_id(text: str) -> int | None:
    m = re.search(r"TMDB[：:\s]*(\d+)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _guess_type(text: str) -> str | None:
    if re.search(r"电视剧|剧集|TV|剧", text):
        return "tv"
    if re.search(r"电影|电影|Movie|movie", text):
        return "movie"
    return None


def _extract_title_year(text: str) -> tuple[str, str]:
    year_match = re.search(r"\((\d{4})\)", text)
    year = year_match.group(1) if year_match else ""
    title = re.sub(r"\(.*?\)", "", text).strip()
    title = re.sub(r"[\d]+[pP].*", "", title).strip()
    title = re.sub(r"★.*", "", title).strip()
    title = re.sub(r"🎬.*", "", title).strip()
    title = re.sub(r"完结|更新中", "", title).strip()
    title = re.sub(r"第\d+季", "", title).strip()
    title = re.sub(r"全\d+集", "", title).strip()
    title = title.strip(" -–—")
    return title, year


async def _resolve_by_search(cfg, title, year, ctx) -> tuple[int | None, str | None]:
    key = cfg.get("tmdb_api_key", "")
    if not key or not title:
        return None, None
    api = TmdbApi(key, cfg.get("tmdb_language", "zh-CN"))
    try:
        results = await api.multi_search(title, year)
        if results:
            return results[0].get("id"), results[0].get("media_type")
    except Exception as e:
        ctx.log.warning("[115扫描] TMDB搜索失败: %r", e)
    return None, None


async def _send_links(client, cfg, links, label, ctx):
    cms = cfg.get("cms_bot_username", "").strip()
    if not cms:
        return
    text = f"{label}:\n" + "\n".join(links)
    ctx.log.info("[115扫描] 转发到 %s: %s", cms, text[:50])
    try:
        await client.send_message(cms, text)
    except Exception as e:
        ctx.log.warning("[115扫描] 转发失败: %r", e)


async def _process_one(client, cfg, msg, ctx):
    """处理单条消息（完整流程，同my115）"""
    text = msg.text or msg.caption or ""
    if not text:
        return None

    links = _extract_links(msg)
    if not links:
        return None

    tmdb_id = _extract_tmdb_id(text)
    media_type = _guess_type(text)

    if not tmdb_id:
        title, year = _extract_title_year(text)
        if title:
            tmdb_id, guessed = await _resolve_by_search(cfg, title, year, ctx)
            if not media_type:
                media_type = guessed

    if not tmdb_id:
        return None

    # 媒体类型过滤
    mt = cfg.get("media_types", ["movie", "tv"])
    if media_type and mt and media_type not in mt:
        return {"action": "类型跳过", "tmdb_id": tmdb_id}

    # 仅完结检查
    if cfg.get("only_complete_series", False) and media_type == "tv":
        if not _COMPLETE_PATTERN.search(text):
            try:
                api = TmdbApi(cfg.get("tmdb_api_key", ""), cfg.get("tmdb_language", "zh-CN"))
                detail = await api.get_details(tmdb_id, media_type)
                if detail and detail.get("status") not in ("Ended", "Cancelled"):
                    return {"action": "未完结跳过", "tmdb_id": tmdb_id}
            except Exception:
                pass

    # Emby查重
    if not cfg.get("skip_emby_check", False):
        emby_url = cfg.get("emby_url", "")
        emby_key = cfg.get("emby_api_key", "")
        if emby_url and emby_key:
            try:
                has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id, media_type)
                if has:
                    return {"action": "Emby已有", "tmdb_id": tmdb_id}
            except Exception as e:
                ctx.log.warning("[115扫描] Emby查询失败: %r", e)

    # 排除类型
    exclude_raw = cfg.get("exclude_genres", "").strip()
    if exclude_raw:
        exclude_list = [g.strip().lower() for g in exclude_raw.replace("，", ",").split(",") if g.strip()]
        if exclude_list:
            try:
                api = TmdbApi(cfg.get("tmdb_api_key", ""), cfg.get("tmdb_language", "zh-CN"))
                detail = await api.get_details(tmdb_id, media_type)
                if detail:
                    genres = [g.get("name", "").lower() for g in (detail.get("genres") or [])]
                    matched = [ex for ex in exclude_list if ex in genres]
                    if matched:
                        for ex in matched:
                            if ex == "animation" and cfg.get("exclude_anime_only", False):
                                orig_lang = (detail.get("original_language") or "").lower()
                                if orig_lang != "ja":
                                    matched.remove(ex)
                        if matched:
                            return {"action": "排除类型跳过", "tmdb_id": tmdb_id}
            except Exception:
                pass

    # 转发去重
    dedup_hours = int(cfg.get("dedup_hours", 24) or 24)
    if dedup_hours > 0:
        dedup_key = f"my115scan_dedup_{tmdb_id}"
        last_ts = ctx.kv.get(dedup_key, 0) or 0
        now = time.time()
        if last_ts > 0 and (now - last_ts) < dedup_hours * 3600:
            return {"action": "重复跳过", "tmdb_id": tmdb_id}
        ctx.kv.set(dedup_key, now)

    # 转发到CMS
    label = cfg.get("forward_label", "115 网盘")
    await _send_links(client, cfg, links, label, ctx)
    return {"action": "转发", "tmdb_id": tmdb_id}


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
        if not cfg.get("tmdb_api_key", "").strip():
            return {"ok": False, "message": "未设置TMDB API Key"}
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

        ctx.log.info("[115扫描] 开始: 来源%s, 每批%s条, 间隔%s秒", src, batch, delay)

        offset = 0
        while True:
            if ctx.kv.get("my115scan_stop", False):
                break

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

            # 从旧到新处理
            for mid in reversed(ids):
                if ctx.kv.get("my115scan_stop", False):
                    break
                try:
                    msg = await client.get_messages(src, mid)
                    if not msg:
                        continue
                    result = await _process_one(client, cfg, msg, ctx)
                    if result and result.get("action") == "转发":
                        forwarded += 1
                        ctx.log.info("[115扫描] ✅ 转发 TMDB%s: %s", result["tmdb_id"], (msg.text or msg.caption or "")[:30])
                    total += 1
                except Exception as e:
                    ctx.log.warning("[115扫描] 消息%s处理异常: %r", mid, e)

                await asyncio.sleep(delay)

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