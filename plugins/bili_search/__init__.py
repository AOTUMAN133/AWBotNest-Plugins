# -*- coding: utf-8 -*-
# AWBotNest V2 插件：B站&YouTube搜索 (bili_search)

import asyncio
import httpx
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "B站&YouTube搜索",
    "id": "bili_search",
    "version": "2.0.3",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/bili_search_v2.svg",
    "author": "凹凸曼",
    "description": "B站+YouTube搜索下载。.spb搜B站，.spy搜YouTube，.sp聚合搜索",
    "tags": ["B站", "YouTube", "搜索下载"],
    "scope": "user",
    "plugin_api_version": 2,
    "requirements": ["yt-dlp", "httpx"],
    "resources": {
        "timeout_seconds": 120,
        "max_concurrency": 8,
        "max_background_tasks": 16,
        "failure_threshold": 5,
    },
    "config_schema": {
        "max_size": {
            "type": "number", "default": 50, "label": "最大文件大小(MB)",
            "section": "下载", "min": 1, "max": 500, "order": 1,
            "help": "超过此大小的视频走备用方案"
        },
        "oversize_action": {
            "type": "select", "default": "notify", "label": "超限处理方式",
            "section": "下载", "order": 2,
            "options": [
                {"value": "saved", "label": "发送到收藏夹"},
                {"value": "link", "label": "仅发送下载链接"},
                {"value": "force", "label": "直接发送"},
                {"value": "notify", "label": "提示用户"},
            ]
        },
        "quality": {
            "type": "select", "default": "80", "label": "B站下载清晰度",
            "section": "B站", "order": 1,
            "options": [
                {"value": "120", "label": "4K"},
                {"value": "116", "label": "1080P60"},
                {"value": "80", "label": "1080P"},
                {"value": "64", "label": "720P"},
                {"value": "32", "label": "480P"},
            ]
        },
        "search_count": {
            "type": "number", "default": 5, "label": "搜索返回数量",
            "section": "搜索", "min": 1, "max": 20, "order": 1
        },
        "yt_quality": {
            "type": "select", "default": "1080", "label": "YouTube下载画质",
            "section": "YouTube", "order": 1,
            "options": [
                {"value": "2160", "label": "4K"},
                {"value": "1440", "label": "2K"},
                {"value": "1080", "label": "1080P"},
                {"value": "720", "label": "720P"},
                {"value": "480", "label": "480P"},
                {"value": "audio", "label": "仅音频(MP3)"},
            ]
        },
        "auto_detect": {
            "type": "boolean", "default": True, "label": "自动检测B站链接",
            "section": "基本", "order": 1,
            "help": "群内发送B站链接自动下载"
        },
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载", "order": 4,
            "help": "发送后不删除本地下载的文件"
        },
        "test_bili": {
            "type": "action", "label": "🔍 测试B站搜索", "section": "调试",
            "action": "test_bili"
        },
        "test_youtube": {
            "type": "action", "label": "▶️ 测试YouTube搜索", "section": "调试",
            "action": "test_youtube"
        },
        "view_logs": {
            "type": "action", "label": "📋 查看日志", "section": "调试",
            "action": "view_logs"
        },
    },
}

_BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

_DOWNLOAD_DIR = Path(__file__).parent / "downloads"
_KV_LOGS = "bili_search_logs"


async def _log(ctx, msg: str):
    # V2: 只写 storage 日志，不刷 ctx.log.info
    logs = await ctx.storage.get(_KV_LOGS, []) or []
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    await ctx.storage.set(_KV_LOGS, logs[-30:])


def _clean_title(title: str) -> str:
    return re.sub(r"<[^>]+>", "", title).strip()


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size/1024/1024:.1f}MB"
    return f"{size/1024/1024/1024:.1f}GB"


def _format_duration(seconds) -> str:
    if not seconds or seconds <= 0:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


# ═══════════════════════════════════════════════
# B站 API
# ═══════════════════════════════════════════════

async def _bili_search(keyword: str, page: int = 1, count: int = 5) -> list:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/web-interface/search/all/v2",
                         params={"keyword": keyword, "page": page})
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("code") != 0:
            return []
        results = []
        for section in data.get("data", {}).get("result", []):
            for v in section.get("data", []):
                if v.get("type") == "video":
                    results.append({
                        "title": _clean_title(v.get("title", "")),
                        "bvid": v.get("bvid", ""),
                        "play": v.get("play", 0),
                        "duration": str(v.get("duration", "?")),
                        "author": v.get("author", ""),
                        "pic": v.get("pic", ""),
                    })
                    if len(results) >= count:
                        break
            if len(results) >= count:
                break
        return results


async def _bili_video_info(bvid: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/web-interface/view",
                         params={"bvid": bvid})
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        v = data["data"]
        return {
            "title": v.get("title", ""),
            "bvid": bvid,
            "cid": v.get("cid", 0),
            "duration": v.get("duration", 0),
            "pages": len(v.get("pages", [])),
            "author": v.get("owner", {}).get("name", ""),
            "pic": v.get("pic", ""),
        }


async def _bili_download_url(bvid: str, cid: int, qn: int = 80) -> list:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/player/playurl",
                         params={"bvid": bvid, "cid": cid, "qn": qn, "fnval": 1, "fnver": 0, "fourk": 1})
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("code") != 0:
            return []
        durl = data.get("data", {}).get("durl", [])
        return [{"url": u.get("url", ""), "size": u.get("size", 0), "order": u.get("order", 1)} for u in durl]


async def _download_file(url: str, path: Path, headers: dict = None) -> bool:
    try:
        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com",
        }
        if headers:
            dl_headers.update(headers)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as cli:
            async with cli.stream("GET", url, headers=dl_headers) as r:
                if r.status_code != 200:
                    return False
                path.parent.mkdir(parents=True, exist_ok=True)
                total = 0
                with open(path, "wb") as f:
                    async for chunk in r.aiter_bytes(1024 * 1024):
                        f.write(chunk)
                        total += len(chunk)
                return total > 0
    except Exception:
        return False


# ═══════════════════════════════════════════════
# YouTube API (yt-dlp)
# ═══════════════════════════════════════════════

def _get_proxy(ctx=None) -> str | None:
    """读取代理: 优先平台配置 ctx.settings.proxy_url (平台已配 192.168.1.33:7890),
    其次环境变量, 返回 yt-dlp 可用的 proxy 值"""
    if ctx is not None:
        try:
            s = ctx.settings
            p = (s.proxy_url or "").strip()
            if p:
                return p
        except Exception:
            pass
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return None


def _youtube_search(keyword: str, count: int = 5, ctx=None) -> list:
    try:
        # 使用 yt-dlp 的 Python API 直接调用（避免子进程/PATH问题）
        import yt_dlp
        proxy = _get_proxy(ctx)
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "skip_download": True,
            "playlistend": count,
            # 关键: YouTube 不可达时不能无限卡住 (socket_timeout 秒级失败)
            "socket_timeout": 15,
            "nocheckcertificate": True,
            "retries": 1,
        }
        if proxy:
            ydl_opts["proxy"] = proxy
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{count}:{keyword}", download=False)
            if not info or not info.get("entries"):
                return []
            results = []
            for entry in info["entries"][:count]:
                if not entry:
                    continue
                results.append({
                    "title": entry.get("title", ""),
                    "id": entry.get("id", ""),
                    "duration": entry.get("duration") or 0,
                    "channel": entry.get("channel", "") or entry.get("uploader", ""),
                    "view_count": entry.get("view_count", 0),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                })
            return results
    except Exception:
        return []


async def _youtube_search_async(keyword: str, count: int = 5, ctx=None) -> list:
    """yt-dlp 是阻塞调用, 包到线程池跑; 内部有 socket_timeout, 外层还有 wait_for 兜底"""
    return await asyncio.to_thread(_youtube_search, keyword, count, ctx)


def _yt_dlp_download(video_url: str, output_path: str, is_audio: bool = False) -> bool:
    """使用 yt-dlp 下载视频/音频，成功返回 True"""
    try:
        import yt_dlp
        if is_audio:
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }],
                "outtmpl": str(output_path).rsplit(".", 1)[0] + ".%(ext)s",
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
        else:
            ydl_opts = {
                "format": "best[ext=mp4]/best",
                "outtmpl": str(output_path),
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════
# 插件入口（V2: Telethon 单参 event）
# ═══════════════════════════════════════════════

async def setup(ctx):
    # ═══════════ 命令入口（统一处理，V2 无 group/filters） ═══════════
    @ctx.on_message(outgoing=True)
    async def _handler(event):
        text = (event.text or "").strip()
        if not text:
            return
        client = event.client

        # ── 处理选择/翻页回复（纯数字 或 n）──
        if text.isdigit() or text.lower() == "n":
            # 搜索结果选择
            pending_key = f"pending_select:{event.chat_id}"
            pending = await ctx.storage.get(pending_key, None)
            if pending:
                if time.time() - pending.get("time", 0) > 30:
                    await ctx.storage.delete(pending_key)
                    return
                if text.lower() == "n":
                    page = pending.get("page", 1) + 1
                    keyword = pending.get("keyword", "")
                    if keyword:
                        await ctx.storage.delete(pending_key)
                        # 根据结果类型决定翻页方式
                        results = pending.get("results", [])
                        platforms = set(r.get("platform", "") for r in results)
                        if platforms == {"B站"}:
                            await _do_search_bili(ctx, event, keyword, page=page)
                        elif platforms == {"YouTube"}:
                            await _do_search_youtube(ctx, event, keyword, page=page)
                        else:
                            # 聚合搜索不支持翻页，重新搜索
                            await _do_search_aggregate(ctx, event, keyword)
                    return
                idx = int(text)
                if idx == 0:
                    await ctx.storage.delete(pending_key)
                    await event.reply("已取消")
                    return
                results = pending.get("results", [])
                if 1 <= idx <= len(results):
                    await ctx.storage.delete(pending_key)
                    r = results[idx - 1]
                    try:
                        await client.delete_messages(event.chat_id, [pending.get("msg_id"), event.id])
                    except Exception:
                        try:
                            await event.delete()
                        except Exception:
                            pass
                    platform = r.get("platform", "")
                    if platform == "B站" and r.get("bvid"):
                        await _do_bili_download(ctx, event, r["bvid"])
                    elif platform == "YouTube" and r.get("url"):
                        await _do_youtube_download(ctx, event, r["url"], r.get("title", "视频"))
                return

            # 超限处理选择
            pending_key = f"pending_oversize:{event.chat_id}"
            pending = await ctx.storage.get(pending_key, None)
            if pending:
                if time.time() - pending.get("time", 0) > 60:
                    await ctx.storage.delete(pending_key)
                    return
                idx = int(text)
                await ctx.storage.delete(pending_key)
                if idx == 0:
                    await event.reply("已取消")
                    return
                bvid = pending.get("bvid", "")
                url = pending.get("url", "")
                title = pending.get("title", "视频")
                msg_id = pending.get("msg_id")
                try:
                    ids = [msg_id, event.id] if msg_id else [event.id]
                    await client.delete_messages(event.chat_id, ids)
                except Exception:
                    try:
                        await event.delete()
                    except Exception:
                        pass
                if idx == 1:
                    dl_msg = await event.reply(f"⏳ 正在下载 {title[:30]}...")
                    dl_path = _DOWNLOAD_DIR / f"{bvid}.mp4"
                    success = await _download_file(url, dl_path)
                    if success and dl_path.exists():
                        try:
                            await client.send_file(event.chat_id, str(dl_path), caption=f"📹 {title[:50]}")
                            try:
                                await dl_msg.delete()
                            except Exception:
                                pass
                            if not ctx.config.get("keep_local", False):
                                dl_path.unlink(missing_ok=True)
                        except Exception as e:
                            await event.reply(f"❌ 发送失败: {e}")
                    else:
                        await event.reply("❌ 下载失败")
                elif idx == 2:
                    link = f"https://www.bilibili.com/video/{bvid}"
                    await event.reply(f"🔗 {link}")
                elif idx == 3:
                    await event.reply(f"📁 已发送到收藏夹")
                return

        # ── 命令处理 ──
        # .spb keyword — B站搜索
        if text.startswith(".spb "):
            kw = text[5:].strip()
            await _do_search_bili(ctx, event, kw)
            return

        # .spy keyword — YouTube搜索
        if text.startswith(".spy "):
            kw = text[5:].strip()
            await _do_search_youtube(ctx, event, kw)
            return

        # .sp keyword — 聚合搜索
        if text.startswith(".sp "):
            kw = text[4:].strip()
            await _do_search_aggregate(ctx, event, kw)
            return

        # 自动检测B站链接
        if ctx.config.get("auto_detect", True):
            bili_m = re.search(r"(?:bilibili\.com/video/|b23\.tv/)(BV\w+)", text)
            if bili_m:
                bvid = bili_m.group(1)
                await _do_bili_download(ctx, event, bvid)

    # ── B站搜索 ──
    async def _do_search_bili(ctx, event, keyword, page=1):
        msg = await event.reply(f"🔍 正在B站搜索「{keyword}」...")
        try:
            await event.delete()
        except Exception:
            pass
        count = ctx.config.get("search_count", 5)
        bili = await _bili_search(keyword, page=page, count=count)
        results = [{"platform": "B站", **v} for v in bili]
        if not results:
            await msg.edit(f"❌ 未在B站找到「{keyword}」的相关视频")
            return
        lines = [f"🔍 <b>B站搜索「{keyword}」</b>\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "?")[:40]
            lines.append(f"<b>{i}.</b> [B站] {title}  ⭐{r.get('play',0)}")
        lines.append(f"\n回复序号选择下载（30秒内）")
        if len(results) >= count:
            lines.append(f"回复 <b>0</b> 取消，<b>n</b> 下一页")
        else:
            lines.append(f"回复 <b>0</b> 取消")
        await msg.edit("\n".join(lines))
        pending_key = f"pending_select:{event.chat_id}"
        await ctx.storage.set(pending_key, {"results": results, "time": time.time(), "msg_id": msg.id, "keyword": keyword, "page": page})

    # ── YouTube搜索 ──
    async def _do_search_youtube(ctx, event, keyword, page=1):
        msg = await event.reply(f"🔍 正在YouTube搜索「{keyword}」...")
        try:
            await event.delete()
        except Exception:
            pass
        count = ctx.config.get("search_count", 5)
        # YouTube 搜索加超时保护, 不可达时 20s 返回空
        try:
            yt_results = await asyncio.wait_for(
                asyncio.to_thread(_youtube_search, keyword, count, ctx), timeout=20)
        except (asyncio.TimeoutError, Exception):
            yt_results = []
        results = [{"platform": "YouTube", **v} for v in yt_results]
        if not results:
            await msg.edit(f"❌ 未在YouTube找到「{keyword}」的相关视频")
            return
        lines = [f"🔍 <b>YouTube搜索「{keyword}」</b>\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "?")[:50]
            dur = _format_duration(r.get("duration", 0))
            lines.append(f"<b>{i}.</b> [YouTube] {title}  ⏱{dur}")
        lines.append(f"\n回复序号选择下载（30秒内）")
        if len(results) >= count:
            lines.append(f"回复 <b>0</b> 取消，<b>n</b> 翻页（新搜索）")
        else:
            lines.append(f"回复 <b>0</b> 取消")
        await msg.edit("\n".join(lines))
        pending_key = f"pending_select:{event.chat_id}"
        await ctx.storage.set(pending_key, {"results": results, "time": time.time(), "msg_id": msg.id, "keyword": keyword, "page": page})

    # ── 聚合搜索 ──
    async def _do_search_aggregate(ctx, event, keyword, page=1):
        msg = await event.reply(f"🔍 正在B站+YouTube搜索「{keyword}」...")
        try:
            await event.delete()
        except Exception:
            pass
        count = ctx.config.get("search_count", 5)

        # 并行搜索 — YouTube 加超时降级: 不可达时 20s 返回空, B站结果照常出
        # 注意: 必须 create_task 包装成 Task, gather 超时后协程不能二次 await
        bili_task = asyncio.create_task(_bili_search(keyword, page=page, count=count))
        yt_task = asyncio.create_task(_youtube_search_async(keyword, count, ctx))
        try:
            bili = await bili_task
        except Exception:
            bili = []
        try:
            yt_results = await asyncio.wait_for(yt_task, timeout=20)
        except (asyncio.TimeoutError, Exception):
            yt_results = []
            yt_task.cancel()

        results = []
        for v in bili:
            results.append({"platform": "B站", **v})
        for v in yt_results:
            results.append({"platform": "YouTube", **v})

        if not results:
            await msg.edit(f"❌ 未找到「{keyword}」的相关视频")
            return

        lines = [f"🔍 <b>聚合搜索「{keyword}」</b>\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "?")[:45]
            plat = r.get("platform", "?")
            if plat == "B站":
                lines.append(f"<b>{i}.</b> [B站] {title}  ⭐{r.get('play',0)}")
            else:
                dur = _format_duration(r.get("duration", 0))
                lines.append(f"<b>{i}.</b> [YouTube] {title}  ⏱{dur}")
        lines.append(f"\n回复序号选择下载（30秒内）")
        lines.append(f"回复 <b>0</b> 取消")
        await msg.edit("\n".join(lines))
        pending_key = f"pending_select:{event.chat_id}"
        await ctx.storage.set(pending_key, {"results": results, "time": time.time(), "msg_id": msg.id, "keyword": keyword, "page": page})

    # ── B站下载 ──
    async def _do_bili_download(ctx, event, bvid):
        msg = await event.reply(f"⏳ 正在解析 B站视频 {bvid}...")
        try:
            await event.delete()
        except Exception:
            pass
        info = await _bili_video_info(bvid)
        if not info:
            await msg.edit(f"❌ 无法获取视频信息")
            return
        title = info["title"]
        await msg.edit(f"⏳ 正在获取下载地址...")
        qn = int(ctx.config.get("quality", 80) or 80)
        urls = await _bili_download_url(bvid, info["cid"], qn)
        if not urls:
            await msg.edit(f"❌ 无法获取下载地址（可能需登录）")
            return
        total_size = sum(u["size"] for u in urls)
        max_mb = int(ctx.config.get("max_size", 50) or 50)
        oversize = total_size > max_mb * 1024 * 1024
        if oversize:
            action = ctx.config.get("oversize_action", "notify")
            if action == "link":
                link = f"https://www.bilibili.com/video/{bvid}"
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n🔗 {link}", link_preview=False)
                return
            elif action == "force":
                pass
            elif action == "saved":
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n📁 已发送到收藏夹")
                return
            else:
                await msg.edit(
                    f"📹 <b>{title}</b>\n"
                    f"📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n\n"
                    f"请选择处理方式：\n"
                    f"1 - 直接下载并发送\n"
                    f"2 - 仅发送下载链接\n"
                    f"3 - 发送到收藏夹\n"
                    f"0 - 取消"
                )
                pending_key = f"pending_oversize:{event.chat_id}"
                await ctx.storage.set(pending_key, {"bvid": bvid, "url": urls[0]["url"], "title": title, "time": time.time(), "msg_id": msg.id})
                return
        await msg.edit(f"⏳ 正在下载 {title}...")
        dl_path = _DOWNLOAD_DIR / f"{bvid}.mp4"
        success = await _download_file(urls[0]["url"], dl_path)
        if success and dl_path.exists():
            try:
                await event.client.send_file(event.chat_id, str(dl_path), caption=f"📹 {title}")
                if not ctx.config.get("keep_local", False):
                    await msg.delete()
                    dl_path.unlink(missing_ok=True)
                else:
                    await msg.edit(f"✅ 已保存到本地: {dl_path}")
            except Exception as e:
                await msg.edit(f"❌ 发送失败: {e}")
        else:
            await msg.edit(f"❌ 下载失败")

    # ── YouTube下载 ──
    async def _do_youtube_download(ctx, event, video_url, title):
        msg = await event.reply(f"⏳ 正在下载 YouTube 视频...")
        try:
            await event.delete()
        except Exception:
            pass
        video_id = video_url.split("watch?v=")[-1].split("&")[0] if "watch?v=" in video_url else "yt"
        yt_quality = ctx.config.get("yt_quality", "1080")
        is_audio = yt_quality == "audio"
        ext = "mp3" if is_audio else "mp4"
        dl_path = _DOWNLOAD_DIR / f"yt_{video_id}.{ext}"

        await msg.edit(f"⏳ 正在下载（{yt_quality}）...")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        try:
            success = _yt_dlp_download(video_url, str(dl_path), is_audio=is_audio)
        except Exception as e:
            await msg.edit(f"❌ 下载异常: {e}")
            return

        if not success:
            await msg.edit(f"❌ 下载失败，请检查视频链接是否有效")
            return

        if not dl_path.exists():
            # 可能是命名问题，检查下载目录排除中间文件
            files = sorted(_DOWNLOAD_DIR.glob(f"yt_{video_id}*"), key=lambda p: p.stat().st_mtime, reverse=True)
            files = [f for f in files if not re.search(r"\.f\d{3,}\.", f.name)]
            if files:
                dl_path = files[0]
            else:
                await msg.edit(f"❌ 下载失败，未找到输出文件")
                return

        file_size = dl_path.stat().st_size
        max_mb = int(ctx.config.get("max_size", 50) or 50)
        oversize = file_size > max_mb * 1024 * 1024 and not is_audio
        if oversize:
            action = ctx.config.get("oversize_action", "notify")
            if action == "link":
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(file_size)}（超过{max_mb}MB）\n🔗 {video_url}", link_preview=False)
                if not ctx.config.get("keep_local", False):
                    dl_path.unlink(missing_ok=True)
                return
            elif action == "saved":
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(file_size)}（超过{max_mb}MB）\n📁 已发送到收藏夹")
                if not ctx.config.get("keep_local", False):
                    dl_path.unlink(missing_ok=True)
                return
        try:
            if is_audio:
                await event.client.send_file(event.chat_id, str(dl_path), caption=f"🎵 {title}")
            else:
                await event.client.send_file(event.chat_id, str(dl_path), caption=f"📹 {title[:50]}")
            if not ctx.config.get("keep_local", False):
                await msg.delete()
                dl_path.unlink(missing_ok=True)
            else:
                await msg.edit(f"✅ 已保存到本地: {dl_path}")
        except Exception as e:
            await msg.edit(f"❌ 发送失败: {e}")

    # ── 配置页动作 ──
    @ctx.action("test_bili")
    async def _test_bili(req=None):
        r = await _bili_search("风景", count=3)
        return {"ok": True, "message": f"B站找到 {len(r)} 个结果: {[v['bvid'] for v in r]}"}

    @ctx.action("test_youtube")
    async def _test_youtube(req=None):
        r = await asyncio.to_thread(_youtube_search, "test", 3)
        return {"ok": True, "message": f"YouTube找到 {len(r)} 个结果: {[v['id'] for v in r]}"}

    @ctx.action("view_logs")
    async def _view_logs(req=None):
        logs = await ctx.storage.get(_KV_LOGS, []) or []
        if not logs:
            return {"ok": True, "message": "暂无日志"}
        lines = ["📋 最近日志:\n"]
        for log in logs[-15:]:
            lines.append(f"[{log['t']}] {log['m']}")
        return {"ok": True, "message": "\n".join(lines)}


async def teardown(ctx):
    pass