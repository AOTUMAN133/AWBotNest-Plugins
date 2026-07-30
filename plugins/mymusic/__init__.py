# -*- coding: utf-8 -*-
# AWBotNest 插件：音乐搜索下载 (mymusic) v1.0.0
# 搜索 YouTube 下载 MP3 音频

import os
import re
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path(__file__).parent / "downloads"

__plugin__ = {
    "name": "音乐搜索下载",
    "id": "mymusic",
    "version": "1.0.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "搜索 YouTube 下载 MP3 音频。支持 .music 歌名搜索、.music URL 直接下载",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "max_results": {
            "type": "number", "default": 5, "label": "搜索结果数量",
            "section": "搜索", "min": 1, "max": 10,
            "help": "搜索时显示的最大结果数"
        },
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载",
            "help": "发送后不删除本地下载的文件"
        },
    },
}


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name)[:100]


async def _run_ytdlp(args: list, timeout: int = 120) -> tuple[str, str]:
    """运行 yt-dlp 并返回 (stdout, stderr)"""
    yt_path = os.path.expanduser("~/.local/bin/yt-dlp")
    if not os.path.isfile(yt_path):
        yt_path = "/root/.hermes/hermes-agent/venv/bin/yt-dlp"
    if not os.path.isfile(yt_path):
        yt_path = "yt-dlp"
    proc = await asyncio.create_subprocess_exec(
        yt_path, *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return "", "timeout"
    return stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")


async def _search_music(query: str, max_results: int = 5) -> list[dict]:
    """搜索 YouTube 音乐，返回结果列表"""
    search_query = f"ytsearch{max_results}:{query}"
    stdout, _ = await _run_ytdlp([
        "--flat-playlist", "--dump-json", "--no-warnings",
        search_query,
    ], timeout=30)

    results = []
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            import json
            data = json.loads(line)
            title = data.get("title", "未知标题")
            url = f"https://www.youtube.com/watch?v={data.get('id', '')}"
            duration = data.get("duration", 0)
            uploader = data.get("uploader", "未知")
            results.append({
                "title": title,
                "url": url,
                "duration": duration,
                "uploader": uploader,
                "id": data.get("id", ""),
            })
        except json.JSONDecodeError:
            continue
    return results


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def _download_audio(url: str, output_dir: Path) -> Path | None:
    """下载 YouTube 音频并转为 MP3"""
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(title)s.%(ext)s")

    stdout, stderr = await _run_ytdlp([
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", template,
        "--no-playlist",
        "--no-warnings",
        "--print", "filename",
        url,
    ], timeout=300)

    if not stdout.strip():
        return None

    # 解析输出的文件名
    filepath = stdout.strip().split("\n")[0]
    path = Path(filepath)
    if path.exists():
        return path
    # 尝试在输出目录找 mp3 文件
    for f in output_dir.iterdir():
        if f.suffix == ".mp3":
            return f
    return None


async def setup(ctx):
    ctx.log.info("音乐搜索下载 v1.0.0 已加载")

    @ctx.on_message(ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        # .music help — 帮助
        if text == ".music help":
            help_text = (
                "🎵 <b>音乐搜索下载 v1.0.0</b>\n\n"
                "🔍 <b>搜索音乐</b>\n"
                "  <code>.music 歌名</code> — 搜索并显示结果\n"
                "  <code>.music dl 编号</code> — 下载指定编号的音乐\n\n"
                "🔗 <b>直接下载</b>\n"
                "  <code>.music URL</code> — 直接下载 YouTube 链接\n\n"
                "⚙️ 可在插件配置中调整搜索结果数量"
            )
            await message.reply(help_text)
            try:
                await message.delete()
            except Exception:
                pass
            return

        if not text.startswith(".music"):
            return

        chat_id = str(message.chat.id)
        cmd = text[len(".music"):].strip()

        # .music dl 编号 — 下载选中的结果
        m = re.match(r"^dl\s+(\d+)$", cmd)
        if m:
            # 从 KV 获取搜索结果
            search_data = ctx.kv.get(f"music_search_{chat_id}", {})
            results = search_data.get("results", [])
            idx = int(m.group(1)) - 1
            if idx < 0 or idx >= len(results):
                await message.reply("❌ 编号无效，请重新搜索")
                try:
                    await message.delete()
                except Exception:
                    pass
                return
            selected = results[idx]
            wait = await message.reply(f"⏳ 正在下载: {selected['title']}")
            try:
                await message.delete()
            except Exception:
                pass
            path = await _download_audio(selected["url"], _DOWNLOAD_DIR)
            if not path:
                await wait.edit_text("❌ 下载失败")
                return
            await wait.edit_text(f"⏳ 正在发送: {selected['title']}")
            try:
                with open(path, "rb") as f:
                    await client.send_audio(chat_id, f, title=selected["title"], performer=selected.get("uploader", ""))
                if not ctx.config.get("keep_local", False):
                    path.unlink(missing_ok=True)
                await wait.delete()
            except Exception as e:
                await wait.edit_text(f"❌ 发送失败: {e}")
            return

        # .music URL — 直接下载链接
        url_match = re.match(r"^https?://", cmd)
        if url_match:
            url = cmd.strip()
            wait = await message.reply("⏳ 正在下载...")
            path = await _download_audio(url, _DOWNLOAD_DIR)
            if not path:
                await wait.edit_text("❌ 下载失败，请检查链接")
                return
            await wait.edit_text("⏳ 正在发送...")
            try:
                with open(path, "rb") as f:
                    await client.send_audio(chat_id, f, title=path.stem)
                if not ctx.config.get("keep_local", False):
                    path.unlink(missing_ok=True)
                await wait.delete()
            except Exception as e:
                await wait.edit_text(f"❌ 发送失败: {e}")
            return

        # .music 搜索词 — 搜索音乐
        if cmd:
            query = cmd.strip()
            max_results = int(ctx.config.get("max_results", 5))
            wait = await message.reply("🔍 正在搜索...")
            results = await _search_music(query, max_results)
            if not results:
                await wait.edit_text("❌ 未找到相关结果")
                return

            # 保存到 KV 供后续下载
            ctx.kv.set(f"music_search_{chat_id}", {"results": results, "time": _now()})

            lines = [f"🎵 <b>搜索结果: {query}</b>\n"]
            for i, r in enumerate(results, 1):
                dur = _format_duration(r["duration"]) if r["duration"] else "未知"
                lines.append(f"<b>{i}.</b> {r['title']}")
                lines.append(f"    👤 {r['uploader']}  ⏱ {dur}")
                lines.append(f"    <code>.music dl {i}</code>\n")
            lines.append("💡 回复编号下载: <code>.music dl 1</code>")
            await wait.edit_text("\n".join(lines))
            return

        # 只有一个 .music 没有参数
        await message.reply("🎵 用法: <code>.music 歌名</code> 搜索音乐，或 <code>.music help</code> 查看帮助")
        try:
            await message.delete()
        except Exception:
            pass

    ctx.log.info("音乐搜索下载 v1.0.0 已就绪")


async def teardown(ctx):
    ctx.log.info("音乐搜索下载已卸载")