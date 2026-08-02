# -*- coding: utf-8 -*-
# AWBotNest 插件：音乐搜索下载 (mymusic) v2.0.0
# 聚合搜索：网易云/QQ/酷狗/酷我/咪咕 + YouTube，支持翻页、编号选择下载

import os
import re
import sys
import asyncio
import json
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
    "version": "2.0.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "聚合搜索 5 音源（网易云/QQ/酷狗/酷我/咪咕）+ YouTube，支持 .yy 聚合搜索、.yyyt YouTube、.yywy 网易云等",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["yt-dlp>=2024.0.0", "aiohttp", "musicdl"],
    "config_schema": {
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载",
            "help": "发送后不删除本地下载的文件"
        },
    },
}


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


def _musicdl_search_sync(keyword: str, sources: list = None) -> list:
    """通过 musicdl 搜索音乐（纯 Python，直接在插件进程内导入）"""
    import json, io, sys as _sys
    
    # 确保模块路径正确
    _base = str(_BASE_DIR)
    if _base not in _sys.path:
        _sys.path.insert(0, _base)
    
    # 音源映射
    CLIENT_MAP = {
        "netease": "NeteaseMusicClient", "qq": "QQMusicClient",
        "kugou": "KugouMusicClient", "kuwo": "KuwoMusicClient", "migu": "MiguMusicClient"
    }
    NAME_MAP = {"netease": "网易云音乐", "qq": "QQ音乐", "kugou": "酷狗音乐", "kuwo": "酷我音乐", "migu": "咪咕音乐"}
    
    src_list = sources or list(CLIENT_MAP.keys())
    client_names = [CLIENT_MAP.get(s, s) for s in src_list]
    
    # 重定向 stdout 以抑制 musicdl 的进度条，保留 stderr 的日志
    _old_stdout = _sys.stdout
    _sys.stdout = io.StringIO()
    
    try:
        from musicdl.musicdl import MusicClient
        client = MusicClient(
            music_sources=client_names,
            init_music_clients_cfg={cn: {"disable_print": True, "search_size_per_source": 5} for cn in client_names}
        )
        result = client.search(keyword)
        
        songs = []
        for src, src_songs in result.items():
            if src in client_names:
                for s in src_songs:
                    songs.append({
                        "song_name": s.song_name,
                        "singers": [str(sg) for sg in (s.singers or [])],
                        "album": s.album or "",
                        "duration_s": s.duration_s or 0,
                        "download_url": s.download_url or "",
                        "ext": s.ext or "",
                        "file_size": s.file_size or "",
                        "source": s.source or src,
                        "_source_key": next((k for k, v in CLIENT_MAP.items() if v == src), src),
                        "_source_name": NAME_MAP.get(next((k for k, v in CLIENT_MAP.items() if v == src), src), src),
                    })
    finally:
        _sys.stdout = _old_stdout
    
    return songs


def _musicdl_url_sync(song_data: dict) -> str:
    """获取网易云歌曲下载URL"""
    url = song_data.get("download_url", "")
    if url:
        return url
    # 如果预获取的URL为空，实时获取
    from _netease_api import get_song_url
    return get_song_url(song_data.get("url_id", ""))


async def setup(ctx):
    ctx.log.info("音乐搜索下载 v2.0.0 已加载")

    # 检查 yt-dlp
    yt_path = _yt_path()
    try:
        r = subprocess.run([yt_path, "--version"], capture_output=True, text=True, timeout=10)
        ctx.log.info(f"yt-dlp 版本: {r.stdout.strip()}")
    except Exception:
        ctx.log.info("yt-dlp 未找到，YouTube 搜索不可用")

    # 检查并安装 musicdl 及其依赖
    # 先确保 pywidevine 版本正确（否则 musicdl 导入会失败）
    try:
        import pywidevine.license_protocol_pb2
    except ImportError:
        ctx.log.info("安装 pywidevine 依赖...")
        for pkg_cmd in [
            ["uv", "pip", "install", "pywidevine>=1.9.0", "-q"],
            [sys.executable, "-m", "pip", "install", "pywidevine>=1.9.0", "-q"],
        ]:
            try:
                subprocess.run(pkg_cmd, capture_output=True, text=True, timeout=60)
                break
            except:
                continue
    
    try:
        from musicdl.musicdl import MusicClient
        ctx.log.info("musicdl 已就绪")
    except ImportError:
        ctx.log.info("安装 musicdl...")
        for pkg_cmd in [
            ["uv", "pip", "install", "musicdl", "-q"],
            [sys.executable, "-m", "pip", "install", "musicdl", "-q"],
        ]:
            try:
                subprocess.run(pkg_cmd, capture_output=True, text=True, timeout=120)
                break
            except:
                continue
        try:
            from musicdl.musicdl import MusicClient
            ctx.log.info("musicdl 安装成功")
        except Exception as e2:
            ctx.log.warning(f"musicdl 安装失败: {e2}")

    # 检查 ffmpeg
    ffmpeg_available = shutil.which("ffmpeg") is not None
    if not ffmpeg_available:
        ctx.log.info("ffmpeg 未找到，尝试安装...")
        try:
            subprocess.run(["apt-get", "install", "-y", "ffmpeg"], capture_output=True, text=True, timeout=120)
            ffmpeg_available = shutil.which("ffmpeg") is not None
            if ffmpeg_available:
                ctx.log.info("ffmpeg 安装成功")
        except Exception as e:
            ctx.log.warning(f"ffmpeg 自动安装失败: {e}")
    else:
        ctx.log.info("ffmpeg 已可用")

    # ── YouTube 搜索 ──
    async def _yt_search(ctx, client, message, keyword, page=1):
        msg = await message.reply(f"🔍 正在搜索 YouTube「{keyword}」...")
        try:
            await message.delete()
        except Exception:
            pass
        try:
            result = subprocess.run(
                [_yt_path(), "--flat-playlist", "--dump-json", "--no-warnings", f"ytsearch{_SEARCH_COUNT}:{keyword}"],
                capture_output=True, text=True, timeout=30,
            )
        except Exception as e:
            await msg.edit(f"❌ 搜索失败: {e}")
            return
        results = []
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
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {"results": results, "page": 0, "query": keyword, "time": time.time(), "msg_id": msg.id, "source": SOURCE_YOUTUBE})
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── YouTube 下载 ──
    async def _yt_download(ctx, client, message, url, title, uploader=""):
        wait = await message.reply(f"⏳ 正在下载: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        template = str(_DOWNLOAD_DIR / "%(title)s.%(ext)s")
        try:
            if shutil.which("ffmpeg"):
                subprocess.run([_yt_path(), "-x", "--audio-format", "mp3", "--audio-quality", "0", "-o", template, "--no-playlist", "--no-warnings", url], capture_output=True, text=True, timeout=300)
            else:
                subprocess.run([_yt_path(), "-f", "bestaudio[ext=m4a]/bestaudio", "-o", template, "--no-playlist", "--no-warnings", url], capture_output=True, text=True, timeout=300)
        except Exception as e:
            await wait.edit_text(f"❌ 下载异常: {e}")
            return
        audio_files = sorted(_DOWNLOAD_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        audio_files = [f for f in audio_files if f.suffix in (".mp3", ".webm", ".m4a", ".opus")]
        if not audio_files:
            await wait.edit_text("❌ 下载失败，未找到音频文件")
            return
        path = audio_files[0]
        await wait.edit_text(f"⏳ 正在发送: {title}")
        try:
            with open(path, "rb") as f:
                await client.send_audio(message.chat.id, f, title=title, performer=uploader)
            if not ctx.config.get("keep_local", False):
                path.unlink(missing_ok=True)
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ 发送失败: {e}")

    # ── 聚合搜索（musicdl）──
    async def _musicdl_search(ctx, client, message, keyword, sources=None):
        msg = await message.reply(f"🔍 正在搜索「{keyword}」...")
        try:
            await message.delete()
        except Exception:
            pass
        try:
            results = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, _musicdl_search_sync, keyword, sources),
                timeout=120
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
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {"results": results, "page": 0, "query": keyword, "time": time.time(), "msg_id": msg.id, "source": SOURCE_AGGREGATE})
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── musicdl 下载 ──
    async def _musicdl_download(ctx, client, message, song_data):
        title = song_data.get("title") or song_data.get("song_name") or "未知"
        wait = await message.reply(f"⏳ 正在获取音频: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        url = song_data.get("download_url", "")
        if not url:
            await wait.edit_text(f"❌ 未获取到下载链接")
            return
        ext = song_data.get("ext", "mp3")
        await wait.edit_text(f"⏳ 正在下载: {title}")
        import aiohttp
        filepath = _DOWNLOAD_DIR / f"musicdl_{int(time.time())}.{ext}"
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        await wait.edit_text(f"❌ 下载失败: HTTP {resp.status}")
                        return
                    with open(filepath, "wb") as f:
                        f.write(await resp.read())
        except Exception as e:
            await wait.edit_text(f"❌ 下载异常: {e}")
            import traceback
            ctx.log.error(traceback.format_exc())
            return
        if not filepath.exists() or filepath.stat().st_size == 0:
            await wait.edit_text("❌ 下载失败，文件为空")
            return
        await wait.edit_text(f"⏳ 正在发送: {title}")
        try:
            with open(filepath, "rb") as f:
                await client.send_audio(message.chat.id, f, title=title, performer=song_data.get("artist", ""))
            if not ctx.config.get("keep_local", False):
                filepath.unlink(missing_ok=True)
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ 发送失败: {e}")

    # ── 命令处理 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
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
            msg = await message.reply(help_text)
            try:
                await message.delete()
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
            msg = await message.reply(help_text)
            try:
                await message.delete()
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
                    await _yt_search(ctx, client, message, keyword)
                else:
                    await _musicdl_search(ctx, client, message, keyword, [engine])
                return

        # .yy 歌名 → 聚合搜索（全部音源）
        if text.startswith(".yy"):
            keyword = text[len(".yy"):].strip()
            if keyword:
                await _musicdl_search(ctx, client, message, keyword, None)
            return

    # ── 选择处理 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=1)
    async def select_handler(client, message):
        text = (message.text or "").strip().lower()
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        pending = ctx.kv.get(pending_key, None)
        if not pending:
            return
        if time.time() - pending.get("time", 0) > 60:
            ctx.kv.delete(pending_key)
            return

        results = pending.get("results", [])
        page = pending.get("page", 0)
        source = pending.get("source", SOURCE_AGGREGATE)
        total_pages = max(1, (len(results) + _PAGE_SIZE - 1) // _PAGE_SIZE)

        if text in ("n", "next"):
            page = min(page + 1, total_pages - 1)
            pending["page"] = page
            pending["time"] = time.time()
            ctx.kv.set(pending_key, pending)
            await message.reply(_build_result_page(results, page, pending.get("query", "")))
            try:
                await message.delete()
            except Exception:
                pass
            return

        if text in ("p", "prev"):
            page = max(page - 1, 0)
            pending["page"] = page
            pending["time"] = time.time()
            ctx.kv.set(pending_key, pending)
            await message.reply(_build_result_page(results, page, pending.get("query", "")))
            try:
                await message.delete()
            except Exception:
                pass
            return

        if text == "0":
            ctx.kv.delete(pending_key)
            try:
                await client.delete_messages(message.chat.id, [pending.get("msg_id"), message.id])
            except Exception:
                pass
            return

        if not text.isdigit():
            return

        idx = int(text)
        if idx < 1 or idx > len(results):
            return

        ctx.kv.delete(pending_key)
        selected = results[idx - 1]

        try:
            await client.delete_messages(message.chat.id, [pending.get("msg_id"), message.id])
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass

        if source == SOURCE_YOUTUBE:
            await _yt_download(ctx, client, message, selected["url"], selected["title"], selected.get("uploader", ""))
        else:
            # 处理 musicdl 下载
            artist = selected.get("artist") or selected.get("singers") or ""
            if isinstance(artist, list):
                artist = "".join(artist) if all(len(c) <= 2 for c in artist) else ", ".join(artist)
            selected["artist"] = artist
            await _musicdl_download(ctx, client, message, selected)

    ctx.log.info("音乐搜索下载 v2.0.0 已就绪")


async def teardown(ctx):
    ctx.log.info("音乐搜索下载已卸载")