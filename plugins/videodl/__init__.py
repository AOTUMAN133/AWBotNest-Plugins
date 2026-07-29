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

__plugin__ = {
    "name": "聚合解析",
    "id": "videodl",
    "version": "2.2.1",
    "author": "凹凸曼",
    "description": "多平台视频/图文解析下载。支持 /jx 解析链接，直接发送链接自动解析。支持抖音/B站/YouTube/小红书/Twitter/微博等20+平台。",
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
            "section": "下载", "order": 2,
            "options": [
                {"value": "saved", "label": "发送到收藏夹"},
                {"value": "link", "label": "仅发送下载链接"},
                {"value": "force", "label": "直接发送"},
                {"value": "notify", "label": "提示用户"},
            ]
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
_PH_VENV_PYTHON = "/root/.hermes/plugins_env/ph_venv/bin/python3"


def _log(ctx, msg: str):
    logs = ctx.kv.get(_KV_LOGS, [])
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
        "  /jx <链接或分享文本>  — 解析并下载\n\n"
        "📌 <b>支持平台</b>\n"
        "  🎬 抖音 · B站 · YouTube · TikTok · 快手\n"
        "  📷 小红书 · 微博 · Instagram · Twitter/X\n"
        "  📝 知乎 · 贴吧 · 微信公众号 · 酷安\n"
        "  🎮 小黑盒 · 最右\n\n"
        "📌 <b>说明</b>\n"
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


async def _parse_via_bridge(url: str) -> dict | None:
    """通过 ParseHub 桥接脚本解析链接"""
    if not _BRIDGE_SCRIPT.exists():
        return {"error": f"桥接脚本不存在: {_BRIDGE_SCRIPT}"}
    import shutil
    python = shutil.which("python3.12") or shutil.which("python3")
    if not python:
        return {"error": "找不到 Python 3.12"}
    # 如果找到的是 Hermes 的 Python 3.11，尝试找系统 Python 3.12
    py_version = await _get_python_version(python)
    if py_version and py_version.startswith("3.11"):
        sys_python = "/usr/bin/python3.12"
        if Path(sys_python).exists():
            python = sys_python
    # 设置 PYTHONPATH 指向 venv 的 site-packages（确保 parsehub 可导入）
    sp = str(Path("/root/.hermes/plugins_env/ph_venv/lib/python3.12/site-packages"))
    try:
        loop = asyncio.get_running_loop()
        cp = await loop.run_in_executor(None, lambda: subprocess.run(
            [python, str(_BRIDGE_SCRIPT), url],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "PYTHONPATH": sp},
        ))
        if cp.returncode != 0:
            err_msg = cp.stderr[:200] if cp.stderr else ""
            if not err_msg and cp.stdout:
                try:
                    err_data = json.loads(cp.stdout)
                    err_msg = err_data.get("error", cp.stdout[:200])
                except Exception:
                    err_msg = cp.stdout[:200]
            return {"error": f"桥接脚本退出码={cp.returncode}, 错误={err_msg}"}
        result = json.loads(cp.stdout)
        if "error" in result:
            return {"error": f"桥接返回: {result['error']}"}
        return result
    except json.JSONDecodeError as e:
        return {"error": f"JSON解析失败: {e}"}
    except subprocess.TimeoutExpired:
        return {"error": "桥接脚本执行超时"}
    except Exception as e:
        return {"error": f"桥接异常: {e}"}


async def setup(ctx):
    ctx.log.info("聚合解析插件已加载 (v2.2.1, ParseHub多平台)")

    @ctx.on_message(ctx.filters.text, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # ── /jx 统一解析命令 ──
        if text.startswith("/jx "):
            content = text[4:].strip()
            await _do_parse(ctx, client, message, content)
            return

        # ── 帮助命令 ──
        if text == "/jxsm":
            await message.reply(_get_help_text())
            return

    # ── 统一解析 ──
    async def _do_parse(ctx, client, message, content):
        # 从文本中提取链接
        url = _extract_url(content)
        if not url:
            await message.reply("❌ 未找到有效链接，请发送 /jx <链接>")
            return

        msg = await message.reply(f"⏳ 正在解析...")
        try:
            result = await _parse_via_bridge(url)
        except Exception as e:
            await msg.edit(f"❌ 解析异常: {e}")
            return
        if not result:
            await msg.edit(f"❌ 解析失败，该平台暂不支持或链接无效")
            return
        if "error" in result:
            await msg.edit(f"❌ {result['error']}")
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
                        dl_path.unlink(missing_ok=True)
                        return
                try:
                    await client.send_video(message.chat.id, str(dl_path), caption=f"📹 {title[:50]}")
                    await msg.delete()
                except Exception as e:
                    await msg.edit(f"❌ 发送失败: {e}")
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
                    await msg.delete()
                except Exception as e:
                    await msg.edit(f"❌ 发送失败: {e}")
                dl_path.unlink(missing_ok=True)
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