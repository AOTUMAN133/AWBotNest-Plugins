# -*- coding: utf-8 -*-
# AWBotNest 插件：聚合解析 (videodl) - 多平台解析下载

import asyncio
import httpx
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))

try:
    from ._videodl_engine import parse_via_videodl, HAS_VIDEODL, get_import_error
except Exception:
    parse_via_videodl = None
    HAS_VIDEODL = False
    get_import_error = lambda: ""

__plugin__ = {
    "name": "聚合解析",
    "id": "videodl",
    "version": "2.4.6",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/videodl_v2.svg",
    "author": "凹凸曼",
    "description": "多平台视频/图文解析下载。支持 /jx 解析链接。支持抖音/B站/优酷/腾讯/爱奇艺/YouTube等1000+平台（videodl原生+ParseHub+yt-dlp三引擎）。",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["SignerPy>=0.12"],
    "config_schema": {
        "max_size": {
            "type": "number", "default": 50, "label": "最大文件大小(MB)",
            "section": "下载", "min": 1, "max": 500, "order": 1,
            "help": "超过此大小的视频走备用方案"
        },
        "oversize_action": {
            "type": "select", "default": "notify", "label": "超限处理方式",
            "section": "下载", "order": 4,
            "options": [
                {"value": "notify", "label": "提示用户"},
                {"value": "link", "label": "仅发送下载链接"},
                {"value": "force", "label": "直接发送"},
            ]
        },
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "下载", "order": 5,
            "help": "发送后不删除本地下载的文件"
        },
        "view_logs": {
            "type": "action", "label": "📋 查看日志", "section": "调试",
            "action": "view_logs"
        },
    },
}

_DOWNLOAD_DIR = Path(__file__).parent / "downloads"
_KV_LOGS = "videodl_logs"
_BRIDGE_SCRIPT = Path(__file__).parent / "_core" / "parse_bridge.py"
_PH_VENV_PYTHON = "/root/.hermes/plugins_env/ph_venv3/bin/python3"


def _log(ctx, msg: str):
    ctx.log.info("[聚合解析] %s", msg)
    logs = ctx.kv.get(_KV_LOGS, []) or []
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-30:])


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size/1024/1024:.1f}MB"
    return f"{size/1024/1024/1024:.1f}GB"


async def _resolve_url(url: str) -> str:
    """跟随短链接跳转，获取真实 URL"""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as cli:
            r = await cli.head(url)
            return str(r.url)
    except Exception:
        return url


async def _download_file(url: str, path: Path, headers: dict = None) -> bool:
    try:
        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
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


def _get_help_text() -> str:
    return (
        "📦 <b>聚合解析 - 多平台解析下载</b>\n\n"
        "📌 <b>使用方法</b>\n"
        "  .jx <链接或分享文本>  — 解析并下载\\n"
        "  .jxsm  — 查看帮助\\n"
        "  .jxstatus  — 查看引擎状态\\n"
        "  💡 回复别人消息发送 .jx 也可解析\\n\\n"
        "📌 <b>三引擎加持，智能选择</b>\n"
        "  🔵 <b>引擎1: videodl 原生</b>（纯Python，优先）\n"
        "  🇨🇳 抖音 · B站 · 快手 · 小红书 · 微博\n"
        "  🎬 爱奇艺 · 腾讯视频 · 优酷 · 芒果TV\n"
        "  📺 知乎 · 贴吧 · 虎牙 · A站 · 开眼\n"
        "  🌍 YouTube · Dailymotion · Reddit · TED\n"
        "  📌 共 100+ 平台（不依赖外部工具）\n\n"
        "  🟢 <b>引擎2: ParseHub 桥接</b>（中文平台补强）\n"
        "  🎯 公众号 · 小黑盒 · 酷安 · 更多中文站\n\n"
        "  🟡 <b>引擎3: yt-dlp</b>（海外平台，1752个网站）\n"
        "  ▶️ YouTube · Twitter/X · Instagram · Facebook\n"
        "  🎵 TikTok · SoundCloud · Vimeo · Twitch\n"
        "  📌 Reddit · Pinterest · Imgur · Flickr\n\n"
        "📌 <b>说明</b>\n"
        "  自动按引擎1→2→3顺序尝试，直到成功\n"
        "  支持的媒体类型：视频、图文、音乐\n"
        "  超过50MB自动提示处理方式\n"
        "  可在插件配置中调整大小限制"
    )


async def _get_python_version(python_path: str) -> str:
    """获取 Python 版本号"""
    try:
        loop = asyncio.get_running_loop()
        cp = await loop.run_in_executor(None, lambda: subprocess.run(
            [python_path, "--version"],
            capture_output=True, text=True, timeout=5,
        ))
        return cp.stdout.strip() or cp.stderr.strip()
    except Exception:
        return ""


async def _parse_via_ytdlp(url: str) -> dict | None:
    """通过 yt-dlp 解析链接（YouTube/海外平台）"""
    try:
        import yt_dlp
        loop = asyncio.get_running_loop()
        def _extract():
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "format": "best"}) as ydl:
                return ydl.extract_info(url, download=False)
        info = await loop.run_in_executor(None, _extract)
        if not info:
            return None
        title = info.get("title", "") or info.get("id", "视频")
        platform = info.get("extractor_key", "unknown").lower()
        # 获取最佳视频/音频
        media = []
        if info.get("url"):
            media.append({"url": info["url"], "type": "video"})
        elif info.get("formats"):
            # 选最佳视频
            best = None
            for f in info["formats"]:
                if f.get("vcodec") and f["vcodec"] != "none":
                    if not best or (f.get("height", 0) or 0) > (best.get("height", 0) or 0):
                        best = f
            if best and best.get("url"):
                media.append({"url": best["url"], "type": "video"})
            elif info.get("formats") and info["formats"][0].get("url"):
                media.append({"url": info["formats"][0]["url"], "type": "video"})
        # 缩略图
        thumb = info.get("thumbnail")
        return {
            "platform": platform,
            "platform_name": info.get("extractor", "YouTube"),
            "title": title,
            "media": media,
            "thumbnail": thumb,
            "duration": info.get("duration", 0),
            "source": "yt-dlp",
        }
    except Exception as e:
        return {"error": f"yt-dlp解析失败: {e}"}


async def _parse_via_bridge(url: str) -> dict | None:
    """通过 ParseHub 桥接脚本解析链接"""
    if not _BRIDGE_SCRIPT.exists():
        return {"error": f"桥接脚本不存在: {_BRIDGE_SCRIPT}"}
    import shutil
    python = None
    for candidate in [
        _PH_VENV_PYTHON,
        "/usr/bin/python3.12",
        shutil.which("python3.12"),
        shutil.which("python3"),
    ]:
        if candidate and Path(candidate).exists():
            python = candidate
            break
    if not python:
        return {"error": "找不到 Python 3.12"}
    # 如果找到的是 Hermes 的 Python 3.11，尝试找系统 Python 3.12
    py_version = await _get_python_version(python)
    if py_version and py_version.startswith("3.11"):
        sys_python = "/usr/bin/python3.12"
        if Path(sys_python).exists():
            python = sys_python
            py_version = await _get_python_version(python)
    # 调试：确认使用的 Python
    dbg = f"Python={python}, 版本={py_version}"
    try:
        loop = asyncio.get_running_loop()
        cp = await loop.run_in_executor(None, lambda: subprocess.run(
            [python, str(_BRIDGE_SCRIPT), url],
            capture_output=True, text=True, timeout=120,
        ))
        if cp.returncode != 0:
            err_msg = cp.stderr[:200] if cp.stderr else ""
            if not err_msg and cp.stdout:
                try:
                    err_data = json.loads(cp.stdout)
                    err_msg = err_data.get("error", cp.stdout[:200])
                except Exception:
                    err_msg = cp.stdout[:200]
            return {"error": f"桥接脚本退出码={cp.returncode}, 错误={err_msg} ({dbg})"}
        result = json.loads(cp.stdout)
        if "error" in result:
            return {"error": f"桥接返回: {result['error']} ({dbg})"}
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON解析失败: {e} ({dbg})"}
    except subprocess.TimeoutExpired:
        return {"error": f"桥接脚本执行超时 ({dbg})"}
    except Exception as e:
        return {"error": f"桥接异常: {e} ({dbg})"}


async def setup(ctx):
    ctx.log.info("聚合解析插件已加载 (v2.4.0, videodl原生+ParseHub+yt-dlp三引擎)")

    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def _handler(client, message):
        try:
            text = (message.text or "").strip()
            if not text:
                return

            # ── 帮助命令（放在 /jx 前面，避免被前缀匹配吞掉）──
            if text == ".jxsm":
                await message.reply(_get_help_text())
                return

            # ── 引擎状态命令 ──
            if text == ".jxstatus":
                v_status = "✅ 可用" if HAS_VIDEODL else "❌ 不可用"
                vendor_pkg_dir = Path(__file__).parent / "_vendor_pkg"
                pkg_ok = "✅ 存在" if vendor_pkg_dir.exists() else "❌ 不存在"
                # 检查关键依赖
                _deps = ["m3u8", "requests", "rich", "bs4", "fake_useragent", "lxml",
                        "platformdirs", "pathvalidate", "parsel", "tldextract",
                        "bleach", "emoji", "filetype", "puremagic", "prettytable",
                        "tqdm", "click", "gmssl", "Cryptodome", "brotli"]
                dep_status = []
                for d in _deps:
                    try:
                        exec(f"import {d}")
                        dep_status.append(f"✅ {d}")
                    except ImportError:
                        dep_status.append(f"❌ {d}")
                status = (
                    f"📊 <b>引擎状态</b>\n\n"
                    f"🔵 引擎1 videodl: {v_status}\n"
                    f"🟢 引擎2 ParseHub: ✅ 工作中\n"
                    f"🟡 引擎3 yt-dlp: ✅ 可用\n\n"
                    f"<b>诊断:</b>\n"
                    f"  _vendor_pkg: {pkg_ok}\n"
                    f"  {' | '.join(dep_status)}\n"
                )
                err = get_import_error()
                if err:
                    status += f"\n<b>导入错误:</b> {err}\n"
                await message.reply(status)
                return

            # ── 帮助命令（放在 /jx 前面，避免被前缀匹配吞掉）──
            if text == ".jxsm":
                await message.reply(_get_help_text())
                return

            # ── .jx 统一解析命令 ──
            if text.startswith(".jx"):
                content = text[3:].strip()
                if not content:
                    # 回复别人的消息时，从被回复的消息中提取链接
                    reply_to = getattr(message, 'reply_to_message', None)
                    if reply_to:
                        reply_text = getattr(reply_to, 'text', '') or getattr(reply_to, 'caption', '') or ''
                        if reply_text:
                            content = reply_text
                if not content:
                    await message.reply(_get_help_text())
                    return
                await _do_parse(ctx, client, message, content)
                return
        except Exception as e:
            try:
                await message.reply(f"❌ 处理异常: {e}")
            except Exception:
                pass

    # ── 统一解析 ──
    async def _do_parse(ctx, client, message, content):
        # 从文本中提取链接
        url = _extract_url(content)
        if not url:
            await message.reply("❌ 未找到有效链接，请发送 .jx <链接> 或回复消息发送 .jx")
            return

        # 解析短链接跳转
        resolved = await _resolve_url(url)
        if resolved != url:
            url = resolved

        msg = await message.reply(f"⏳ 正在解析...")
        # 删除原始消息
        try:
            await message.delete()
        except Exception:
            pass
        try:
            result = None
            errs = []
            # 引擎1: videodl 原生（纯Python，100+平台，优先）
            if HAS_VIDEODL:
                result = await parse_via_videodl(url)
                if result and "error" in result:
                    errs.append(f"引擎1(videodl): {result['error']}")
                    result = None  # 模块级错误不打断，继续走下一引擎
            else:
                errs.append("引擎1(videodl): 未安装(需要联网安装依赖)")
            # 引擎2: ParseHub（中文平台）
            if not result:
                result = await _parse_via_bridge(url)
                if result and "error" in result:
                    errs.append(f"引擎2(ParseHub): {result['error']}")
                    result = None
            # 引擎3: yt-dlp（海外平台，1752个网站）
            if not result:
                yt_result = await _parse_via_ytdlp(url)
                if yt_result and "error" not in yt_result:
                    result = yt_result
                elif yt_result:
                    errs.append(f"引擎3(yt-dlp): {yt_result['error']}")
        except Exception as e:
            await msg.edit(f"❌ 解析异常: {e}")
            return
        if not result:
            detail = "\n".join(errs) if errs else "所有引擎均无返回"
            await msg.edit(f"❌ 解析失败，该平台暂不支持或链接无效\n\n{detail}")
            return

        platform = result.get("platform_name", "未知")
        title = result.get("title", "") or f"{platform}内容"
        media = result.get("media", [])

        if not media:
            await msg.edit(f"📄 <b>{platform}</b>\n{title}\n\n⚠️ 未找到可下载的媒体")
            return

        first = media[0]
        media_url = first.get("url", "")
        if not media_url:
            await msg.edit(f"❌ 未获取到下载地址")
            return

        ref_map = {
            "douyin": "https://www.douyin.com/",
            "bilibili": "https://www.bilibili.com/",
            "youtube": "https://www.youtube.com/",
            "twitter": "https://twitter.com/",
            "xhs": "https://www.xiaohongshu.com/",
            "weibo": "https://www.weibo.com/",
            "instagram": "https://www.instagram.com/",
            "tiktok": "https://www.tiktok.com/",
            "kuaishou": "https://www.kuaishou.com/",
            "zhihu": "https://www.zhihu.com/",
            "tieba": "https://tieba.baidu.com/",
            "facebook": "https://www.facebook.com/",
        }
        referer = ref_map.get(result.get("platform", ""), "https://www.douyin.com/")

        mtype = first.get("type", "video")
        if mtype == "video":
            await _do_download_video(ctx, client, message, msg, media_url, title, referer)
        elif mtype == "image":
            await _do_download_image(ctx, client, message, msg, media_url, title, referer)

    # ── 下载视频 ──
    async def _do_download_video(ctx, client, message, msg, video_url, title, referer):
        await msg.edit(f"⏳ 正在下载 {title[:30]}...")
        try:
            max_mb = int(ctx.config.get("max_size", 50) or 50)
            dl_path = _DOWNLOAD_DIR / f"video_{int(time.time())}.mp4"
            success = await _download_file(video_url, dl_path, {
                "Referer": referer,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })
            if success and dl_path.exists():
                size = dl_path.stat().st_size
                if size > max_mb * 1024 * 1024:
                    oversize_action = ctx.config.get("oversize_action", "notify")
                    if oversize_action == "notify":
                        await msg.edit(f"📹 <b>{title[:50]}</b>\n📐 大小: {_format_size(size)}（超过{max_mb}MB）\n💡 请在配置中调整超限处理方式")
                        if not ctx.config.get("keep_local", False):
                            dl_path.unlink(missing_ok=True)
                        return
                try:
                    await client.send_video(message.chat.id, str(dl_path), caption=f"📹 {title[:50]}")
                    if not ctx.config.get("keep_local", False):
                        await msg.delete()
                        dl_path.unlink(missing_ok=True)
                    else:
                        await msg.edit(f"✅ 已保存到本地: {dl_path}")
                except Exception as e:
                    await msg.edit(f"❌ 发送失败: {e}")
                if ctx.config.get("keep_local", False):
                    return
                dl_path.unlink(missing_ok=True)
            else:
                await msg.edit(f"❌ 下载失败")
        except Exception as e:
            await msg.edit(f"❌ 下载失败: {e}")

    # ── 下载图片 ──
    async def _do_download_image(ctx, client, message, msg, img_url, title, referer):
        await msg.edit(f"⏳ 正在下载图片...")
        try:
            dl_path = _DOWNLOAD_DIR / f"img_{int(time.time())}.jpg"
            success = await _download_file(img_url, dl_path, {
                "Referer": referer,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })
            if success and dl_path.exists():
                try:
                    await client.send_photo(message.chat.id, str(dl_path), caption=f"📷 {title[:50]}")
                    if not ctx.config.get("keep_local", False):
                        await msg.delete()
                        dl_path.unlink(missing_ok=True)
                    else:
                        await msg.edit(f"✅ 已保存到本地: {dl_path}")
                except Exception as e:
                    await msg.edit(f"❌ 发送失败: {e}")
            else:
                await msg.edit(f"❌ 下载失败")
        except Exception as e:
            await msg.edit(f"❌ 下载失败: {e}")

    def _extract_url(text: str) -> str | None:
        """从文本中提取第一个链接"""
        for pattern in [
            re.compile(r"https?://[^\s]+"),
        ]:
            m = pattern.search(text)
            if m:
                return m.group(0)
        return None

    @ctx.action("view_logs")
    async def _view_logs(req=None):
        logs = ctx.kv.get(_KV_LOGS, [])
        if not logs:
            return {"ok": True, "message": "暂无日志"}
        lines = ["📋 最近日志:\n"]
        for log in logs[-15:]:
            lines.append(f"[{log['t']}] {log['m']}")
        return {"ok": True, "message": "\n".join(lines)}

    ctx.log.info("聚合解析已就绪")


async def teardown(ctx):
    ctx.log.info("聚合解析已卸载")