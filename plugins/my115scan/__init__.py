# -*- coding: utf-8 -*-
# AWBotNest 插件：115历史扫描 (my115scan)

import asyncio
import re
import time
from datetime import datetime, timezone, timedelta
from collections import deque

from ._tmdb import TmdbApi, get_emby_tmdb_ids, emby_has_tmdb_id

__plugin__ = {
    "name": "115历史扫描",
    "id": "my115scan",
    "version": "0.2.0",
    "author": "凹凸曼",
    "description": "扫描指定频道的历史消息，识别115链接→TMDB识别→Emby查重→缺失转发到CMS入库。完整流程，和my115一致。",
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
            "section": "TMDB", "help": "zh-CN / en-US", "order": 5
        },
        "emby_url": {
            "type": "string", "default": "", "label": "Emby 地址",
            "section": "Emby", "help": "例如 http://192.168.1.1:8096", "order": 6
        },
        "emby_api_key": {
            "type": "string", "default": "", "label": "Emby API Key",
            "section": "Emby", "help": "Emby 后台获取", "order": 7
        },
        "media_types": {
            "type": "select", "default": "all", "label": "媒体类型",
            "section": "过滤", "options": {"all": "全部", "movie": "仅电影", "tv": "仅剧集"},
            "help": "只转发指定类型的资源", "order": 8
        },
        "only_complete_series": {
            "type": "boolean", "default": False, "label": "剧集仅转存完结",
            "section": "过滤", "help": "剧集未完结的跳过", "order": 9
        },
        "exclude_genres": {
            "type": "string", "default": "", "label": "排除类型",
            "section": "过滤", "help": "填TMDB类型名，逗号分隔。例如: 动画, Animation", "order": 10
        },
        "exclude_anime_only": {
            "type": "boolean", "default": False, "label": "动画仅排除日本动画",
            "section": "过滤", "help": "勾选后只排除日漫，不排除国漫/美漫", "order": 11
        },
        "dedup_hours": {
            "type": "number", "default": 24, "label": "去重冷却(小时)",
            "section": "过滤", "min": 0, "max": 720, "help": "同一TMDB在N小时内不重复转发，0=关闭", "order": 12
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

_LINK_PATTERN = re.compile(
    r"https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s)\]】]+", re.IGNORECASE
)

_COMPLETE_PATTERN = re.compile(r"完结|全\d+集|全集|全季", re.IGNORECASE)


def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


async def _send_links(client, cfg, links, label, ctx):
    """转发115链接到CMS机器人"""
    cms = cfg.get("cms_bot_username", "").strip()
    if not cms:
        return
    text = f"{label}:\n" + "\n".join(links)
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
        label = cfg.get("forward_label", "115 网盘")
        media_types = cfg.get("media_types", "all")
        only_complete = cfg.get("only_complete_series", False)
        exclude_raw = cfg.get("exclude_genres", "").strip()
        exclude_list = [g.strip().lower() for g in exclude_raw.replace("，", ",").split(",") if g.strip()] if exclude_raw else []
        dedup_hours = int(cfg.get("dedup_hours", 24) or 24)

        api = TmdbApi(cfg.get("tmdb_api_key", ""), cfg.get("tmdb_language", "zh-CN"))
        emby_url = cfg.get("emby_url", "")
        emby_key = cfg.get("emby_api_key", "")

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
                    text = (msg.text or msg.caption or "").strip()
                    if not text:
                        continue

                    links = list(_LINK_PATTERN.finditer(text))
                    if not links:
                        continue
                    links = [m.group(0) for m in links]
                    total += 1

                    # ── 提取TMDB ID ──
                    tmdb_id = None
                    media_type = None
                    tmdb_match = re.search(r"TMDB[：:\s]*(\d+)", text, re.IGNORECASE)
                    if tmdb_match:
                        tmdb_id = int(tmdb_match.group(1))
                        # 推测类型
                        if re.search(r"电视剧|剧集|TV|剧", text):
                            media_type = "tv"
                        elif re.search(r"电影|电影|Movie", text):
                            media_type = "movie"

                    if not tmdb_id:
                        try:
                            # 从标题搜索
                            title_match = re.search(r"[\u4e00-\u9fff\w\s\-:：]+", text)
                            if title_match:
                                title = title_match.group(0).strip()
                                # 提取年份
                                year_match = re.search(r"(\d{4})", text)
                                year = year_match.group(1) if year_match else ""
                                results = await api.multi_search(title, year)
                                if results:
                                    tmdb_id = results[0].get("id")
                                    media_type = results[0].get("media_type", media_type)
                        except Exception as e:
                            ctx.log.warning("[115扫描] TMDB搜索失败: %r", e)

                    if not tmdb_id:
                        ctx.log.info("[115扫描] 未识别TMDB: %s", text[:30])
                        await asyncio.sleep(delay)
                        continue

                    # ── 媒体类型过滤 ──
                    if media_types != "all" and media_type and media_type != media_types:
                        ctx.log.info("[115扫描] 类型不匹配(%s): %s", media_type, text[:30])
                        await asyncio.sleep(delay)
                        continue

                    # ── 仅完结检查 ──
                    if only_complete and media_type == "tv":
                        if not _COMPLETE_PATTERN.search(text):
                            try:
                                detail = await api.get_details(tmdb_id, media_type)
                                if detail and detail.get("status") not in ("Ended", "Cancelled"):
                                    ctx.log.info("[115扫描] 剧集未完结跳过: %s", text[:30])
                                    await asyncio.sleep(delay)
                                    continue
                            except Exception:
                                pass

                    # ── Emby查重 ──
                    has = False
                    if emby_url and emby_api_key:
                        try:
                            has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id, media_type)
                            if has:
                                ctx.log.info("[115扫描] Emby已有: %s", text[:30])
                                await asyncio.sleep(delay)
                                continue
                        except Exception as e:
                            ctx.log.warning("[115扫描] Emby查询失败: %r", e)

                    # ── 排除类型检查 ──
                    if exclude_list:
                        try:
                            detail = await api.get_details(tmdb_id, media_type)
                            if detail:
                                genres = [g.get("name", "").lower() for g in (detail.get("genres") or [])]
                                genres_lower = set(genres)
                                matched = [ex for ex in exclude_list if ex in genres_lower]
                                if matched:
                                    ctx.log.info("[115扫描] 排除类型(%s): %s", ",".join(matched), text[:30])
                                    await asyncio.sleep(delay)
                                    continue
                        except Exception:
                            pass

                    # ── 转发去重 ──
                    if dedup_hours > 0:
                        dedup_key = f"my115scan_dedup_{tmdb_id}"
                        last_ts = ctx.kv.get(dedup_key, 0) or 0
                        now = time.time()
                        if last_ts > 0 and (now - last_ts) < dedup_hours * 3600:
                            ctx.log.info("[115扫描] 去重跳过(TMDB%s): %s", tmdb_id, text[:30])
                            await asyncio.sleep(delay)
                            continue
                        ctx.kv.set(dedup_key, now)

                    # ── 转发到CMS ──
                    await _send_links(client, cfg, links, label, ctx)
                    forwarded += 1
                    ctx.log.info("[115扫描] ✅ 转发 TMDB%s: %s", tmdb_id, text[:30])

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