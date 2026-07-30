# -*- coding: utf-8 -*-
# AWBotNest 插件：音乐搜索下载 (mymusic) v1.4.0
# 搜索 YouTube 下载 MP3 音频，支持翻页、编号选择下载

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
_PAGE_SIZE = 5
_SEARCH_COUNT = 10

__plugin__ = {
    "name": "音乐搜索下载",
    "id": "mymusic",
    "version": "1.4.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "搜索 YouTube 下载 MP3 音频。支持 .yy 歌名搜索、输入编号下载、翻页",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["yt-dlp>=2024.0.0"],
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
        dur = _format_duration(r["duration"]) if r["duration"] else "未知"
        lines.append(f"<b>{i + 1}.</b> {r['title']}")
        lines.append(f"    👤 {r['uploader']}  ⏱ {dur}\n")
    lines.append("💡 输入编号下载，<b>n</b> 下一页 <b>p</b> 上一页 <b>0</b> 取消")
    return "\n".join(lines)


def _yt_path() -> str:
    """查找 yt-dlp 可执行文件路径"""
    path = shutil.which("yt-dlp")
    if path:
        return path
    # 常见 venv 路径
    for p in [
        os.path.expanduser("~/.local/bin/yt-dlp"),
        "/usr/local/bin/yt-dlp",
        "/usr/bin/yt-dlp",
    ]:
        if os.path.isfile(p):
            return p
    return "yt-dlp"


async def setup(ctx):
    ctx.log.info("音乐搜索下载 v1.4.0 已加载")

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

    # ── 搜索 ──
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

        # 保存 pending
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {
            "results": results,
            "page": 0,
            "query": keyword,
            "time": time.time(),
            "msg_id": msg.id,
        })

        await msg.edit(_build_result_page(results, 0, keyword))

    # ── 下载 ──
    async def _do_download(ctx, client, message, url, title, uploader=""):
        wait = await message.reply(f"⏳ 正在下载: {title}")
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        template = str(_DOWNLOAD_DIR / "%(title)s.%(ext)s")

        yt_path = _yt_path()
        try:
            if shutil.which("ffmpeg"):
                # 有 ffmpeg，转 mp3
                subprocess.run(
                    [yt_path, "-x", "--audio-format", "mp3", "--audio-quality", "0",
                     "-o", template, "--no-playlist", "--no-warnings", url],
                    capture_output=True, text=True, timeout=300,
                )
            else:
                # 无 ffmpeg，下载 M4A 格式（Telegram 可直接播放）
                subprocess.run(
                    [yt_path, "-f", "bestaudio[ext=m4a]/bestaudio",
                     "-o", template, "--no-playlist", "--no-warnings", url],
                    capture_output=True, text=True, timeout=300,
                )
        except Exception as e:
            await wait.edit_text(f"❌ 下载异常: {e}")
            return

        # 找音频文件（mp3 或 webm/m4a）
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

    # ── 命令处理 ──
    @ctx.on_message(ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        # .yysm 帮助（30秒自毁）
        if text == ".yysm":
            help_text = (
                "🎵 <b>音乐搜索下载 v1.4.0</b>\n\n"
                "🔍 <b>搜索音乐</b>\n"
                "  <code>.yy 歌名</code> — 搜索并显示结果\n"
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
                "🎵 <b>音乐搜索下载 v1.4.0</b>\n\n"
                "🔍 <b>搜索音乐</b>\n"
                "  <code>.yy 歌名</code> — 搜索并显示结果\n"
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
    @ctx.on_message(ctx.filters.text, group=1)
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

        await _do_download(ctx, client, message, selected["url"], selected["title"], selected.get("uploader", ""))

    ctx.log.info("音乐搜索下载 v1.4.0 已就绪")


async def teardown(ctx):
    ctx.log.info("音乐搜索下载已卸载")