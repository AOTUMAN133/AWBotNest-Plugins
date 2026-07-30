# -*- coding: utf-8 -*-
# AWBotNest 插件：音乐搜索下载 (mymusic) v1.2.0
# 搜索 YouTube 下载 MP3 音频，支持翻页、编号选择下载

import os
import re
import asyncio
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path("/tmp/mymusic_downloads")
_PAGE_SIZE = 5
_SEARCH_COUNT = 10

__plugin__ = {
    "name": "音乐搜索下载",
    "id": "mymusic",
    "version": "1.2.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mymusic_v1.svg",
    "author": "凹凸曼",
    "description": "搜索 YouTube 下载 MP3 音频。支持 .yy 歌名搜索、直接输入编号下载、翻页",
    "scope": "user",
    "default_enabled": False,
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

async def _run_ytdlp(args: list, timeout: int = 120) -> tuple[str, str]:
    """运行 yt-dlp 并返回 (stdout, stderr)"""
    yt_path = os.path.expanduser("~/.local/bin/yt-dlp")
    if not os.path.isfile(yt_path):
        yt_path = "/root/.hermes/hermes-agent/venv/bin/yt-dlp"
    if not os.path.isfile(yt_path):
        yt_path = "yt-dlp"
    cmd = [yt_path] + args
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return "", "timeout"
    except FileNotFoundError:
        # yt-dlp not found, try with shell
        try:
            proc = await asyncio.create_subprocess_shell(
                f"{yt_path} {' '.join(args)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        except Exception as e:
            return "", f"shell error: {e}"
    except Exception as e:
        return "", f"error: {e}"


async def _search_music(query: str, max_results: int = _SEARCH_COUNT) -> list[dict]:
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
            results.append({
                "title": data.get("title", "未知标题"),
                "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                "duration": data.get("duration", 0),
                "uploader": data.get("uploader", "未知"),
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
    output_dir.mkdir(parents=True, exist_ok=True)
    template = str(output_dir / "%(title)s.%(ext)s")

    stdout, stderr = await _run_ytdlp([
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", template,
        "--no-playlist",
        "--no-warnings",
        url,
    ], timeout=300)

    # 写日志
    log_path = output_dir / "_ytdlp_log.txt"
    try:
        log_path.write_text(f"stdout({len(stdout)}): {stdout[:2000]}\n\nstderr({len(stderr)}): {stderr[:2000]}")
    except Exception:
        pass

    # 输出目录快照
    all_files = list(output_dir.iterdir())
    mp3_files = [f for f in all_files if f.suffix == ".mp3" and f.name != "_ytdlp_log.txt"]
    mp3_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if mp3_files:
        return mp3_files[0]

    # 尝试从 stdout 解析文件名
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line and ("/" in line or "\\" in line):
            p = Path(line)
            if p.exists():
                return p
            p_mp3 = p.with_suffix(".mp3")
            if p_mp3.exists():
                return p_mp3

    # 如果 async 方式失败，尝试同步方式
    try:
        import subprocess
        yt_path = os.path.expanduser("~/.local/bin/yt-dlp")
        if not os.path.isfile(yt_path):
            yt_path = "/root/.hermes/hermes-agent/venv/bin/yt-dlp"
        if not os.path.isfile(yt_path):
            yt_path = "yt-dlp"
        cmd = [yt_path, "-x", "--audio-format", "mp3", "--audio-quality", "0",
               "-o", template, "--no-playlist", "--no-warnings", url]
        result = await asyncio.to_thread(lambda: subprocess.run(cmd, capture_output=True, timeout=300, text=True))
        log_path.write_text(log_path.read_text() + f"\n\n--- sync fallback ---\nstdout: {result.stdout[:1000]}\nstderr: {result.stderr[:1000]}")
        mp3_files = [f for f in output_dir.iterdir() if f.suffix == ".mp3"]
        mp3_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if mp3_files:
            return mp3_files[0]
    except Exception as e:
        try:
            log_path.write_text(log_path.read_text() + f"\n\nsync fallback error: {e}")
        except Exception:
            pass

    return None


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


async def setup(ctx):
    ctx.log.info("音乐搜索下载 v1.2.0 已加载")

    @ctx.on_message(ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        # ── .yysm 帮助（30秒自毁） ──
        if text == ".yysm":
            help_text = (
                "🎵 <b>音乐搜索下载 v1.2.0</b>\n\n"
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

        # ── .yy help 帮助（30秒自毁） ──
        if text == ".yy help":
            help_text = (
                "🎵 <b>音乐搜索下载 v1.2.0</b>\n\n"
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

        # ── .yy URL 直接下载 ──
        url_match = re.match(r"^https?://", cmd)
        if url_match:
            url = cmd.strip()
            wait = await message.reply("⏳ 正在下载...")
            try:
                await message.delete()
            except Exception:
                pass
            path = await _download_audio(url, _DOWNLOAD_DIR)
            if not path:
                await wait.edit_text("❌ 下载失败，请检查链接")
                return
            await wait.edit_text("⏳ 正在发送...")
            try:
                with open(path, "rb") as f:
                    await client.send_audio(message.chat.id, f, title=path.stem)
                if not ctx.config.get("keep_local", False):
                    path.unlink(missing_ok=True)
                await wait.delete()
            except Exception as e:
                await wait.edit_text(f"❌ 发送失败: {e}")
            return

        # ── .yy 搜索词 ──
        if cmd:
            query = cmd.strip()
            msg = await message.reply("🔍 正在搜索...")
            try:
                await message.delete()
            except Exception:
                pass
            results = await _search_music(query, _SEARCH_COUNT)
            if not results:
                await msg.edit("❌ 未找到相关结果")
                return

            # 保存 pending 选择
            pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
            ctx.kv.set(pending_key, {
                "results": results,
                "page": 0,
                "query": query,
                "time": time.time(),
                "msg_id": msg.id,
            })

            result_text = _build_result_page(results, 0, query)
            await msg.edit(result_text)
            return

        # ── 空参数 ──
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

    # ── 处理用户选择（回复编号/n/p） ──
    @ctx.on_message(ctx.filters.text, group=1)
    async def select_handler(client, message):
        text = (message.text or "").strip().lower()
        pending_key = f"pending_music:{message.chat.id}:{message.from_user.id}"
        pending = ctx.kv.get(pending_key, None)
        if not pending:
            return

        # 30秒超时
        if time.time() - pending.get("time", 0) > 30:
            ctx.kv.delete(pending_key)
            return

        results = pending.get("results", [])
        page = pending.get("page", 0)
        total_pages = max(1, (len(results) + _PAGE_SIZE - 1) // _PAGE_SIZE)

        # n/p 翻页
        if text in ("n", "next"):
            page = min(page + 1, total_pages - 1)
            pending["page"] = page
            pending["time"] = time.time()
            ctx.kv.set(pending_key, pending)
            result_text = _build_result_page(results, page, pending.get("query", ""))
            await message.reply(result_text)
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
            result_text = _build_result_page(results, page, pending.get("query", ""))
            await message.reply(result_text)
            try:
                await message.delete()
            except Exception:
                pass
            return

        # 0 取消
        if text == "0":
            ctx.kv.delete(pending_key)
            try:
                await client.delete_messages(message.chat.id, [pending.get("msg_id"), message.id])
            except Exception:
                pass
            return

        # 编号下载
        if not text.isdigit():
            return

        idx = int(text)
        if idx < 1 or idx > len(results):
            return

        # 有效选择，清理 pending
        ctx.kv.delete(pending_key)
        selected = results[idx - 1]

        # 删除搜索结果消息和用户的选择消息
        try:
            await client.delete_messages(message.chat.id, [pending.get("msg_id"), message.id])
        except Exception:
            try:
                await message.delete()
            except Exception:
                pass

        # 下载并发送
        wait = await message.reply(f"⏳ 正在下载: {selected['title']}")
        try:
            path = await _download_audio(selected["url"], _DOWNLOAD_DIR)
        except Exception as e:
            await wait.edit_text(f"❌ 下载异常: {e}")
            return
        if not path:
            # 重试一次
            try:
                path = await _download_audio(selected["url"], _DOWNLOAD_DIR)
            except Exception:
                pass
        if not path:
            await wait.edit_text("❌ 下载失败")
            return

        await wait.edit_text(f"⏳ 正在发送: {selected['title']}")
        try:
            with open(path, "rb") as f:
                await client.send_audio(message.chat.id, f, title=selected["title"], performer=selected.get("uploader", ""))
            if not ctx.config.get("keep_local", False):
                path.unlink(missing_ok=True)
            await wait.delete()
        except Exception as e:
            await wait.edit_text(f"❌ 发送失败: {e}")

    ctx.log.info("音乐搜索下载 v1.2.0 已就绪")


async def teardown(ctx):
    ctx.log.info("音乐搜索下载已卸载")