# -*- coding: utf-8 -*-
# AWBotNest 插件：Cosplay (mycosplay)

import asyncio
import os
import re
import tempfile
import httpx
from html import escape

__plugin__ = {
    "name": "Cosplay",
    "id": "mycosplay",
    "version": "1.0.1",
    "author": "凹凸曼",
    "description": "从 cosplaytele.com 获取随机cosplay图片。用法: .cos [数量]",
    "scope": "user",
    "requirements": ["httpx"],
}

BASE_URL = "https://cosplaytele.com/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
MAX_IMAGES = 10
TIMEOUT = 30


async def _fetch_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as cli:
        r = await cli.get(url)
        return r.text


async def _get_random_photo_set() -> dict | None:
    """获取随机套图"""
    html = await _fetch_html(BASE_URL)
    # 提取套图链接: https://cosplaytele.com/NAME-N/
    links = re.findall(r'href="(https://cosplaytele\.com/[^"/]+/?)"', html)
    links = [l for l in links if not any(x in l for x in ("wp-", "feed", "xmlrpc", "page", "category", ".png", ".css", ".js", "explore", "top-search", "24-hours", "best-cosplayer"))]
    if not links:
        return None
    import random
    url = random.choice(links).rstrip("/") + "/"
    title = url.rstrip("/").split("/")[-1].replace("-", " ")
    return {"url": url, "title": title}


async def _get_gallery_images(photo_set_url: str) -> list[str]:
    """获取套图页面中的所有图片URL"""
    html = await _fetch_html(photo_set_url)
    images = []
    # 提取 <figure class="gallery-item"> 中的图片
    for m in re.finditer(r'<figure[^>]*gallery-item[^>]*>.*?<img[^>]*src="([^"]+)"', html, re.DOTALL):
        src = m.group(1)
        if src.startswith("http") and re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", src.lower()):
            images.append(src)
    # 备用: 直接提取所有图片
    if not images:
        for m in re.finditer(r'<img[^>]*src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', html, re.I):
            images.append(m.group(1))
    return images


async def _download_image(url: str) -> str | None:
    """下载图片到临时文件"""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as cli:
            r = await cli.get(url)
            if r.status_code != 200:
                return None
            ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
            if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg"
            fd, path = tempfile.mkstemp(suffix=ext)
            os.write(fd, r.content)
            os.close(fd)
            return path
    except Exception:
        return None


async def setup(ctx):
    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=7)
    async def _cos_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith(".cos") and not text.startswith(".cosplay"):
            return

        parts = text.split()
        count = 1
        if len(parts) > 1 and parts[1].isdigit():
            count = min(int(parts[1]), MAX_IMAGES)

        try:
            await message.edit(f"⏳ 正在搜索随机套图...")

            # 获取随机套图
            photo_set = await _get_random_photo_set()
            if not photo_set:
                await message.edit("❌ 未找到套图")
                return

            await message.edit(f"📸 套图: {photo_set['title']}，正在获取图片列表...")

            # 获取图片列表
            images = await _get_gallery_images(photo_set["url"])
            if not images:
                await message.edit("❌ 未找到图片")
                return

            # 随机选择
            import random
            selected = random.sample(images, min(count, len(images)))

            await message.edit(f"⏳ 正在下载 {len(selected)} 张图片...")

            # 下载图片
            files = []
            for url in selected:
                path = await _download_image(url)
                if path:
                    files.append(path)
                if len(files) >= count:
                    break

            if not files:
                await message.edit("❌ 下载失败")
                return

            await message.edit("📤 正在发送...")

            # 发送图片
            caption = f"套图链接: {photo_set['url']}"
            if len(files) == 1:
                await client.send_photo(message.chat.id, files[0], caption=caption)
            else:
                media = [{"type": "photo", "file": f, "caption": caption if i == 0 else ""} for i, f in enumerate(files)]
                try:
                    await client.send_media_group(message.chat.id, media)
                except Exception:
                    for f in files:
                        await client.send_photo(message.chat.id, f, caption=caption if len(files) == 1 else "")
                        await asyncio.sleep(0.5)

            # 清理临时文件
            for f in files:
                try:
                    os.remove(f)
                except Exception:
                    pass

            try:
                await message.delete()
            except Exception:
                pass

        except Exception as e:
            await message.edit(f"❌ 错误: {e}")


async def teardown(ctx):
    pass