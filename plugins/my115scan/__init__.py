# =============================================================================
# AWBotNest 插件：115 频道监控（movie_monitor_115）
#
# 通用监控：监听会话里的 115 分享消息，不依赖固定频道格式——
#   1) 优先直接读取消息里写好的「TMDB ID」；
#   2) 读不到再用标题/年份走 TMDB 搜索识别；
#   3) 查 Emby 媒体库，库里没有的把 115 链接转发给 CMS 入库机器人。
# 链接支持多域名（115.com / 115cdn.com …）与「超链接」形式（藏在文字里）。
# 也支持 /getmedia 手动查 TMDB。用你的用户账号监听，参数都在配置里填。
# =============================================================================

import asyncio
import hashlib
import re
import time
from collections import deque
from datetime import datetime

from ._tmdb import TmdbApi, emby_has_tmdb_id, get_emby_tmdb_ids

__plugin__ = {
    "name": "115历史扫描",
    "id": "my115scan",
    "version": "0.10.22",
    "author": "凹凸曼",
    "description": "扫描指定频道的历史消息，识别115链接→TMDB→Emby查重→缺失转发到CMS入库。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
    "requirements": [],
    "config_schema": {
        "source_chat": {
            "type": "number", "default": 0, "label": "来源频道ID",
            "section": "扫描设置", "help": "扫描哪个频道的历史消息", "order": 1
        },
        "cms_bot_username": {
            "type": "string", "default": "", "label": "CMS机器人用户名",
            "section": "扫描设置", "help": "转发给哪个机器人入库", "order": 2
        },
        "forward_label": {
            "type": "string", "default": "115 网盘", "label": "转发标签",
            "section": "扫描设置", "order": 3
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
            "section": "速度控制", "min": 1, "max": 30, "order": 13
        },
        "batch_size": {
            "type": "number", "default": 200, "label": "每批拉取条数",
            "section": "速度控制", "min": 50, "max": 1000, "order": 14
        },
        "_scan_status": {
            "type": "info", "label": "扫描状态",
            "section": "操作"
        },
        "start_scan": {
            "type": "action", "label": "▶ 开始扫描",
            "section": "操作", "action": "start_scan", "danger": True
        },
        "stop_scan": {
            "type": "action", "label": "⏹ 停止扫描",
            "section": "操作", "action": "stop_scan", "danger": True
        },
        "reset_scan": {
            "type": "action", "label": "🔄 重置进度",
            "section": "操作", "action": "reset_scan", "danger": True
        },
    },
}

# ── 配置默认值 ──
DEFAULTS = {
    "media_types": ["movie", "tv"],
    "only_complete_series": False,
    "tmdb_api_key": "",
    "tmdb_language": "zh-CN",
    "emby_url": "",
    "emby_api_key": "",
    "emby_db_path": "", "skip_emby_check": False, "emby_check_mode": "cache",
    "cms_bot_username": "",
    "forward_label": "115 网盘",
    "dedup_hours": 24,
    "forward_to_saved": False,
    "pan115_cookie": "",
    "exclude_genres": "",
}

# ── 运行态 ──
_logs = deque(maxlen=200)

# 115 分享链接
_LINK_PATTERN = re.compile(
    r"https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s)\]】]+", re.IGNORECASE
)
_TMDB_ID_PATTERN = re.compile(r"TMDB\s*(?:ID)?\s*[:：]\s*(\d+)", re.IGNORECASE)
_COMPLETE_PATTERN = re.compile(r"完结|全\s*\d+\s*[集話话]|全集|\(完|（完")
_GETMEDIA_TTL = 30


def _effective_cfg(ctx) -> dict:
    cfg = {**DEFAULTS, **dict(ctx.config or {})}
    # 统一 media_types 为列表
    mt = cfg.get("media_types", ["movie", "tv"])
    if isinstance(mt, str):
        mt = [x.strip() for x in mt.split(",") if x.strip()]
    if not mt:
        mt = ["movie", "tv"]
    cfg["media_types"] = mt
    return cfg


def _fmt_getmedia(result, title, year, limit=8) -> str:
    yr = year if year and year != "0" else ""
    if not result:
        return f"❌ TMDB 无结果：{title} {yr}".rstrip()
    lines = [f"🔍 {title} {yr}".rstrip() + f"  ·  {len(result)} 条"]
    for it in result[:limit]:
        name = it.get("title") or it.get("name") or "?"
        date = it.get("release_date") or it.get("first_air_date") or ""
        y = date[:4] if date else "----"
        mt = "电影" if it.get("media_type") == "movie" else "剧集"
        vote = it.get("vote_average") or 0
        lines.append(f"• [{mt}] {name} ({y})  id={it.get('id')}  ⭐{vote}")
    if len(result) > limit:
        lines.append(f"… 其余 {len(result) - limit} 条略")
    return "\n".join(lines)


def _lines(raw) -> list[str]:
    return [s.strip() for s in str(raw or "").splitlines() if s.strip()]


def _normalize(raw):
    s = str(raw or "").strip().lower()
    s = re.sub(r"[\s\-_\.]+", "", s)
    return s


def _monitor_ids(cfg) -> list[int]:
    raw = cfg.get("monitor_ids", "")
    if isinstance(raw, list):
        return [int(x) for x in raw if x]
    ids = []
    for tok in re.split(r"[,，\s]+", str(raw or "").strip()):
        if tok:
            try:
                ids.append(int(tok))
            except ValueError:
                pass
    return ids


def _pan115_id(cfg):
    ck = str(cfg.get("pan115_cookie") or "").strip()
    if not ck:
        return None
    try:
        from ._pan115 import Pan115
        return Pan115(ck)
    except Exception:  # noqa: BLE001
        return None


def _msg_text(message) -> str:
    return (message.text or message.caption or "").strip()


def _extract_links(message) -> list[str]:
    text = _msg_text(message)
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


def _extract_tmdb_id(text: str):
    m = _TMDB_ID_PATTERN.search(text)
    return int(m.group(1)) if m else None


def _guess_type(text: str):
    lower = text.lower()
    if any(k in lower for k in ["电影", "movie", "film"]):
        return "movie"
    if any(k in lower for k in ["剧集", "电视剧", "tv", "series"]):
        return "tv"
    return None


def _extract_title_year(text: str):
    lines = _lines(text)
    if not lines:
        return "", ""
    first = lines[0]
    year_m = re.search(r"\b(19\d{2}|20\d{2})\b", first)
    year = year_m.group(1) if year_m else ""
    title = re.sub(r"\b(19\d{2}|20\d{2})\b", "", first).strip()
    title = re.sub(r"[【\[].*?[】\]]", "", title).strip()
    return title, year


def _parse_pan115(text: str):
    lines = _lines(text)
    if not lines:
        return {}
    code = ""
    m = re.search(r"(?:提取码|访问码|口令|密码)[：:]\s*(\w+)", text, re.IGNORECASE)
    if m:
        code = m.group(1)
    return {"raw": lines[0], "access_code": code}


async def _resolve_target(client, target, ctx):
    if target == "me":
        return "me"
    if target.startswith("@"):
        try:
            chat = await client.get_chat(target)
            return chat.id
        except Exception as e:  # noqa: BLE001
            ctx.log.error("[115扫描] 解析转发目标失败 %s: %r", target, e)
            return None
    try:
        return int(target)
    except ValueError:
        return None


async def _send_links(client, cfg, links, label, ctx):
    target = cfg.get("cms_bot_username") or ""
    if cfg.get("forward_to_saved"):
        target = "me"
    if not target:
        return
    tid = await _resolve_target(client, target, ctx)
    if not tid:
        return
    text = f"{label}\n" + "\n".join(links)
    try:
        await client.send_message(tid, text)
    except Exception as e:  # noqa: BLE001
        ctx.log.error("[115扫描] 转发失败: %r", e)


async def _resolve_by_search(cfg, title, year, ctx):
    if not (cfg.get("tmdb_api_key") and title):
        return None, None
    api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
    try:
        result = await api.multi_search(title, year)
    except Exception as e:  # noqa: BLE001
        ctx.log.error("[115扫描] TMDB 搜索失败: %r", e)
        return None, None
    if not result:
        return None, None
    first = result[0]
    tmdb_id = first.get("id")
    media_type = first.get("media_type")
    return tmdb_id, media_type


async def _process(client, cfg, message, ctx):
    # 检查停止信号
    if ctx.kv.get("my115scan_stop", False):
        return
    links = _extract_links(message)
    if not links:
        return
    ctx.log.info("[115扫描] 检测到 %d 条 115 链接", len(links))
    text = _msg_text(message)
    tmdb_id = _extract_tmdb_id(text)
    media_type = _guess_type(text)

    if not tmdb_id:
        title, year = _extract_title_year(text)
        tmdb_id, guessed_type = await _resolve_by_search(cfg, title, year, ctx)
        if not media_type:
            media_type = guessed_type
    # 如果media_type仍未确定但TMDB ID已知，查TMDB确认类型
    if tmdb_id and media_type is None:
        try:
            api = TmdbApi(cfg.get("tmdb_api_key", ""), cfg.get("tmdb_language", "zh-CN"))
            tv_detail = await api.get_details(tmdb_id, "tv")
            if tv_detail and tv_detail.get("id"):
                media_type = "tv"
                ctx.log.info("[115扫描] TMDB确认类型: tv, tmdb_id=%d", tmdb_id)
            else:
                movie_detail = await api.get_details(tmdb_id, "movie")
                if movie_detail and movie_detail.get("id"):
                    media_type = "movie"
                    ctx.log.info("[115扫描] TMDB确认类型: movie, tmdb_id=%d", tmdb_id)
        except Exception as e:
            ctx.log.warning("[115扫描] TMDB类型查询失败: %r", e)

    if not tmdb_id:
        ctx.log.info("[115扫描] 未识别 TMDB: %s", text[:50])
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": None, "action": "跳过(未识别TMDB)"})
        return

    allowed = cfg.get("media_types", ["movie", "tv"])
    if isinstance(allowed, str):
        allowed = [x.strip() for x in allowed.split(",") if x.strip()]
    if not allowed:
        allowed = ["movie", "tv"]
    if media_type and media_type not in allowed:
        ctx.log.info("[115扫描] 跳过类型 %s: %d, allowed=%s, media_type=%s", media_type, tmdb_id, str(allowed), media_type)
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": f"跳过(类型{media_type})"})
        return

    if cfg.get("only_complete_series", False):
        # 尝试确定media_type（如果还没确定的话）
        check_type = media_type
        if check_type is None:
            if re.search(r"\bs\d+\s*e\d+", text.lower()) or re.search(r"第\s*\d+\s*[集話话]", text):
                check_type = "tv"
        ctx.log.info("[115扫描] 完结检查: media_type=%s check_type=%s text=%s", media_type, check_type, text[:50])
        if check_type == "tv":
            # 先看消息文本有没有完结关键词（快速判断）
            if _COMPLETE_PATTERN.search(text):
                ctx.log.info("[115扫描] 文本匹配完结关键词: %s", text[:50])
                pass  # 文本明确写了完结
            else:
                ctx.log.info("[115扫描] 文本未匹配完结, 查询TMDB: tmdb_id=%d", tmdb_id)
                # 文本没写，查 TMDB 确认是否完结
                detail = None
                try:
                    api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
                    detail = await api.get_details(tmdb_id, check_type)
                    status = detail.get("status", "N/A")
                    in_prod = detail.get("in_production")
                    ctx.log.info("[115扫描] TMDB详情: status=%s in_production=%s", status, in_prod)
                    if detail.get("status") in ("Ended", "Canceled", "Cancelled"):
                        ctx.log.info("[115扫描] TMDB确认已完结: %d", tmdb_id)
                        pass
                    elif detail.get("in_production") is False:
                        ctx.log.info("[115扫描] TMDB确认不再制作: %d", tmdb_id)
                        pass
                    else:
                        ctx.log.info("[115扫描] 剧集未完结(TMDB), 跳过: %d", tmdb_id)
                        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "跳过(未完结)"})
                        return
                except Exception as e:
                    ctx.log.warning("[115扫描] TMDB完结查询异常: %r", e)
                    if not _COMPLETE_PATTERN.search(text):
                        ctx.log.info("[115扫描] 剧集未完结(文本), 跳过: %d", tmdb_id)
                        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "跳过(未完结)"})
                        return

    if not cfg.get("skip_emby_check", False):
        emby_url = cfg.get("emby_url")
        emby_key = cfg.get("emby_api_key")
        if emby_url and emby_key:
            emby_set = cfg.get("_emby_set")
            try:
                has = False
                if emby_set:
                    has = tmdb_id in emby_set
                else:
                    if ctx.kv.get("my115scan_stop", False):
                        return
                    has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id)
                if has:
                    ctx.log.info("[115扫描] Emby 已有 %d，跳过", tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby已有"})
                    return
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby未命中"})
            except Exception as e:  # noqa: BLE001
                err = str(e) or e.__class__.__name__
                ctx.log.warning("[115扫描] Emby 查询失败(%s)，跳过 %d 避免重复", err[:30], tmdb_id)
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": f"Emby查询失败-跳过({err[:30]})"})
                return
        else:
            _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby未配置跳过查重"})
    else:
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "已跳过查重"})

    # 排除类型检查
    exclude_raw = str(cfg.get("exclude_genres", "") or "").strip()
    if exclude_raw and media_type and tmdb_id:
        exclude_list = [g.strip().lower() for g in exclude_raw.replace("，", ",").split(",") if g.strip()]
        if exclude_list:
            try:
                api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
                detail = await api.get_details(tmdb_id, media_type)
                # 获取 genre 英文名（兼容语言设置）
                _GENRE_IDS = {12:"adventure",14:"fantasy",16:"animation",18:"drama",27:"horror",28:"action",35:"comedy",36:"history",37:"western",53:"thriller",80:"crime",99:"documentary",878:"science fiction",964:"mystery",10402:"music",10749:"romance",10751:"family",10752:"war",10759:"action & adventure",10762:"kids",10763:"news",10764:"reality",10765:"sci-fi & fantasy",10766:"soap",10767:"talk",10768:"war & politics",10770:"tv movie"}
                genre_ids = [g.get("id") for g in (detail.get("genres") or [])]
                genre_names = [_GENRE_IDS.get(gid) for gid in genre_ids if _GENRE_IDS.get(gid)]
                is_animation = 16 in genre_ids

                skip = False
                matched = []
                for rule in exclude_list:
                    if rule.startswith("animation:") and is_animation:
                        country = rule.split(":", 1)[1]
                        origin = detail.get("origin_country") or []
                        if country == "cn" and "CN" in origin:
                            skip = True; matched.append(rule)
                        elif country == "jp" and "JP" in origin:
                            langs = [l.get("iso_639_1","") for l in (detail.get("spoken_languages") or [])]
                            if "zh" not in langs:
                                skip = True; matched.append(rule)
                        elif country == "us" and "US" in origin:
                            skip = True; matched.append(rule)
                        elif country == "other" and origin:
                            if not any(c in origin for c in ("CN", "JP", "US")):
                                skip = True; matched.append(rule)
                    elif rule in genre_names:
                        skip = True; matched.append(rule)
                    if skip:
                        break

                if skip:
                    ctx.log.info("[115扫描] 排除类型 %s: %d", exclude_raw, tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": f"排除类型({','.join(matched)})"})
                    return
            except Exception:  # noqa: BLE001
                pass

    label = cfg.get("forward_label", "115 网盘")
    # 转发去重：同一TMDB ID在冷却期内不重复转发
    if tmdb_id:
        dedup_hours = int(cfg.get("dedup_hours", 24) or 24)
        if dedup_hours > 0:
            dedup_key = f"my115_dedup_{tmdb_id}"
            last_ts = ctx.kv.get(dedup_key, 0) or 0
            now = time.time()
            if last_ts > 0 and (now - last_ts) < dedup_hours * 3600:
                ctx.log.info("[115扫描] TMDB %d 在冷却期内(%sh)，跳过重复转发", tmdb_id, dedup_hours)
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "重复跳过"})
                return
    # 链接去重（即使没有TMDB ID，相同链接也不重复转发）
    link_hash = hashlib.md5("".join(sorted(links)).encode()).hexdigest()
    link_dedup_key = "my115_link_dedup_" + link_hash
    link_last = ctx.kv.get(link_dedup_key, 0) or 0
    now = time.time()
    link_dedup_hours = max(24, int(cfg.get("dedup_hours", 24) or 24))
    if link_last > 0 and (now - link_last) < link_dedup_hours * 3600:
        ctx.log.info("[115扫描] 链接在冷却期内，跳过重复转发")
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "链接重复跳过"})
        return
    ctx.kv.set(link_dedup_key, now)
    if tmdb_id and dedup_hours > 0:
        ctx.kv.set(f"my115_dedup_{tmdb_id}", now)
    await _send_links(client, cfg, links, label, ctx)
    ctx.log.info("[115扫描] 已转发 TMDB %d: %s", tmdb_id, text[:30])
    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "转发"})
    # 转存后加入缓存，防止同批重复转存
    emby_set = cfg.get("_emby_set")
    if emby_set is not None:
        emby_set.add(tmdb_id)


async def _cmd_getmedia(client, message, ctx):
    text = message.text or ""
    parts = text.split(maxsplit=2)
    if len(parts) < 2:
        return
    query = parts[1]
    year = parts[2] if len(parts) > 2 else ""
    cfg = _effective_cfg(ctx)
    if not cfg.get("tmdb_api_key"):
        return
    api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
    try:
        result = await api.multi_search(query, year)
        summary = _fmt_getmedia(result, query, year)
    except Exception as e:  # noqa: BLE001
        summary = f"❌ 查询失败：{e}"
    try:
        await message.edit(f"```\n{summary}\n```")
    except Exception:
        pass
    await asyncio.sleep(_GETMEDIA_TTL)
    try:
        await message.delete()
    except Exception:
        pass


async def _cmd_find(client, message, ctx):
    text = message.text or ""
    m = re.search(r"/find\s+(\d+)", text, re.IGNORECASE)
    if not m:
        return
    tmdb_id = int(m.group(1))
    cfg = _effective_cfg(ctx)
    emby_url = cfg.get("emby_url")
    emby_key = cfg.get("emby_api_key")
    if not (emby_url and emby_key):
        return
    try:
        has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id)
        reply = f"✅ Emby 有 TMDB {tmdb_id}" if has else f"❌ Emby 无 TMDB {tmdb_id}"
    except Exception as e:  # noqa: BLE001
        reply = f"❌ 查询失败：{e}"
    try:
        await message.edit(reply)
    except Exception:
        pass
    await asyncio.sleep(_GETMEDIA_TTL)
    try:
        await message.delete()
    except Exception:
        pass


async def setup(ctx):
    # ───────── Vue 模式后端 API ─────────
    @ctx.on_api("/status", methods=["GET"])
    async def _api_status(req):
        cfg = _effective_cfg(ctx)
        tmdb_ok = bool(cfg.get("tmdb_api_key"))
        emby_ok = bool(cfg.get("emby_url") and cfg.get("emby_api_key"))
        items = 0
        if emby_ok:
            try:
                ids = await get_emby_tmdb_ids(cfg["emby_url"], cfg["emby_api_key"])
                items = len(ids)
            except Exception:  # noqa: BLE001
                pass
        return {
            "tmdb_ok": tmdb_ok,
            "tmdb_status": "已配置" if tmdb_ok else "未配置",
            "emby_ok": emby_ok,
            "emby_status": "连接正常" if emby_ok else "未配置",
            "emby_items": items,
        }

    @ctx.on_api("/test", methods=["POST"])
    async def _api_test(req):
        cfg = _effective_cfg(ctx)
        msgs = []

        if cfg.get("tmdb_api_key"):
            api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
            try:
                await api.multi_search("复仇者联盟", "2012")
                msgs.append("TMDB: ✅")
            except Exception as e:  # noqa: BLE001
                msgs.append(f"TMDB: ❌ {e}")
        else:
            msgs.append("TMDB: 未配置")

        if cfg.get("emby_url") and cfg.get("emby_api_key"):
            try:
                await get_emby_tmdb_ids(cfg["emby_url"], cfg["emby_api_key"])
                msgs.append("Emby: ✅")
            except Exception as e:  # noqa: BLE001
                err = str(e) or e.__class__.__name__
                ctx.log.warning("[115扫描] Emby测试失败: %r", e)
                msgs.append(f"Emby: ❌ {err}")
        else:
            msgs.append("Emby: 未配置")

        ok = all("✅" in m for m in msgs)
        return {"ok": ok, "message": " | ".join(msgs)}

    @ctx.on_api("/logs", methods=["GET"])
    async def _api_logs(req):
        return {"logs": list(_logs)}

    @ctx.on_api("/update_config", methods=["POST"])
    async def _api_update_config(req):
        body = await req.json()
        # shareswitch 从 enabled 推导
        body["shareswitch"] = body.get("shareswitch", True)
        ctx.update_config(body)
        return {"ok": True}

    # ───────── 监听 115 分享消息 ─────────
    @ctx.on_message(ctx.filters.text | ctx.filters.caption, group=7)
    async def monitor_channels(client, message):
        cfg = _effective_cfg(ctx)
        if not cfg.get("shareswitch", False):
            return
        monitor_ids = _monitor_ids(cfg)
        if monitor_ids and message.chat.id not in monitor_ids:
            return
        try:
            await _process(client, cfg, message, ctx)
        except Exception as e:  # noqa: BLE001
            ctx.log.error("[115扫描] 处理消息异常: %r", e)

    # ───────── 命令：/getmedia 和 /find ─────────
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=-9)
    async def commands(client, message):
        text = message.text or ""
        if re.match(r"^[/\.]getmedia(?:\s|$)", text, re.IGNORECASE):
            await _cmd_getmedia(client, message, ctx)
        elif re.match(r"^[/\.]find(?:\s|$)", text, re.IGNORECASE):
            await _cmd_find(client, message, ctx)


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
        ctx.update_config({"_scan_status": "扫描中\u2026"})
        asyncio.create_task(_do_scan(ctx, src))
        return {"ok": True, "message": "开始扫描"}

    @ctx.action("stop_scan")
    async def _stop(req=None):
        ctx.kv.set("my115scan_stop", True)
        ctx.update_config({"_scan_status": "已停止"})
        return {"ok": True, "message": "已停止"}

    @ctx.action("reset_scan")
    async def _reset(req=None):
        ctx.kv.set("my115scan_stop", True)
        ctx.kv.set("my115scan_last_id", 0)
        ctx.kv.set("my115scan_total", 0)
        ctx.kv.set("my115scan_forwarded", 0)
        ctx.update_config({"_scan_status": "已重置"})
        return {"ok": True, "message": "已重置"}

    async def _scan_status_pusher():
        total = int(ctx.kv.get("my115scan_total", 0) or 0)
        fwd = int(ctx.kv.get("my115scan_forwarded", 0) or 0)
        last = int(ctx.kv.get("my115scan_last_id", 0) or 0)
        ctx.update_config({"_scan_status": f"已扫描{total}条, 转发{fwd}条, 最后ID={last}"})

    ctx.schedule(_scan_status_pusher, "interval", seconds=15, id="my115scan_status")

    # ───────── 扫描 API ─────────
    @ctx.on_api("/start_scan", methods=["POST"])
    async def _api_start_scan(req):
        cfg = ctx.config
        src = int(cfg.get("source_chat", 0) or 0)
        if not src:
            return {"ok": False, "message": "未设置来源频道"}
        if not cfg.get("cms_bot_username", "").strip():
            return {"ok": False, "message": "未设置CMS机器人"}
        if not cfg.get("tmdb_api_key", "").strip():
            return {"ok": False, "message": "未设置TMDB API Key"}
        ctx.kv.set("my115scan_stop", False)
        asyncio.create_task(_do_scan(ctx, src))
        return {"ok": True, "message": "开始扫描"}

    @ctx.on_api("/stop_scan", methods=["POST"])
    async def _api_stop_scan(req):
        ctx.kv.set("my115scan_stop", True)
        return {"ok": True, "message": "已停止"}

    @ctx.on_api("/reset_scan", methods=["POST"])
    async def _api_reset_scan(req):
        ctx.kv.set("my115scan_stop", True)
        ctx.kv.set("my115scan_last_id", 0)
        ctx.kv.set("my115scan_total", 0)
        ctx.kv.set("my115scan_forwarded", 0)
        return {"ok": True, "message": "已重置"}

    @ctx.on_api("/scan_status", methods=["GET"])
    async def _api_scan_status(req):
        running = not ctx.kv.get("my115scan_stop", True)
        total = int(ctx.kv.get("my115scan_total", 0) or 0)
        fwd = int(ctx.kv.get("my115scan_forwarded", 0) or 0)
        last = int(ctx.kv.get("my115scan_last_id", 0) or 0)
        cfg_status = ctx.config.get("_scan_status", "")
        if cfg_status:
            status = cfg_status
        elif running:
            status = f"扫描{total}条, 转发{fwd}条"
        else:
            status = "就绪"
        return {"status": status, "running": running}


    @ctx.on_api("/build_cache", methods=["POST"])
    async def _api_build_cache(req):
        cfg = ctx.config
        def upd(s):
            ctx.update_config({"_cache_status": s})
        emby_set = set()
        # 优先从数据库读
        db_path = str(cfg.get("emby_db_path", "") or "").strip()
        if db_path:
            upd("正在读取 Emby 数据库...")
            emby_set = await _fetch_emby_from_db(db_path, ctx.log)
        if not emby_set and cfg.get("emby_url") and cfg.get("emby_api_key"):
            ctx.kv.set("my115scan_building_cache", True)
            try:
                upd("正在拉取 Emby 全量清单...")
                emby_set = await _fetch_emby_ids(cfg["emby_url"], cfg["emby_api_key"], ctx.log, upd)
            finally:
                ctx.kv.set("my115scan_building_cache", False)
        if emby_set:
            ctx.kv.set("my115scan_emby_set", ",".join(str(x) for x in emby_set))
            ctx.kv.set("my115scan_cache_size", len(emby_set))
            upd(f"缓存就绪: {len(emby_set)}个ID")
            return {"ok": True, "status": f"缓存就绪: {len(emby_set)}个ID"}
        else:
            upd("缓存建立失败")
            return {"ok": False, "status": "缓存建立失败"}

    @ctx.on_api("/cache_status", methods=["GET"])
    async def _api_cache_status(req):
        status = ctx.config.get("_cache_status", "")
        if not status:
            size = int(ctx.kv.get("my115scan_cache_size", 0) or 0)
            status = f"缓存就绪: {size}个ID" if size else "未建立"
        return {"status": status}


async def _fetch_emby_from_db(db_path, _log=None) -> set:
    """直接从 Emby library.db 读取所有 TMDB ID"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # 探测表名和列名
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0].lower() for r in c.fetchall()]
        if _log:
            _log.info("[115扫描] 数据库表: %s", tables[:30])
        ids = set()
        # MediaItems 表（区分大小写）
        c.execute("PRAGMA table_info(MediaItems)")
        mcols = [r[1] for r in c.fetchall()]
        if "ProviderIds" in mcols:
            try:
                # ProviderIds 格式: Tmdb=10092|Imdb=tt0384286|...
                sql = "SELECT DISTINCT CAST(SUBSTR(ProviderIds, INSTR(ProviderIds, 'Tmdb=') + 5) AS INTEGER) "
                sql += "FROM MediaItems WHERE ProviderIds LIKE '%Tmdb=%'"
                c.execute(sql)
                for r in c.fetchall():
                    if r[0] and r[0] > 0:
                        ids.add(int(r[0]))
                if _log:
                    _log.info("[115扫描] MediaItems.ProviderIds 找到 %d 个 TMDB ID", len(ids))
            except Exception as e:
                if _log:
                    _log.info("[115扫描] ProviderIds 查询失败: %r", e)
        conn.close()
        if _log:
            _log.info("[115扫描] ✅ 数据库共读取 %d 个 TMDB ID", len(ids))
        return ids
    except Exception as e:
        if _log:
            _log.warning("[115扫描] 数据库读取失败: %r", e)
        return set()


async def _fetch_emby_ids(emby_url, emby_key, _log=None, _update_status=None) -> set:
    """分批拉取 Emby 全部资源的 TMDB ID，返回集合（超时重试3次）"""
    import httpx
    base = f"{emby_url.rstrip('/')}/emby/Items"
    ids = set()
    page = 0
    page_size = 500
    max_retries = 3
    if _log:
        _log.info("[115扫描] 正在分批拉取 Emby 全量清单...")
    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            while True:
                params = {
                    "Recursive": "true", "Fields": "ProviderIds",
                    "api_key": emby_key,
                    "StartIndex": page * page_size,
                    "Limit": page_size,
                }
                retries = 0
                while retries <= max_retries:
                    try:
                        r = await cli.get(base, params=params)
                        r.raise_for_status()
                        break  # 成功，跳出重试循环
                    except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                        retries += 1
                        if retries > max_retries:
                            raise  # 重试用完，向上抛
                        wait = retries * 5
                        if _log:
                            _log.warning("[115扫描] 第%d页超时(第%d次重试)，%ds后重试...",
                                        page + 1, retries, wait)
                        if _update_status:
                            _update_status(f"拉取缓存第{page+1}页超时，重试{retries}/{max_retries}")
                        await asyncio.sleep(wait)
                data = r.json()
                items = data.get("Items") or []
                total = data.get("TotalRecordCount", 0)
                for item in items:
                    pid = (item.get("ProviderIds") or {})
                    tid = pid.get("Tmdb")
                    if tid:
                        ids.add(int(tid))
                page += 1
                if _update_status:
                    _update_status(f"拉取Emby缓存: {min(page * page_size, total)}/{total}")
                if _log and page % 5 == 0:
                    _log.info("[115扫描] Emby 拉取进度: %d/%d, 已收集 %d 个 TMDB ID",
                              min(page * page_size, total), total, len(ids))
                if page * page_size >= total:
                    break
        if _log:
            _log.info("[115扫描] ✅ Emby 全量拉取完成，共 %d 个 TMDB ID（%d页）", len(ids), page)
        if _update_status:
            _update_status(f"Emby缓存就绪: {len(ids)}个ID")
        return ids
    except httpx.HTTPStatusError as e:
        if _log:
            _log.warning("[115扫描] Emby 拉取 HTTP %s: %s", e.response.status_code, e.response.text[:200])
            _log.info("[115扫描] ⚠️ Emby 缓存拉取未完成，将使用逐条查询")
        if _update_status:
            _update_status("Emby缓存失败(HTTP错误)")
    except httpx.TimeoutException:
        if _log:
            _log.warning("[115扫描] Emby 拉取超时(重试%d次后放弃)，进度 %d/%d",
                         max_retries, page * page_size, total if 'total' in dir() else '?')
        if _update_status:
            _update_status("Emby缓存失败(超时)")
    except Exception as e:
        if _log:
            _log.warning("[115扫描] Emby 拉取失败: %r", e)
            _log.info("[115扫描] ⚠️ 将使用逐条查询 Emby")
        if _update_status:
            _update_status("Emby缓存失败")
    # 超时/失败时不返回部分数据，避免漏查
    return set()


async def _do_scan(ctx, src):
    """扫描历史消息"""
    try:
        apps = list(ctx.user_apps or [])
        if not apps:
            ctx.log.error("[115扫描] 没有可用用户账号")
            ctx.update_config({"_scan_status": "失败：无可用账号"})
            return
        client = apps[0]
        cfg = _effective_cfg(ctx)
        # 读取 Emby 缓存（从 KV 或数据库直读）
        cache_raw = ctx.kv.get("my115scan_emby_set", "")
        if cache_raw:
            emby_set = set(int(x) for x in cache_raw.split(",") if x.strip().isdigit())
            if emby_set:
                cfg["_emby_set"] = emby_set
                ctx.log.info("[115扫描] 使用 Emby 缓存查重，共 %d 个 ID", len(emby_set))
        delay = int(cfg.get("delay", 2) or 2)
        batch = int(cfg.get("batch_size", 200) or 200)
        last_id = int(ctx.kv.get("my115scan_last_id", 0) or 0)
        total = int(ctx.kv.get("my115scan_total", 0) or 0)
        forwarded = int(ctx.kv.get("my115scan_forwarded", 0) or 0)
        ctx.log.info("[115扫描] 开始: 来源%s, 每批%s条, 间隔%s秒, only_complete_series=%s", src, batch, delay, cfg.get("only_complete_series", "N/A"))

        processed = 0
        offset = last_id if last_id > 0 else 0
        ids = []
        from pyrogram.raw.functions.messages import GetHistory
        while True:
            ctx.log.info("[115扫描] DEBUG offset=%s", offset)
            if ctx.kv.get("my115scan_stop", False):
                break
            peer = await client.resolve_peer(src)
            raw = await client.invoke(GetHistory(
                peer=peer, offset_id=offset, offset_date=0,
                add_offset=0, limit=100, max_id=0, min_id=0, hash=0,
            ))
            msgs = [m for m in raw.messages if hasattr(m, 'id')]
            if not msgs:
                ctx.log.info("[115扫描] 结束: API返回空消息")
                break
            ids = [m.id for m in msgs]
            ctx.log.info("[115扫描] 拉取: offset_id=%s, %d条, 范围=%s-%s, 新offset=%s",
                         offset, len(ids), ids[0], ids[-1], ids[-1])
            offset = ids[-1]
            for mid in reversed(ids):
                if ctx.kv.get("my115scan_stop", False):
                    break
                try:
                    msg = await client.get_messages(src, mid)
                    if not msg:
                        continue
                    if isinstance(msg, list):
                        msg = msg[0] if msg else None
                    if not msg:
                        continue
                    await _process(client, cfg, msg, ctx)
                    total += 1
                except Exception as e:
                    ctx.log.warning("[115扫描] 消息%s异常: %r", mid, e)
                await asyncio.sleep(delay)
                processed += 1
                if processed % 50 == 0:
                    ctx.log.info("[115扫描] 进度: %d条, 最后ID=%s", total, mid)
            ctx.kv.set("my115scan_last_id", ids[-1])
            ctx.kv.set("my115scan_total", total)
            ctx.kv.set("my115scan_forwarded", forwarded)
            ctx.log.info("[115扫描] 一批完成, offset=%s, %d条, 总计%d条", offset, len(ids), total)
            if len(ids) == 0:
                break

        ctx.kv.set("my115scan_last_id", ids[-1] if ids else 0)
        ctx.kv.set("my115scan_total", total)
        ctx.kv.set("my115scan_forwarded", forwarded)
        ctx.log.info("[115扫描] ✅ 完成, 扫描%d条, 最后offset=%s", total, offset)
        ctx.update_config({"_scan_status": f"完成: {total}条"})
    except asyncio.CancelledError:
        ctx.log.warning("[115扫描] 扫描任务被取消")
        ctx.update_config({"_scan_status": "已取消"})
        raise
    except Exception as e:
        ctx.log.error("[115扫描] 异常: %r", e)
        import traceback
        ctx.log.error("[115扫描] 堆栈: %s", traceback.format_exc())
        ctx.update_config({"_scan_status": f"异常: {e}"})
    finally:
        ctx.log.info("[115扫描] cleanup done")

