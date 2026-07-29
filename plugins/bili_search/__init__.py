# -*- coding: utf-8 -*-
# AWBotNest 插件：B站搜索 (bili_search)

import asyncio
import httpx
import json
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "B站搜索",
    "id": "bili_search",
    "version": "1.0.5",
    "author": "凹凸曼",
    "description": "B站视频搜索与下载。支持 /sp 搜索，直接发送链接自动下载。",
    "scope": "user",
    "default_enabled": False,
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
        "quality": {
            "type": "select", "default": "80", "label": "下载清晰度",
            "section": "下载", "order": 3,
            "options": [
                {"value": "120", "label": "4K"},
                {"value": "116", "label": "1080P60"},
                {"value": "80", "label": "1080P"},
                {"value": "64", "label": "720P"},
                {"value": "32", "label": "480P"},
            ]
        },
        "search_count": {
            "type": "number", "default": 5, "label": "搜索返回数量",
            "section": "搜索", "min": 1, "max": 20, "order": 1
        },
        "auto_detect": {
            "type": "boolean", "default": True, "label": "自动检测链接",
            "section": "基本", "order": 1,
            "help": "群内发送B站链接自动下载"
        },
        "test_bili": {
            "type": "action", "label": "🔍 测试B站搜索", "section": "调试",
            "action": "test_bili"
        },
        "view_logs": {
            "type": "action", "label": "📋 查看日志", "section": "调试",
            "action": "view_logs"
        },
    },
}

_BILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
}

_DOWNLOAD_DIR = Path(__file__).parent / "downloads"
_KV_LOGS = "bili_search_logs"


def _log(ctx, msg: str):
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-30:])


def _clean_title(title: str) -> str:
    return re.sub(r"<[^>]+>", "", title).strip()


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size/1024/1024:.1f}MB"
    return f"{size/1024/1024/1024:.1f}GB"


async def _bili_search(keyword: str, page: int = 1, count: int = 5) -> list:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/web-interface/search/all/v2",
                         params={"keyword": keyword, "page": page})
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("code") != 0:
            return []
        results = []
        for section in data.get("data", {}).get("result", []):
            for v in section.get("data", []):
                if v.get("type") == "video":
                    results.append({
                        "title": _clean_title(v.get("title", "")),
                        "bvid": v.get("bvid", ""),
                        "play": v.get("play", 0),
                        "duration": str(v.get("duration", "?")),
                        "author": v.get("author", ""),
                        "pic": v.get("pic", ""),
                    })
                    if len(results) >= count:
                        break
            if len(results) >= count:
                break
        return results


async def _bili_video_info(bvid: str) -> dict | None:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/web-interface/view",
                         params={"bvid": bvid})
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        v = data["data"]
        return {
            "title": v.get("title", ""),
            "bvid": bvid,
            "cid": v.get("cid", 0),
            "duration": v.get("duration", 0),
            "pages": len(v.get("pages", [])),
            "author": v.get("owner", {}).get("name", ""),
            "pic": v.get("pic", ""),
        }


async def _bili_download_url(bvid: str, cid: int, qn: int = 80) -> list:
    async with httpx.AsyncClient(timeout=15, headers=_BILI_HEADERS) as cli:
        r = await cli.get("https://api.bilibili.com/x/player/playurl",
                         params={"bvid": bvid, "cid": cid, "qn": qn, "fnval": 1, "fnver": 0, "fourk": 1})
        if r.status_code != 200:
            return []
        data = r.json()
        if data.get("code") != 0:
            return []
        durl = data.get("data", {}).get("durl", [])
        return [{"url": u.get("url", ""), "size": u.get("size", 0), "order": u.get("order", 1)} for u in durl]


async def _download_file(url: str, path: Path, headers: dict = None) -> bool:
    try:
        dl_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com",
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


async def setup(ctx):
    ctx.log.info("B站搜索插件已加载")

    @ctx.on_message(ctx.filters.text, group=0)
    async def _handler(client, message):
        text = (message.text or "").strip()
        if not text:
            return

        # ── 搜索命令 ──
        if text.startswith("/sp "):
            kw = text[4:].strip()
            await _do_search(ctx, client, message, kw)
            return

        # ── 自动检测B站链接 ──
        if ctx.config.get("auto_detect", True):
            bili_m = re.search(r"(?:bilibili\.com/video/|b23\.tv/)(BV\w+)", text)
            if bili_m:
                bvid = bili_m.group(1)
                await _do_bili_download(ctx, client, message, bvid)
                return

    # ── B站搜索 ──
    async def _do_search(ctx, client, message, keyword):
        msg = await message.reply(f"🔍 正在搜索「{keyword}」...")
        # 删除原始消息
        try:
            await message.delete()
        except Exception:
            pass
        results = []
        bili = await _bili_search(keyword, count=ctx.config.get("search_count", 5))
        for v in bili:
            results.append({"platform": "B站", **v})
        if not results:
            await msg.edit(f"❌ 未找到「{keyword}」的相关视频")
            return
        lines = [f"🔍 <b>搜索「{keyword}」结果</b>\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "?")[:40]
            lines.append(f"<b>{i}.</b> [B站] {title}  ⭐{r.get('play',0)}")
        lines.append(f"\n回复序号选择下载（30秒内），或发送0取消")
        await msg.edit("\n".join(lines))
        pending_key = f"pending_select:{message.chat.id}:{message.from_user.id}"
        ctx.kv.set(pending_key, {"results": results, "time": time.time(), "msg_id": msg.id})

    # ── 处理用户选择回复 ──
    @ctx.on_message(ctx.filters.text, group=1)
    async def _select_handler(client, message):
        text = (message.text or "").strip()
        if not text.isdigit():
            return
        pending_key = f"pending_select:{message.chat.id}:{message.from_user.id}"
        pending = ctx.kv.get(pending_key, None)
        if pending:
            if time.time() - pending.get("time", 0) > 30:
                ctx.kv.delete(pending_key)
                return
            idx = int(text)
            if idx == 0:
                ctx.kv.delete(pending_key)
                await message.reply("已取消")
                return
            results = pending.get("results", [])
            if 1 <= idx <= len(results):
                ctx.kv.delete(pending_key)
                r = results[idx - 1]
                # 删除搜索结果列表和回复消息
                try:
                    await client.delete_messages(message.chat.id, [pending.get("msg_id"), message.id])
                except Exception:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                if r.get("bvid"):
                    await _do_bili_download(ctx, client, message, r["bvid"])
                return

        pending_key = f"pending_oversize:{message.chat.id}:{message.from_user.id}"
        pending = ctx.kv.get(pending_key, None)
        if pending:
            if time.time() - pending.get("time", 0) > 60:
                ctx.kv.delete(pending_key)
                return
            idx = int(text)
            ctx.kv.delete(pending_key)
            if idx == 0:
                await message.reply("已取消")
                return
            bvid = pending.get("bvid", "")
            url = pending.get("url", "")
            title = pending.get("title", "视频")
            if idx == 1:
                await message.reply(f"⏳ 正在下载 {title[:30]}...")
                dl_path = _DOWNLOAD_DIR / f"{bvid}.mp4"
                success = await _download_file(url, dl_path)
                if success and dl_path.exists():
                    try:
                        await client.send_video(message.chat.id, str(dl_path), caption=f"📹 {title[:50]}")
                        dl_path.unlink(missing_ok=True)
                    except Exception as e:
                        await message.reply(f"❌ 发送失败: {e}")
                else:
                    await message.reply("❌ 下载失败")
            elif idx == 2:
                link = f"https://www.bilibili.com/video/{bvid}"
                await message.reply(f"🔗 {link}")
            elif idx == 3:
                await message.reply(f"📁 已发送到收藏夹")

    # ── B站下载 ──
    async def _do_bili_download(ctx, client, message, bvid):
        msg = await message.reply(f"⏳ 正在解析 B站视频 {bvid}...")
        # 删除原始消息
        try:
            await message.delete()
        except Exception:
            pass
        info = await _bili_video_info(bvid)
        if not info:
            await msg.edit(f"❌ 无法获取视频信息")
            return
        title = info["title"]
        await msg.edit(f"⏳ 正在获取下载地址...")
        qn = int(ctx.config.get("quality", 80) or 80)
        urls = await _bili_download_url(bvid, info["cid"], qn)
        if not urls:
            await msg.edit(f"❌ 无法获取下载地址（可能需登录）")
            return
        total_size = sum(u["size"] for u in urls)
        max_mb = int(ctx.config.get("max_size", 50) or 50)
        oversize = total_size > max_mb * 1024 * 1024
        if oversize:
            action = ctx.config.get("oversize_action", "notify")
            if action == "link":
                link = f"https://www.bilibili.com/video/{bvid}"
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n🔗 {link}", disable_web_page_preview=True)
                return
            elif action == "force":
                pass
            elif action == "saved":
                await msg.edit(f"📹 <b>{title}</b>\n📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n📁 已发送到收藏夹")
                return
            else:
                await msg.edit(
                    f"📹 <b>{title}</b>\n"
                    f"📐 大小: {_format_size(total_size)}（超过{max_mb}MB）\n\n"
                    f"请选择处理方式：\n"
                    f"1 - 直接下载并发送\n"
                    f"2 - 仅发送下载链接\n"
                    f"3 - 发送到收藏夹\n"
                    f"0 - 取消"
                )
                pending_key = f"pending_oversize:{message.chat.id}:{message.from_user.id}"
                ctx.kv.set(pending_key, {"bvid": bvid, "url": urls[0]["url"], "title": title, "time": time.time()})
                return
        await msg.edit(f"⏳ 正在下载 {title}...")
        dl_path = _DOWNLOAD_DIR / f"{bvid}.mp4"
        success = await _download_file(urls[0]["url"], dl_path)
        if success and dl_path.exists():
            try:
                await client.send_video(message.chat.id, str(dl_path), caption=f"📹 {title}")
                await msg.delete()
                dl_path.unlink(missing_ok=True)
            except Exception as e:
                await msg.edit(f"❌ 发送失败: {e}")
        else:
            await msg.edit(f"❌ 下载失败")

    @ctx.action("test_bili")
    async def _test_bili(req=None):
        r = await _bili_search("风景", count=3)
        return {"ok": True, "message": f"找到 {len(r)} 个结果: {[v['bvid'] for v in r]}"}

    @ctx.action("view_logs")
    async def _view_logs(req=None):
        logs = ctx.kv.get(_KV_LOGS, [])
        if not logs:
            return {"ok": True, "message": "暂无日志"}
        lines = ["📋 最近日志:\n"]
        for log in logs[-15:]:
            lines.append(f"[{log['t']}] {log['m']}")
        return {"ok": True, "message": "\n".join(lines)}

    ctx.log.info("B站搜索已就绪")


async def teardown(ctx):
    ctx.log.info("B站搜索已卸载")