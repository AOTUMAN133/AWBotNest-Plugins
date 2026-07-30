# -*- coding: utf-8 -*-
# AWBotNest 插件：AI 图片生成 (mydraw) v1.0.0
# 使用 pollinations.ai 免费生成图片

import os
import re
import asyncio
import httpx
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path(".tmp/mydraw_downloads")
_POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"

__plugin__ = {
    "name": "AI 图片生成",
    "id": "mydraw",
    "version": "1.1.1",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mydraw_v1.svg",
    "author": "凹凸曼",
    "description": "AI 图片生成。支持 .st 提示词 生成图片，免费免 Key",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "width": {
            "type": "number", "default": 1024, "label": "图片宽度",
            "section": "生成", "min": 256, "max": 2048, "step": 64,
            "help": "生成图片的宽度"
        },
        "height": {
            "type": "number", "default": 1024, "label": "图片高度",
            "section": "生成", "min": 256, "max": 2048, "step": 64,
            "help": "生成图片的高度"
        },
        "seed": {
            "type": "number", "default": -1, "label": "随机种子(-1=随机)",
            "section": "生成", "min": -1, "max": 999999,
            "help": "固定种子可获得相同结果，-1 为随机"
        },
        "keep_local": {
            "type": "boolean", "default": False, "label": "保留本地文件",
            "section": "生成",
            "help": "发送后不删除本地生成的图片"
        },
    },
}


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


async def _generate_image(prompt: str, width: int = 1024, height: int = 1024, seed: int = -1) -> bytes | None:
    """调用 pollinations.ai 生成图片，返回图片二进制数据"""
    import urllib.parse
    encoded = urllib.parse.quote(prompt)

    # 构建参数
    params = f"?width={width}&height={height}"
    if seed >= 0:
        params += f"&seed={seed}"

    url = f"{_POLLINATIONS_URL}{encoded}{params}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as cli:
            r = await cli.get(url, headers=headers)
            if r.status_code == 200:
                return r.content
            return None
    except Exception:
        return None


async def setup(ctx):
    ctx.log.info("AI 图片生成 v1.0.0 已加载")

    @ctx.on_message(ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        # .stsm — 帮助（30秒自毁）
        if text == ".stsm":
            help_text = (
                "🎨 <b>AI 图片生成 v1.0.0</b>\n\n"
                "📝 <b>生成图片</b>\n"
                "  <code>.st 一只猫在太空</code> — 根据提示词生成图片\n"
                "  <code>.st 赛博朋克城市 --宽 1280 --高 720</code> — 指定尺寸\n\n"
                "⚙️ 可在插件配置中调整默认尺寸和随机种子\n"
                "🔗 基于 pollinations.ai，免费免 Key"
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

        # .st help — 帮助（30秒自毁）
        if text == ".st help":
            help_text = (
                "🎨 <b>AI 图片生成 v1.0.0</b>\n\n"
                "📝 <b>生成图片</b>\n"
                "  <code>.st 一只猫在太空</code> — 根据提示词生成图片\n"
                "  <code>.st 赛博朋克城市 --宽 1280 --高 720</code> — 指定尺寸\n\n"
                "⚙️ 可在插件配置中调整默认尺寸和随机种子\n"
                "🔗 基于 pollinations.ai，免费免 Key"
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

        if not text.startswith(".st"):
            return

        cmd = text[len(".st"):].strip()
        chat_id = message.chat.id

        if not cmd:
            await message.reply("🎨 用法: <code>.st 提示词</code> 生成图片，或 <code>.st help</code> 查看帮助")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # 解析参数
        width = int(ctx.config.get("width", 1024))
        height = int(ctx.config.get("height", 1024))
        seed = int(ctx.config.get("seed", -1))

        # 支持命令行参数 --宽/--width --高/--height --seed
        wm = re.search(r"--宽\s*(\d+)", cmd)
        if wm:
            width = int(wm.group(1))
            cmd = cmd.replace(wm.group(0), "")
        wm = re.search(r"--width\s*(\d+)", cmd, re.IGNORECASE)
        if wm:
            width = int(wm.group(1))
            cmd = cmd.replace(wm.group(0), "")

        hm = re.search(r"--高\s*(\d+)", cmd)
        if hm:
            height = int(hm.group(1))
            cmd = cmd.replace(hm.group(0), "")
        hm = re.search(r"--height\s*(\d+)", cmd, re.IGNORECASE)
        if hm:
            height = int(hm.group(1))
            cmd = cmd.replace(hm.group(0), "")

        sm = re.search(r"--seed\s*(\d+)", cmd, re.IGNORECASE)
        if sm:
            seed = int(sm.group(1))
            cmd = cmd.replace(sm.group(0), "")

        prompt = cmd.strip()
        if not prompt:
            await message.reply("🎨 请输入提示词，如: <code>.st 一只猫在太空</code>")
            try:
                await message.delete()
            except Exception:
                pass
            return

        wait = await message.reply(f"🎨 正在生成: {prompt}\n⏳ 请稍候...")

        try:
            await message.delete()
        except Exception:
            pass

        img_data = await _generate_image(prompt, width, height, seed)

        if not img_data:
            await wait.edit_text("❌ 图片生成失败，请稍后重试")
            return

        # 保存并发送
        _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filepath = _DOWNLOAD_DIR / f"mydraw_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.png"
        filepath.write_bytes(img_data)

        await wait.delete()
        try:
            with open(filepath, "rb") as f:
                await client.send_photo(chat_id, f, caption=f"🎨 {prompt}\n{width}x{height}")
            if not ctx.config.get("keep_local", False):
                filepath.unlink(missing_ok=True)
        except Exception as e:
            await message.reply(f"❌ 发送失败: {e}")

    ctx.log.info("AI 图片生成 v1.0.0 已就绪")


async def teardown(ctx):
    ctx.log.info("AI 图片生成已卸载")