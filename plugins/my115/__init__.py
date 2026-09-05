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
import re
import time
from collections import deque
from datetime import datetime

from ._tmdb import TmdbApi, emby_has_tmdb_id, get_emby_tmdb_ids

__plugin__ = {
    "name": "115频道监控",
    "id": "my115",
    "version": "1.7.6",
    "changelog": "v1.7.6 修复单集误判完结\n- 修复：S01E12 单集发布被误判为整季完结（TMDB 对比只查结束集编号未查起始集）\n- 最后一季必须存在「从 E01 开始且覆盖全部集数」的完整范围才算完结\n- 连载单集/增量集数（S01E12、S03E07-E12）不再被误转存",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/my115_v2.svg",
    "author": "凹凸曼",
    "description": "通用监控频道里的 115 分享，读取/识别 TMDB 后查 Emby 媒体库，缺失的转发给 CMS 入库机器人。可选电影/电视剧，默认全部。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
    "plugin_api_version": 1,
    "min_platform_version": "1.1.4.0",
    "instance_mode": "shared",
    "resources": {
        "timeout_seconds": 120,
        "max_concurrency": 8,
        "max_background_tasks": 32,
        "failure_threshold": 5,
        "recovery_seconds": 60,
    },
    "requirements": ["httpx>=0.27"],
}

# ── 配置默认值 ──
DEFAULTS = {
    "shareswitch": False,
    "monitor_ids": "",
    "media_types": ["movie", "tv"],
    "only_complete_series": False,
    "tmdb_api_key": "",
    "tmdb_language": "zh-CN",
    "emby_url": "",
    "emby_api_key": "",
    "skip_emby_check": False,
    "cms_bot_username": "",
    "forward_label": "115 网盘",
    "dedup_hours": 24,
    "forward_to_saved": False,
    "pan115_cookie": "",
    "exclude_genres": "",
    "emby_check_cache_hours": 6,
}

# ── 运行态 ──
_logs = deque(maxlen=200)

# 链接匹配
_LINK_PATTERN = re.compile(
    r"https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s)\]】\"'<>，]+|"
    r"ed2k://\|file\|[^|]+\|[^|]+\|[^|]+\|/|"
    r"https?://telegra\.ph/[^\s\n\"'<>，]+|"
    r"magnet:\?xt=urn:[a-z0-9]+:[a-f0-9]+",
    re.IGNORECASE
)
_TMDB_ID_PATTERN = re.compile(r"TMDB\s*(?:ID)?\s*[:：]\s*(\d+)|tmdb-(\d+)", re.IGNORECASE)
_COMPLETE_PATTERN = re.compile(r"完结|全\s*\d+\s*[集話话]|全集|\(完|（完")
_GETMEDIA_TTL = 30


def _parse_season_ranges(text: str) -> list[tuple[int, int, int]]:
    """解析 S01E01-E27 / S01E01-E06 S02E01-E12 等季/集范围标注。
    返回 [(季号, 起始集, 结束集), ...]，无则空列表。
    注意：频道不标注「完结」只给 S 范围时，用它自行判断完结。"""
    ranges = []
    for m in re.finditer(r"[Ss](\d{1,2})\s*[Ee](\d{1,3})\s*(?:-\s*[Ee]?(\d{1,3}))?", text):
        s, e1 = int(m.group(1)), int(m.group(2))
        e2 = int(m.group(3) or m.group(2))
        if e2 >= e1:
            ranges.append((s, e1, e2))
    return ranges


def _complete_by_season_range(text: str, detail: dict) -> bool:
    """S 范围 vs TMDB：消息覆盖到最后一季的全部集数 → 视为完结。
    解决「频道只标 S01E01-E27 不写完结、TMDB 状态滞后(Returning)」的场景。
    必须存在从 E01 开始的完整范围（单集 S01E12 不算整季，连载中不判完结）。"""
    ranges = _parse_season_ranges(text)
    if not ranges:
        return False
    seasons = [s for s in (detail.get("seasons") or []) if s.get("season_number", 0) > 0]
    if not seasons:
        return False
    total_seasons = max(int(s["season_number"]) for s in seasons)
    max_season = max(r[0] for r in ranges)
    if max_season < total_seasons:
        return False  # 消息只覆盖部分季，剧还在更新
    last_season_eps = next(
        (int(s.get("episode_count") or 0) for s in seasons if s["season_number"] == max_season), 0)
    if last_season_eps <= 0:
        return False
    # 最后一季必须存在「从 E01 开始且覆盖全部集数」的完整范围；
    # S01E12 这类单集发布（start=12）或 S03E07-E12 增量（start=7）都不算
    return any(r[1] == 1 and r[2] >= last_season_eps for r in ranges if r[0] == max_season)


def _complete_by_season_range_heuristic(text: str) -> bool:
    """TMDB 查不到该剧时的兜底：所有 S 范围都从 E01 开始完整发布（整季合集）→ 视为完结。
    连载剧一般只发增量集数（起始集 > 1，如 S03E07-E12），不会误判。"""
    ranges = _parse_season_ranges(text)
    if not ranges:
        return False
    return all(r[1] == 1 for r in ranges)


def _effective_cfg(ctx) -> dict:
    return {**DEFAULTS, **dict(ctx.config or {})}


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
    links = []
    telegraph_links = []
    for m in found:
        link = m.group(0)
        if "telegra.ph" in link:
            telegraph_links.append(link)
        else:
            links.append(link)
    # 处理实体中的链接
    ents = getattr(message, "entities", []) or []
    cap_ents = getattr(message, "caption_entities", []) or []
    for e in ents + cap_ents:
        url = getattr(e, "url", None)
        if url and _LINK_PATTERN.match(url):
            if "telegra.ph" not in url:
                links.append(url)
            else:
                telegraph_links.append(url)
    return links, telegraph_links


def _extract_tmdb_id(text: str):
    m = _TMDB_ID_PATTERN.search(text)
    if m:
        # 两种捕获组：TMDB ID: 12345 或 tmdb-12345
        return int(m.group(1) or m.group(2))
    return None


def _guess_type(text: str):
    lower = text.lower()
    if any(k in lower for k in ["电影", "movie", "film"]):
        return "movie"
    if any(k in lower for k in ["剧集", "电视剧", "tv", "series"]):
        return "tv"
    # 检测单集格式
    if re.search(r"\bs\d+\s*e\d+", lower) or re.search(r"e\s*p\s*\d+", lower) or re.search(r"第\s*\d+\s*[集話话]", lower):
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
            ctx.log.error("[115监控] 解析转发目标失败 %s: %r", target, e)
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
        ctx.log.error("[115监控] 转发失败: %r", e)


async def _resolve_by_search(cfg, title, year, ctx):
    if not (cfg.get("tmdb_api_key") and title):
        return None, None
    api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
    try:
        result = await api.multi_search(title, year)
    except Exception as e:  # noqa: BLE001
        ctx.log.error("[115监控] TMDB 搜索失败: %r", e)
        return None, None
    if not result:
        return None, None
    first = result[0]
    tmdb_id = first.get("id")
    media_type = first.get("media_type")
    return tmdb_id, media_type


async def _emby_check_only(cfg, tmdb_id, media_type, text, ctx):
    """只有TMDB ID没有链接时，仅查Emby状态并记录"""
    if cfg.get("skip_emby_check", False):
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "已跳过查重(无链接)"})
        return
    emby_url = cfg.get("emby_url")
    emby_key = cfg.get("emby_api_key")
    if not emby_url or not emby_key:
        return
    # KV 缓存检查
    _cache_hours = int(cfg.get("emby_check_cache_hours", 6) or 6)
    _cache_key = f"my115_emby_has_{tmdb_id}"
    _cached = ctx.kv.get(_cache_key, "") or ""
    if _cached and time.time() - float(_cached) < _cache_hours * 3600:
        ctx.log.info("[115监控] Emby 已有(缓存) %d（无链接情报）", tmdb_id)
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby已有(缓存/无链接)"})
        return
    try:
        has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id)
        if has:
            ctx.log.info("[115监控] Emby 已有 %d（无链接情报）", tmdb_id)
            _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby已有(无链接)"})
            ctx.kv.set(_cache_key, str(time.time()))
        else:
            ctx.log.info("[115监控] ★ Emby 无 %d，需关注（无链接，无法自动转发）", tmdb_id)
            _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby未命中(无链接)"})
    except Exception as e:
        ctx.log.warning("[115监控] Emby 查询失败(无链接情报): %r", e)
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby查询失败"})

async def _process(client, cfg, message, ctx):
    links, telegraph_links = _extract_links(message)
    text = _msg_text(message)

    # 先提取 TMDB ID（即使没有链接也能处理）
    tmdb_id = _extract_tmdb_id(text)
    media_type = _guess_type(text)

    if not tmdb_id:
        title, year = _extract_title_year(text)
        tmdb_id, guessed_type = await _resolve_by_search(cfg, title, year, ctx)
        if not media_type:
            media_type = guessed_type

    if not links and not telegraph_links:
        # 没有链接但可能有 TMDB ID：只查 Emby 不转发
        if tmdb_id:
            ctx.log.info("[115监控] 无链接但有 TMDB=%d，仅查Emby状态", tmdb_id)
            await _emby_check_only(cfg, tmdb_id, media_type, text, ctx)
        else:
            # 诊断：无链接无TMDB，记录消息来源辅助排查（只在监控频道内，不刷屏）
            ctx.log.info("[115监控] 无链接消息: chat=%s text=%r",
                         message.chat.id, text[:80])
        return

    ctx.log.info("[115监控] 检测到 %d 条链接, %d 个 Telegraph 页面", len(links), len(telegraph_links))

    # 爬取 Telegraph 页面获取实际链接
    if telegraph_links:
        for tl in telegraph_links:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=15, verify=False) as cli:
                    r = await cli.get(tl)
                    if r.status_code == 200:
                        html = r.text
                        # 提取 ed2k 和 115 链接
                        page_links = re.findall(r"ed2k://\|file\|[^|]+\|[^|]+\|[^|]+\|/|https?://(?:[\w-]*115[\w-]*\.(?:com|cn)|anxia\.com|115cdn\.com)/s/[^\s<\"\\']+", html)
                        for pl in page_links:
                            if pl not in links:
                                links.append(pl)
                        ctx.log.info("[115监控] Telegraph 页面提取到 %d 条链接", len(page_links))
            except Exception as e:
                ctx.log.warning("[115监控] Telegraph 爬取失败: %r", e)

    if not tmdb_id:
        ctx.log.info("[115监控] 未识别 TMDB: %s", text[:50])
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": None, "action": "跳过"})
        return

    allowed = cfg.get("media_types", ["movie", "tv"])
    if media_type and media_type not in allowed:
        ctx.log.info("[115监控] 跳过类型 %s: %d", media_type, tmdb_id)
        _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "跳过"})
        return

    if media_type == "tv" and cfg.get("only_complete_series", False):
        # 先看消息文本有没有完结关键词（快速判断）
        if _COMPLETE_PATTERN.search(text):
            pass  # 文本明确写了完结
        else:
            # 文本没写完结：查 TMDB 确认；TMDB 状态滞后时用 S01E01-E27 结构自行判断
            detail = None
            try:
                api = TmdbApi(cfg["tmdb_api_key"], cfg.get("tmdb_language", "zh-CN"))
                detail = await api.get_details(tmdb_id, media_type)
            except Exception:  # noqa: BLE001
                detail = None
            if detail:
                if detail.get("status") in ("Ended", "Canceled", "Cancelled"):
                    pass  # TMDB 确认已完结
                elif detail.get("in_production") is False:
                    pass  # 不再制作中=完结
                elif _complete_by_season_range(text, detail):
                    ctx.log.info("[115监控] 剧集完结(S范围对比TMDB): %d", tmdb_id)
                else:
                    ctx.log.info("[115监控] 剧集未完结(TMDB), 跳过: %d", tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "跳过(未完结)"})
                    return
            else:
                # TMDB 查不到：S01E01-E27 结构启发式判断（整季合集=完结）
                if _complete_by_season_range_heuristic(text):
                    ctx.log.info("[115监控] 剧集完结(S结构启发式,TMDB无数据): %d", tmdb_id)
                else:
                    ctx.log.info("[115监控] 剧集未完结(文本/S结构), 跳过: %d", tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "跳过(未完结)"})
                    return

    if not cfg.get("skip_emby_check", False):
        emby_url = cfg.get("emby_url")
        emby_key = cfg.get("emby_api_key")
        if emby_url and emby_key:
            # ── KV 缓存：Emby 已确认有的 TMDB ID 不重复查（避免 13s+ 慢查询）──
            _cache_hours = int(cfg.get("emby_check_cache_hours", 6) or 6)
            _cache_key = f"my115_emby_has_{tmdb_id}"
            _cached = ctx.kv.get(_cache_key, "") or ""
            if _cached and time.time() - float(_cached) < _cache_hours * 3600:
                ctx.log.info("[115监控] Emby 已有(缓存) %d，跳过", tmdb_id)
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby已有(缓存)"})
                return
            try:
                has = await emby_has_tmdb_id(emby_url, emby_key, tmdb_id)
                if has:
                    ctx.log.info("[115监控] Emby 已有 %d，跳过", tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby已有"})
                    ctx.kv.set(_cache_key, str(time.time()))  # 缓存正结果
                    return
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "Emby未命中"})
            except Exception as e:  # noqa: BLE001
                err = str(e) or e.__class__.__name__
                ctx.log.warning("[115监控] Emby 查询失败: %r", e)
                _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": f"Emby查询失败({err[:30]})"})
                # Emby不可达时跳过转发并通知用户（每30分钟最多通知一次）
                _emby_notify_key = "my115_emby_down_notified"
                _notified_ts = ctx.kv.get(_emby_notify_key, 0) or 0
                if time.time() - _notified_ts > 1800:
                    ctx.notify(f"⚠️ 115频道监控：Emby 查询失败，请检查 Emby 状态\n({err[:80]})", level="warning")
                    ctx.kv.set(_emby_notify_key, time.time())
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
                for rule in exclude_list:
                    if rule.startswith("animation:") and is_animation:
                        country = rule.split(":", 1)[1]
                        origin = detail.get("origin_country") or []
                        if country == "cn" and "CN" in origin:
                            skip = True
                        elif country == "jp" and "JP" in origin:
                            # 日语原声且没有中文配音 → 跳过
                            langs = [l.get("iso_639_1","") for l in (detail.get("spoken_languages") or [])]
                            if "zh" not in langs:
                                skip = True
                        elif country == "us" and "US" in origin:
                            skip = True
                        elif country == "other" and origin:
                            if not any(c in origin for c in ("CN", "JP", "US")):
                                skip = True
                    elif rule in genre_names:
                        skip = True
                    if skip:
                        break

                if skip:
                    ctx.log.info("[115监控] 排除类型 %s: %d", exclude_raw, tmdb_id)
                    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "排除类型跳过"})
                    return
            except Exception:  # noqa: BLE001
                pass

    label = cfg.get("forward_label", "115 网盘")
    # 转发去重：同一TMDB ID在冷却期内不重复转发
    dedup_hours = int(cfg.get("dedup_hours", 24) or 24)
    if tmdb_id and dedup_hours > 0:
        dedup_key = f"my115_dedup_{tmdb_id}"
        last_ts = ctx.kv.get(dedup_key, 0) or 0
        now = time.time()
        if last_ts > 0 and (now - last_ts) < dedup_hours * 3600:
            ctx.log.info("[115监控] TMDB %d 在冷却期内(%sh)，跳过重复转发", tmdb_id, dedup_hours)
            _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "重复跳过"})
            return
        ctx.kv.set(dedup_key, now)
    await _send_links(client, cfg, links, label, ctx)
    ctx.log.info("[115监控] 已转发 TMDB %d: %s", tmdb_id, text[:30])
    _logs.append({"time": datetime.now().strftime("%H:%M:%S"), "title": text[:30], "tmdb_id": tmdb_id, "action": "转发"})


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
    m = re.search(r".find\s+(\d+)", text, re.IGNORECASE)
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
                ctx.log.warning("[115监控] Emby测试失败: %r", e)
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
        body = req if isinstance(req, dict) else {}
        if not body and hasattr(req, 'json'):
            body = req.json
        # shareswitch 从 enabled 推导
        body["shareswitch"] = body.get("shareswitch", True)
        ctx.update_config(body)
        return {"ok": True}

    # ───────── 监听 115 分享消息 ─────────
    _process_sem = asyncio.Semaphore(5)  # 最多5个并发处理

    @ctx.on_message(ctx.filters.text | ctx.filters.caption, group=7, target="both")
    async def monitor_channels(client, message):
        cfg = _effective_cfg(ctx)
        if not cfg.get("shareswitch", False):
            return
        monitor_ids = _monitor_ids(cfg)
        if monitor_ids and message.chat.id not in monitor_ids:
            return
        # 实时监听发布：立即推进轮询进度，轮询兜底不会再重复处理本条
        if monitor_ids:
            last_msg_key = f"my115_last_msg_{message.chat.id}"
            try:
                known = int(ctx.kv.get(last_msg_key, 0) or 0)
                if message.id > known:
                    ctx.kv.set(last_msg_key, str(message.id))
            except Exception as e:
                ctx.log.warning("[115监控] 更新轮询进度失败: %r", e)
        async with _process_sem:
            try:
                await _process(client, cfg, message, ctx)
            except Exception as e:
                ctx.log.error("[115监控] 处理消息异常: %r", e)

    # ───────── 低频兜底轮询：每5分钟增量拉取（正常应走 on_message 实时监听发布）─────────
    async def _poll_channels():
        """低频增量兜底，避免 on_message 漏消息时完全失明。
        高频轮询（30s）会触发 Telegram 限流导致频道静默哑火（v1.7.4 实测根因）。"""
        cfg = _effective_cfg(ctx)
        if not cfg.get("shareswitch", False):
            return
        monitor_ids = _monitor_ids(cfg)
        if not monitor_ids:
            return
        # 取用户账号发请求
        user_clients = ctx.user_apps
        if not user_clients:
            return
        client = user_clients[0]
        import time as _time
        for cid in monitor_ids:
            try:
                # 低频轮询：每频道至少 300s 查一次，避免触发限流
                poll_key = f"my115_poll_ts_{cid}"
                last_poll = ctx.kv.get(poll_key, 0) or 0
                if _time.time() - float(last_poll) < 300:
                    continue
                ctx.kv.set(poll_key, str(_time.time()))

                # 从最后已知消息ID之后增量拉取（limit=100 防一次发布多条遗漏）
                last_msg_key = f"my115_last_msg_{cid}"
                known_id = int(ctx.kv.get(last_msg_key, 0) or 0)
                newest_id = known_id
                async for msg in client.get_chat_history(cid, limit=100):
                    if msg.id <= known_id:
                        break
                    newest_id = max(newest_id, msg.id)
                    if msg.text or msg.caption:
                        ctx.log.info("[115监控] 轮询发现新消息 chat=%s id=%s text=%s", cid, msg.id, (msg.text or msg.caption or "")[:60])
                        async with _process_sem:
                            try:
                                await _process(client, cfg, msg, ctx)
                            except Exception as e:
                                ctx.log.error("[115监控] 轮询处理异常: %r", e)
                if newest_id > known_id:
                    ctx.kv.set(last_msg_key, str(newest_id))
            except Exception as e:
                # 拉取失败必须可见：未加入频道 / 限流(FloodWait) / 403 等
                ctx.log.error("[115监控] 轮询频道 %s 失败: %r", cid, e)

    ctx.schedule(_poll_channels, trigger="interval", seconds=300)

    # ───────── 命令：/getmedia 和 /find ─────────
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=-9)
    async def commands(client, message):
        text = message.text or ""
        if re.match(r"^[/\.]getmedia(?:\s|$)", text, re.IGNORECASE):
            await _cmd_getmedia(client, message, ctx)
        elif re.match(r"^[/\.]find(?:\s|$)", text, re.IGNORECASE):
            await _cmd_find(client, message, ctx)


async def teardown(ctx):
    pass
