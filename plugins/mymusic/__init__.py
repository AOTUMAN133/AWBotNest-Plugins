# -*- coding: utf-8 -*-
# AWBotNest 插件：音乐搜索下载 (mymusic) v1.5.1
# 搜索 YouTube / 网易云音乐下载 MP3，支持翻页、编号选择下载

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
SOURCE_NETEASE = "netease"

__plugin__ = {
    "name": "音乐搜索下载",
    "id": "mymusic",
    "version": "1.5.1",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "搜索 YouTube / 网易云音乐下载 MP3。支持 .yy 歌名搜索、.yywy 网易云搜索、输入编号下载、翻页",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["yt-dlp>=2024.0.0", "aiohttp"],
    "config_schema": {
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载",
            "help": "发送后不删除本地下载的文件"
        },
    },
}


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_result_page(results: list, page: int, query: str) -> str:
    total = len(results)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _PAGE_SIZE
    end = min(start + _PAGE_SIZE, total)

    lines = [f"🎵 <b>搜索结果: {query}</b>  ({page + 1}/{total_pages})\n"]
    for i in range(start, end):
        r = results[i]
        title = r.get("title") or r.get("name") or "未知"
        uploader = r.get("uploader") or r.get("artist") or "未知"
        dur = _format_duration(r["duration"]) if r.get("duration") else "未知"
        lines.append(f"<b>{i + 1}.</b> {title}")
        lines.append(f"    👤 {uploader}  ⏱ {dur}\n")
    lines.append("💡 输入编号下载，<b>n</b> 下一页 <b>p</b> 上一页 <b>0</b> 取消")
    return "\n".join(lines)


def _yt_path() -> str:
    """查找 yt-dlp 可执行文件路径"""
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


def _netease_search_sync(keyword: str, limit: int = 10) -> list:
    """搜索网易云音乐（纯 Python）"""
    api_path = str(_BASE_DIR / "_netease_api.py")
    try:
        r = subprocess.run(
            [sys.executable, api_path, "search", keyword],
            capture_output=True, text=True, timeout=30,
            cwd=str(_BASE_DIR),
        )
        if r.returncode != 0:
            raise RuntimeError(f"脚本错误: {r.stderr[:200]}")
        data = json.loads(r.stdout.strip())
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(data["error"])
        if not isinstance(data, list):
            raise RuntimeError("返回格式异常")
        return data[:limit]
    except Exception as e:
        raise RuntimeError(f"网易云搜索失败: {e}")


def _netease_url_sync(song_id: str) -> str:
    """获取网易云音乐下载链接（纯 Python）"""
    api_path = str(_BASE_DIR / "_netease_api.py")
    try:
        r = subprocess.run(
            [sys.executable, api_path, "url", str(song_id)],
            capture_output=True, text=True, timeout=30,
            cwd=str(_BASE_DIR),
        )
        if r.returncode != 0:
            raise RuntimeError(f"脚本错误: {r.stderr[:200]}")
        data = json.loads(r.stdout.strip())
        if isinstance(data, dict) and "error" in data:
            raise RuntimeError(data["error"])
        if not isinstance(data, dict) or not data.get("url"):
            raise RuntimeError("未获取到下载链接")
        return data["url"]
    except Exception as e:
        raise RuntimeError(f"获取网易云URL失败: {e}")


async def setup(ctx):
    ctx.log.info("音乐搜索下载 v1.5.1 已加载")

    # 确保 yt-dlp 可用
    yt_path = _yt_path()
    yt_available = True
    try:
        r = subprocess.run([yt_path, "--version"], capture_output=True, text=True, timeout=10)
        ctx.log.info(f"yt-dlp 版本: {r.stdout.strip()}")
    except Exception:
        yt_available = False
        ctx.log.info("yt-dlp 未找到，尝试自动安装...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "yt-dlp", "--quiet"],
                capture_output=True, text=True, timeout=60,
            )
            yt_path = _yt_path()
            r = subprocess.run([yt_path, "--version"], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                yt_available = True
                ctx.log.info(f"yt-dlp 安装成功: {r.stdout.strip()}")
            else:
                ctx.log.warning("yt-dlp 安装后仍不可用")
        except Exception as e:
            ctx.log.warning(f"yt-dlp 自动安装失败: {e}")

    if not yt_available:
        ctx.log.warning("yt-dlp 不可用，搜索下载功能将无法使用")

    # 检查 ffmpeg
    ffmpeg_available = shutil.which("ffmpeg") is not None
    if not ffmpeg_available:
        ctx.log.info("ffmpeg 未找到，尝试安装...")
        try:
            subprocess.run(
                ["apt-get", "install", "-y", "ffmpeg"],
                capture_output=True, text=True, timeout=120,
            )
            ffmpeg_available = shutil.which("ffmpeg") is not None
            if ffmpeg_available:
                ctx.log.info("ffmpeg 安装成功")
        except Exception as e:
            ctx.log.warning(f"ffmpeg 自动安装失败: {e}")
    else:
        ctx.log.info("ffmpeg 已可用")

    # ── YouTube 搜索 ──
    async def _do_search(ctx, client, message, keyword, page=1):
        msg = await message.reply(f"🔍 正在搜索「{keyword}」...")
        try:
            await message.delete()
        except Exception:
            pass

        yt_path = _yt_path()
        search_query = f"ytsearch{_SEARCH_COUNT}:{keyword}"
        try:
            result = subprocess.run(
                [yt_path, "--flat-playlist", "--dump-json", "--no-warnings", search_query],
                capture_output=True, text=True, timeout=30,
            )
            stdout = result.stdout
        except Exception as e:
            await msg.edit(f"❌ 搜索失败: {e}")
            return

        results = []
        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                results.append({
                    "title": data.get("title", "未知标题"),
                    "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                    "duration": data.get("duration", 0),
                    "uploader": data.get("uploader", "未知"),
                    "id": data.get("id", ""),
                })
            except json.JSONDecodeError:
                continue

        if not results:
            await msg.edit(f"❌ 未找到相关结果")
            return

        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {
            "results": results,
            "page": 0,
            "query": keyword,
            "time": time.time(),
            "msg_id": msg.id,
            "source": SOURCE_YOUTUBE,
        })
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── YouTube 下载 ──
    async def _do_download(ctx, client, message, url, title, uploader=""):
        wait = await message.reply(f"⏳ 正在下载: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        template = str(_DOWNLOAD_DIR / "%(title)s.%(ext)s")

        yt_path = _yt_path()
        try:
            if shutil.which("ffmpeg"):
                subprocess.run(
                    [yt_path, "-x", "--audio-format", "mp3", "--audio-quality", "0",
                     "-o", template, "--no-playlist", "--no-warnings", url],
                    capture_output=True, text=True, timeout=300,
                )
            else:
                subprocess.run(
                    [yt_path, "-f", "bestaudio[ext=m4a]/bestaudio",
                     "-o", template, "--no-playlist", "--no-warnings", url],
                    capture_output=True, text=True, timeout=300,
                )
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

    # ── 网易云搜索 ──
    async def _netease_do_search(ctx, client, message, keyword, page=1):
        msg = await message.reply(f"🔍 正在搜索网易云「{keyword}」...")
        try:
            await message.delete()
        except Exception:
            pass

        try:
            results = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, _netease_search_sync, keyword, _SEARCH_COUNT
                ), timeout=35
            )
        except Exception as e:
            await msg.edit(f"❌ {e}")
            return

        if not results:
            await msg.edit(f"❌ 网易云未找到相关结果")
            return

        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {
            "results": results,
            "page": 0,
            "query": keyword,
            "time": time.time(),
            "msg_id": msg.id,
            "source": SOURCE_NETEASE,
        })
        await msg.edit(_build_result_page(results, 0, keyword))

    # ── 网易云下载 ──
    async def _netease_do_download(ctx, client, message, song_id, title, artist=""):
        wait = await message.reply(f"⏳ 正在获取网易云音频: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

        try:
            url = await asyncio.get_event_loop().run_in_executor(
                None, _netease_url_sync, song_id
            )
        except Exception as e:
            await wait.edit_text(f"❌ {e}")
            return

        if not url:
            await wait.edit_text(f"❌ 未获取到下载链接（可能需VIP）")
            return

        await wait.edit_text(f"⏳ 正在下载: {title}")
        import aiohttp
        filepath = _DOWNLOAD_DIR / f"netease_{song_id}_{int(time.time())}.mp3"
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
            return

        if not filepath.exists() or filepath.stat().st_size == 0:
            await wait.edit_text("❌ 下载失败，文件为空")
            return

        await wait.edit_text(f"⏳ 正在发送: {title}")
        try:
            with open(filepath, "rb") as f:
                await client.send_audio(message.chat.id, f, title=title, performer=artist)
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

        # .yysm 帮助（30秒自毁）
        if text == ".yysm":
            help_text = (
                "🎵 <b>音乐搜索下载 v1.5.1</b>\n\n"
                "🔍 <b>搜索音乐</b>\n"
                "  <code>.yy 歌名</code> — 搜索YouTube并显示结果\n"
                "  <code>.yywy 歌名</code> — 搜索网易云音乐\n"
                "  输入 <b>编号</b> 下载，<b>n</b>/<b>p</b> 翻页\n\n"
                "🔗 <b>直接下载</b>\n"
                "  <code>.yy URL</code> — 直接下载 YouTube 链接"
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
                "🎵 <b>音乐搜索下载 v1.5.1</b>\n\n"
                "🔍 <b>搜索音乐</b>\n"
                "  <code>.yy 歌名</code> — 搜索YouTube并显示结果\n"
                "  <code>.yywy 歌名</code> — 搜索网易云音乐\n"
                "  输入 <b>编号</b> 下载，<b>n</b>/<b>p</b> 翻页\n\n"
                "🔗 <b>直接下载</b>\n"
                "  <code>.yy URL</code> — 直接下载 YouTube 链接"
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

        # .yywy 歌名 → 网易云搜索
        if text.startswith(".yywy"):
            keyword = text[len(".yywy"):].strip()
            if keyword:
                await _netease_do_search(ctx, client, message, keyword)
            return

        cmd = text[len(".yy"):].strip()

        if re.match(r"^https?://", cmd):
            await _do_download(ctx, client, message, cmd.strip(), "音频")
            return

        if cmd:
            await _do_search(ctx, client, message, cmd.strip())
            return

        msg = await message.reply("🎵 用法: <code>.yy 歌名</code> 搜索音乐，或 <code>.yysm</code> 查看帮助")
        try:
            await message.delete()
        except Exception:
            pass
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except Exception:
            pass

    # ── 选择处理 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=1)
    async def select_handler(client, message):
        text = (message.text or "").strip().lower()
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        pending = ctx.kv.get(pending_key, None)
        if not pending:
            return

        if time.time() - pending.get("time", 0) > 30:
            ctx.kv.delete(pending_key)
            return

        results = pending.get("results", [])
        page = pending.get("page", 0)
        source = pending.get("source", SOURCE_YOUTUBE)
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

        if source == SOURCE_NETEASE:
            await _netease_do_download(ctx, client, message, selected["id"], selected["name"], selected.get("artist", ""))
        else:
            await _do_download(ctx, client, message, selected["url"], selected["title"], selected.get("uploader", ""))

    ctx.log.info("音乐搜索下载 v1.5.1 已就绪")


async def teardown(ctx):
    ctx.log.info("音乐搜索下载已卸载")