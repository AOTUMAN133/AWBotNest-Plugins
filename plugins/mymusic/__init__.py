# -*- coding: utf-8 -*-
# AWBotNest V2 插件：音乐搜索下载 (mymusic) v2.0.0
# 聚合搜索：网易云/QQ/酷狗/酷我/咪咕 + YouTube，支持翻页、编号选择下载

import os
import re
import sys
import asyncio
import json
import subprocess
import shutil
import time
import importlib
from pathlib import Path
from datetime import datetime, timezone, timedelta

from telethon.tl.types import DocumentAttributeAudio

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path(__file__).parent / "downloads"
_BASE_DIR = Path(__file__).parent
_PAGE_SIZE = 5
_SEARCH_COUNT = 10

# 音源标识
SOURCE_YOUTUBE = "youtube"
SOURCE_AGGREGATE = "aggregate"
SOURCE_NETEASE = "netease"

# 聚合音源配置
SOURCES = {
    "netease": {"name": "网易云音乐", "cmd": "wy"},
    "qq": {"name": "QQ音乐", "cmd": "qq"},
    "kugou": {"name": "酷狗音乐", "cmd": "kg"},
    "kuwo": {"name": "酷我音乐", "cmd": "kw"},
    "migu": {"name": "咪咕音乐", "cmd": "mg"},
}

__plugin__ = {
    "name": "音乐搜索下载",
    "id": "mymusic",
    "version": "2.0.1",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "聚合搜索 5 音源（网易云/QQ/酷狗/酷我/咪咕）+ YouTube，支持 .yy 聚合搜索、.yyyt YouTube、.yywy 网易云等",
    "tags": ["音乐", "搜索", "下载"],
    "scope": "user",
    "plugin_api_version": 2,
    "requirements": ["yt-dlp>=2024.0.0", "aiohttp", "click", "json_repair", "rich"],
    "resources": {
        "timeout_seconds": 180,
        "max_concurrency": 8,
        "max_background_tasks": 32,
        "failure_threshold": 5,
    },
    "config_schema": {
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载",
            "help": "发送后不删除本地下载的文件"
        },
    },
}

# 插件日志区：运行明细写入 storage（供前端/排障读取），不刷平台日志；仅 error 级进平台日志
_LOG_KEY = "mymusic_logs"


async def _add_plugin_log(ctx, msg: str):
    """记录运行日志到插件日志区（storage），不刷平台运行日志"""
    try:
        logs = await ctx.storage.get(_LOG_KEY, []) or []
        if isinstance(logs, str):
            logs = json.loads(logs) if logs else []
        if not isinstance(logs, list):
            logs = []
        logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
        await ctx.storage.set(_LOG_KEY, logs[-100:])
    except Exception:
        pass


def _format_duration(seconds: int) -> str:
    m, s = divmod(int(seconds or 0), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_result_page(results: list, page: int, query: str, show_source: bool = True) -> str:
    """构建结果页，支持音源分组"""
    total = len(results)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    end = min(start + _PAGE_SIZE, total)

    lines = [f"🎵 <b>搜索结果: {query}</b>  ({page + 1}/{total_pages})\n"]
    last_source = None
    for i in range(start, end):
        r = results[i]
        source = r.get("_source_name", "")
        if show_source and source and source != last_source:
            lines.append(f"\n=== {source} ===")
            last_source = source
        title = r.get("title") or r.get("song_name") or r.get("name") or "未知"
        uploader = r.get("uploader") or r.get("artist") or "未知"
        if isinstance(uploader, list):
            uploader = "".join(uploader) if all(len(c) <= 2 for c in uploader) else ", ".join(uploader)
        dur = _format_duration(r.get("duration") or r.get("duration_s") or 0)
        lines.append(f"<b>{i + 1}.</b> {title}")
        lines.append(f"    👤 {uploader}  ⏱ {dur}\n")
    lines.append("💡 输入编号下载，<b>n</b> 下一页 <b>p</b> 上一页 <b>0</b> 取消")
    return "\n".join(lines)


def _yt_path() -> str:
    path = shutil.which("yt-dlp")
    if path:
        return path
    for p in [
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
        "/usr/bin/yt-dlp",
    ]:
        if os.path.isfile(p):
            return p
    return "yt-dlp"


# 检查 yt-dlp Python 模块是否可用（优先用 Python API，不依赖二进制路径）
HAS_YTDLP = False
try:
    import yt_dlp
    HAS_YTDLP = True
except Exception:
    pass


# 确保模块路径正确（平台通过 importlib 加载，可能不添加插件目录到 sys.path）
if str(_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(_BASE_DIR))

from _musicdl_engine import search as _musicdl_search_sync, get_url as _musicdl_url_sync, HAS_MUSICDL, get_import_error


async def _repair_deps(ctx):
    """后台修复依赖（pywidevine/ffmpeg）——不阻塞 setup, 修复完更新全局标志"""
    global HAS_YTDLP, HAS_MUSICDL, _musicdl_search_sync, _musicdl_url_sync, get_import_error

    # 检查 musicdl 引擎状态（pywidevine 修复）
    if not HAS_MUSICDL:
        await _add_plugin_log(ctx, f"musicdl 引擎不可用（{get_import_error()}），尝试修复 pywidevine...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "pywidevine>=1.9.0", "--upgrade", "-q"],
                capture_output=True, text=True, timeout=60
            )
            importlib.invalidate_caches()
            import _musicdl_engine as _me
            importlib.reload(_me)
            if _me.HAS_MUSICDL:
                globals()["HAS_MUSICDL"] = _me.HAS_MUSICDL
                globals()["_musicdl_search_sync"] = _me.search
                globals()["_musicdl_url_sync"] = _me.get_url
                globals()["get_import_error"] = _me.get_import_error
                await _add_plugin_log(ctx, "pywidevine 修复成功，musicdl 引擎已可用")
            else:
                await _add_plugin_log(ctx, f"pywidevine 修复后仍不可用: {_me.get_import_error()}")
        except Exception as e:
            await _add_plugin_log(ctx, f"pywidevine 修复失败: {e}；降级使用网易云 EAPI 搜索")

    # 检查 ffmpeg（仅在确实缺失时后台安装）
    if shutil.which("ffmpeg") is None:
        await _add_plugin_log(ctx, "ffmpeg 未找到，尝试后台安装...")
        try:
            subprocess.run(["apt-get", "install", "-y", "ffmpeg"], capture_output=True, text=True, timeout=180)
            if shutil.which("ffmpeg"):
                await _add_plugin_log(ctx, "ffmpeg 安装成功")
            else:
                await _add_plugin_log(ctx, "ffmpeg 安装完成但未生效（可能需要重启）")
        except Exception as e:
            await _add_plugin_log(ctx, f"ffmpeg 自动安装失败: {e}")


async def setup(ctx):
    await _add_plugin_log(ctx, "音乐搜索下载 v2.0.0 插件加载中")

    # 快速检查（不做耗时子进程调用, 避免超过平台 setup 30s 超时）
    global HAS_YTDLP
    if HAS_YTDLP:
        await _add_plugin_log(ctx, "yt-dlp Python 模块可用，YouTube 搜索可用")
    else:
        try:
            r = subprocess.run([_yt_path(), "--version"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                await _add_plugin_log(ctx, f"yt-dlp 二进制可用: {r.stdout.strip()}")
            else:
                await _add_plugin_log(ctx, "yt-dlp 未找到，YouTube 搜索不可用")
        except Exception:
            await _add_plugin_log(ctx, "yt-dlp 未找到，YouTube 搜索不可用")

    # 耗时修复(pywidevine/ffmpeg)丢后台, 不阻塞 setup
    ctx.create_task(_repair_deps(ctx), name="mymusic-repair-deps")

    # ── YouTube 搜索 ──
    async def _yt_search(ctx, event, keyword, page=1):
        msg = await event.reply(f"🔍 正在搜索 YouTube「{keyword}」...")
        try:
            await event.delete()
        except Exception:
            pass

        results = []
        if HAS_YTDLP:
            # 优先用 Python API（不依赖二进制路径）
            def _search():
                ydl_opts = {
                    "quiet": True, "no_warnings": True,
                    "extract_flat": "in_playlist", "skip_download": True,
                    "playlistend": _SEARCH_COUNT,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch{_SEARCH_COUNT}:{keyword}", download=False)
                if not info or not info.get("entries"):
                    return []
                out = []
                for entry in info["entries"][:_SEARCH_COUNT]:
                    if not entry:
                        continue
                    out.append({
                        "title": entry.get("title", "未知"),
                        "url": f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                        "duration": entry.get("duration") or 0,
                        "uploader": entry.get("channel", "") or entry.get("uploader", "未知"),
                        "id": entry.get("id", ""),
                        "_source": SOURCE_YOUTUBE,
                        "_source_name": "YouTube",
                    })
                return out
            try:
                results = await asyncio.get_running_loop().run_in_executor(None, _search)
            except Exception as e:
                await msg.edit(f"❌ YouTube 搜索失败: {e}")
                return
        else:
            # 兜底用二进制
            try:
                result = subprocess.run(
                    [_yt_path(), "--flat-playlist", "--dump-json", "--no-warnings", f"ytsearch{_SEARCH_COUNT}:{keyword}"],
                    capture_output=True, text=True, timeout=30,
                )
            except Exception as e:
                await msg.edit(f"❌ 搜索失败: {e}")
                return
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    results.append({
                        "title": data.get("title", "未知"),
                        "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                        "duration": data.get("duration", 0),
                        "uploader": data.get("uploader", "未知"),
                        "id": data.get("id", ""),
                        "_source": SOURCE_YOUTUBE,
                        "_source_name": "YouTube",
                    })
                except json.JSONDecodeError:
                    continue

        if not results:
            await msg.edit(f"❌ YouTube 未找到相关结果")
            return
        pending_key = f"pending_music:{event.chat_id}"
        await ctx.storage.set(pending_key, {"results": results, "page": 0, "query": keyword, "time": time.time(), "msg_id": msg.id, "source": SOURCE_YOUTUBE})
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── YouTube 下载 ──
    async def _yt_download(ctx, event, url, title, uploader=""):
        wait = await event.reply(f"⏳ 正在下载: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        template = str(_DOWNLOAD_DIR / "%(title)s.%(ext)s")

        if HAS_YTDLP:
            # 优先用 Python API
            def _download():
                if shutil.which("ffmpeg"):
                    ydl_opts = {
                        "format": "bestaudio/best",
                        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}],
                        "outtmpl": template, "quiet": True, "no_warnings": True, "noplaylist": True,
                    }
                else:
                    ydl_opts = {
                        "format": "bestaudio[ext=m4a]/bestaudio",
                        "outtmpl": template, "quiet": True, "no_warnings": True, "noplaylist": True,
                    }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            try:
                await asyncio.get_running_loop().run_in_executor(None, _download)
            except Exception as e:
                await wait.edit(f"❌ 下载异常: {e}")
                return
        else:
            # 兜底用二进制
            try:
                if shutil.which("ffmpeg"):
                    subprocess.run([_yt_path(), "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", template, "--no-playlist", "--no-warnings", url], capture_output=True, text=True, timeout=300)
                else:
                    subprocess.run([_yt_path(), "-f", "bestaudio[ext=m4a]/bestaudio", "-o", template, "--no-playlist", "--no-warnings", url], capture_output=True, text=True, timeout=300)
            except Exception as e:
                await wait.edit(f"❌ 下载异常: {e}")
                return
        audio_files = sorted(_DOWNLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        audio_files = [f for f in audio_files if f.suffix in (".mp3", ".webm", ".m4a", ".opus")]
        if not audio_files:
            await wait.edit("❌ 下载失败，未找到音频文件")
            return
        path = audio_files[0]
        await wait.edit(f"⏳ 正在发送: {title}")
        try:
            with open(path, "rb") as f:
                await event.client.send_file(
                    event.chat_id, f,
                    attributes=[DocumentAttributeAudio(duration=0, title=title, performer=uploader, voice=False)],
                )
            if not ctx.config.get("keep_local", False):
                path.unlink(missing_ok=True)
            await wait.delete()
        except Exception as e:
            await wait.edit(f"❌ 发送失败: {e}")

    # ── 聚合搜索（musicdl）──
    async def _musicdl_search(ctx, event, keyword, sources=None):
        msg = await event.reply(f"🔍 正在搜索「{keyword}」...")
        try:
            await event.delete()
        except Exception:
            pass
        try:
            results = await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(None, _musicdl_search_sync, keyword, sources),
                timeout=30
            )
        except asyncio.TimeoutError:
            await msg.edit(f"❌ 搜索超时（部分音源响应慢，请重试）")
            return
        except Exception as e:
            await msg.edit(f"❌ {e}")
            return
        if not results:
            await msg.edit(f"❌ 未找到相关结果")
            return
        pending_key = f"pending_music:{event.chat_id}"
        await ctx.storage.set(pending_key, {"results": results, "page": 0, "query": keyword, "time": time.time(), "msg_id": msg.id, "source": SOURCE_AGGREGATE})
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── musicdl 下载 ──
    async def _musicdl_download(ctx, event, song_data):
        title = song_data.get("title") or song_data.get("song_name") or "未知"
        wait = await event.reply(f"⏳ 正在获取音频: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        url = song_data.get("download_url", "")
        if not url:
            await wait.edit(f"❌ 未获取到下载链接")
            return
        ext = song_data.get("ext", "mp3")
        await wait.edit(f"⏳ 正在下载: {title}")
        import aiohttp
        filepath = _DOWNLOAD_DIR / f"musicdl_{int(time.time())}.{ext}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        await wait.edit(f"❌ 下载失败: HTTP {resp.status}")
                        return
                    with open(filepath, "wb") as f:
                        f.write(await resp.read())
        except Exception as e:
            await wait.edit(f"❌ 下载异常: {e}")
            import traceback
            ctx.log.error(traceback.format_exc())
            return
        if not filepath.exists() or filepath.stat().st_size == 0:
            await wait.edit("❌ 下载失败，文件为空")
            return
        await wait.edit(f"⏳ 正在发送: {title}")
        try:
            with open(filepath, "rb") as f:
                await event.client.send_file(
                    event.chat_id, f,
                    attributes=[DocumentAttributeAudio(duration=0, title=title, performer=song_data.get("artist", ""), voice=False)],
                )
            if not ctx.config.get("keep_local", False):
                filepath.unlink(missing_ok=True)
            await wait.delete()
        except Exception as e:
            await wait.edit(f"❌ 发送失败: {e}")

    # ── 命令处理 ──
    @ctx.on_message(outgoing=True)
    async def cmd_handler(event):
        text = (event.text or "").strip()
        if not text.startswith("."):
            return

        # .yysm 帮助
        if text == ".yysm":
            help_text = (
                "🎵 <b>音乐搜索下载 v2.0.0</b>\n\n"
                "🔍 <b>聚合搜索</b>（5音源）\n"
                "  <code>.yy 歌名</code> — 网易云/QQ/酷狗/酷我/咪咕\n\n"
                "🔍 <b>单音源搜索</b>\n"
                "  <code>.yyyt 歌名</code> — YouTube\n"
                "  <code>.yywy 歌名</code> — 网易云音乐\n"
                "  <code>.yyqq 歌名</code> — QQ音乐\n"
                "  <code>.yykg 歌名</code> — 酷狗音乐\n"
                "  <code>.yykw 歌名</code> — 酷我音乐\n"
                "  <code>.yymg 歌名</code> — 咪咕音乐\n\n"
                "💡 输入编号下载，<b>n</b> 下一页 <b>p</b> 上一页 <b>0</b> 取消"
            )
            msg = await event.reply(help_text)
            try:
                await event.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        if text == ".yy help":
            help_text = (
                "🎵 <b>音乐搜索下载 v2.0.0</b>\n\n"
                "🔍 <b>聚合搜索</b>（5音源）\n"
                "  <code>.yy 歌名</code> — 网易云/QQ/酷狗/酷我/咪咕\n\n"
                "🔍 <b>单音源搜索</b>\n"
                "  <code>.yyyt 歌名</code> — YouTube\n"
                "  <code>.yywy 歌名</code> — 网易云音乐\n"
                "  <code>.yyqq 歌名</code> — QQ音乐\n"
                "  <code>.yykg 歌名</code> — 酷狗音乐\n"
                "  <code>.yykw 歌名</code> — 酷我音乐\n"
                "  <code>.yymg 歌名</code> — 咪咕音乐\n\n"
                "💡 输入编号下载，<b>n</b> 下一页 <b>p</b> 上一页 <b>0</b> 取消"
            )
            msg = await event.reply(help_text)
            try:
                await event.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        if not text.startswith(".yy"):
            return

        # 单音源命令映射
        cmd_map = {
            ".yyyt": ("youtube", None),
            ".yywy": ("netease", None),
            ".yyqq": ("qq", None),
            ".yykg": ("kugou", None),
            ".yykw": ("kuwo", None),
            ".yymg": ("migu", None),
        }
        for prefix, (engine, sources) in cmd_map.items():
            if text.startswith(prefix):
                keyword = text[len(prefix):].strip()
                if not keyword:
                    break
                if engine == "youtube":
                    await _yt_search(ctx, event, keyword)
                else:
                    await _musicdl_search(ctx, event, keyword, [engine])
                return

        # .yy 歌名 → 聚合搜索（全部音源）
        if text.startswith(".yy"):
            keyword = text[len(".yy"):].strip()
            if keyword:
                await _musicdl_search(ctx, event, keyword, None)
            return

    # ── 选择处理 ──
    @ctx.on_message(outgoing=True)
    async def select_handler(event):
        text = (event.text or "").strip().lower()
        pending_key = f"pending_music:{event.chat_id}"
        pending = await ctx.storage.get(pending_key, None)
        if not pending:
            return
        if time.time() - pending.get("time", 0) > 60:
            await ctx.storage.delete(pending_key)
            return

        results = pending.get("results", [])
        page = pending.get("page", 0)
        source = pending.get("source", SOURCE_AGGREGATE)
        total_pages = max(1, (len(results) + _PAGE_SIZE - 1) // _PAGE_SIZE)

        if text in ("n", "next"):
            page = min(page + 1, total_pages - 1)
            pending["page"] = page
            pending["time"] = time.time()
            await ctx.storage.set(pending_key, pending)
            await event.reply(_build_result_page(results, page, pending.get("query", "")))
            try:
                await event.delete()
            except Exception:
                pass
            return

        if text in ("p", "prev"):
            page = max(page - 1, 0)
            pending["page"] = page
            pending["time"] = time.time()
            await ctx.storage.set(pending_key, pending)
            await event.reply(_build_result_page(results, page, pending.get("query", "")))
            try:
                await event.delete()
            except Exception:
                pass
            return

        if text == "0":
            await ctx.storage.delete(pending_key)
            try:
                await event.client.delete_messages(event.chat_id, [pending.get("msg_id"), event.id])
            except Exception:
                pass
            return

        if not text.isdigit():
            return

        idx = int(text)
        if idx < 1 or idx > len(results):
            return

        await ctx.storage.delete(pending_key)
        selected = results[idx - 1]

        try:
            await event.client.delete_messages(event.chat_id, [pending.get("msg_id"), event.id])
        except Exception:
            try:
                await event.delete()
            except Exception:
                pass

        if source == SOURCE_YOUTUBE:
            await _yt_download(ctx, event, selected["url"], selected["title"], selected.get("uploader", ""))
        else:
            # 处理 musicdl 下载
            artist = selected.get("artist") or selected.get("singers") or ""
            if isinstance(artist, list):
                artist = "".join(artist) if all(len(c) <= 2 for c in artist) else ", ".join(artist)
            selected["artist"] = artist
            await _musicdl_download(ctx, event, selected)

    await _add_plugin_log(ctx, "音乐搜索下载 v2.0.0 已就绪")


async def teardown(ctx):
    await _add_plugin_log(ctx, "音乐搜索下载已卸载")