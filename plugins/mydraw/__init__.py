# -*- coding: utf-8 -*-
# AWBotNest 插件：豆包多模态 (mydraw) v2.0.0
# 基于 doubao2api，免费文生图/视频/音乐

import asyncio
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path("/tmp/mydraw_downloads")

__plugin__ = {
    "name": "豆包多模态",
    "id": "mydraw",
    "version": "2.0.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mydraw_v1.svg",
    "author": "凹凸曼",
    "description": "豆包 AI 多模态生成。支持 .dt 文生图，.dtv 文生视频，.dtm 文生音乐。免费免 Key，扫码登录豆包账号即可使用。",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["aiohttp"],
    "config_schema": {
        "ratio": {
            "type": "select", "default": "1:1", "label": "默认比例",
            "section": "生成",
            "options": {"1:1": "1:1 正方形", "16:9": "16:9 横屏", "9:16": "9:16 竖屏", "4:3": "4:3", "3:4": "3:4"},
        },
        "music_genre": {
            "type": "select", "default": "Pop", "label": "默认音乐风格",
            "section": "生成",
            "options": {
                "Pop": "流行", "Rock": "摇滚", "Folk": "民谣",
                "Electronic": "电音", "Hip Hop/Rap": "嘻哈",
                "Chinese Style": "国风", "DJ": "DJ", "R&B/Soul": "R&B",
                "Reggae": "雷鬼", "Punk": "朋克", "Jazz": "爵士",
            },
        },
        "music_mood": {
            "type": "select", "default": "Happy", "label": "默认音乐情绪",
            "section": "生成",
            "options": {
                "Happy": "快乐", "Chill": "放松", "Dynamic/Energetic": "活力",
                "Excited": "兴奋", "Sentimental/Melancholic/Lonely": "忧郁",
                "Inspirational/Hopeful": "鼓舞", "Sorrow/Sad": "伤感",
                "Nostalgic/Memory": "怀旧", "Romantic": "浪漫",
            },
        },
        "music_gender": {
            "type": "select", "default": "Female", "label": "默认歌手性别",
            "section": "生成",
            "options": {"Male": "男声", "Female": "女声"},
        },
        "video_timeout": {
            "type": "number", "default": 300, "label": "视频生成超时(秒)",
            "section": "生成", "min": 60, "max": 600,
        },
        # 登录状态
        "_login_status": {
            "type": "info", "label": "登录状态", "section": "豆包账号",
        },
        "_login_qr": {
            "type": "action", "label": "📱 扫码登录豆包", "section": "豆包账号",
            "action": "qr_login", "danger": False,
        },
        "_login_check": {
            "type": "action", "label": "🔄 检查登录状态", "section": "豆包账号",
            "action": "check_login", "danger": False,
        },
    },
}

_SESSION_FILE = "doubao_session.json"
_CLIENT_INSTANCE = None
_CLIENT_LOCK = asyncio.Lock()


async def _get_client(ctx) -> object | None:
    """获取或创建客户端"""
    global _CLIENT_INSTANCE
    session_path = ctx.data_dir / _SESSION_FILE
    if not session_path.exists():
        return None
    async with _CLIENT_LOCK:
        if _CLIENT_INSTANCE is None:
            try:
                from _doubao2api import DoubaoChatClient
                _CLIENT_INSTANCE = DoubaoChatClient.from_session(str(session_path))
                _CLIENT_INSTANCE._session_path = session_path
                ctx.log.info("豆包客户端已加载")
            except Exception as e:
                ctx.log.error("豆包客户端加载失败: %s", e)
                return None
        return _CLIENT_INSTANCE


async def setup(ctx):
    ctx.log.info("豆包多模态 v2.0.0 已加载")

    # 恢复登录状态
    session_path = ctx.data_dir / _SESSION_FILE
    if session_path.exists():
        try:
            from _doubao2api.session import load_session
            session = load_session(str(session_path))
            if session.get("cookies", {}).get("sessionid"):
                ctx.update_config({"_login_status": "✅ 已登录"})
        except Exception:
            pass

    # ── 扫码登录 ──
    @ctx.action("qr_login")
    async def _qr_login(req=None):
        from _doubao2api.qr_login import QRLogin
        try:
            result = QRLogin.login_and_save(str(ctx.data_dir / _SESSION_FILE))
            ctx.update_config({"_login_status": "✅ 已登录"})
            global _CLIENT_INSTANCE
            _CLIENT_INSTANCE = None
            return {"ok": True, "message": "✅ 豆包登录成功"}
        except Exception as e:
            return {"ok": False, "message": f"❌ 登录失败: {e}"}

    @ctx.action("check_login")
    async def _check_login(req=None):
        session_path = ctx.data_dir / _SESSION_FILE
        if session_path.exists():
            try:
                from _doubao2api.session import load_session
                session = load_session(str(session_path))
                if session.get("cookies", {}).get("sessionid"):
                    ctx.update_config({"_login_status": "✅ 已登录"})
                    return {"ok": True, "message": "✅ 已登录"}
            except Exception:
                pass
        ctx.update_config({"_login_status": "❌ 未登录"})
        return {"ok": False, "message": "❌ 未登录，请先扫码登录"}

    # ── 命令处理 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        # 命令分发
        if text.startswith(".dt "):
            await _handle_image(ctx, client, message, text[4:])
        elif text.startswith(".dtv "):
            await _handle_video(ctx, client, message, text[5:])
        elif text.startswith(".dtm "):
            await _handle_music(ctx, client, message, text[5:])
        elif text == ".dt help":
            help_text = (
                "🎨 <b>豆包多模态 v2.0.0</b>\n\n"
                "📝 <b>生成图片</b>\n"
                "  <code>.dt 一只柴犬</code> — 文生图\n\n"
                "🎬 <b>生成视频</b>\n"
                "  <code>.dtv 一只柴犬奔跑</code> — 文生视频（约1-3分钟）\n\n"
                "🎵 <b>生成音乐</b>\n"
                "  <code>.dtm 一首轻快的歌</code> — 文生音乐\n"
                "  <code>.dtm 星空之歌 --lyric 星光洒满夜空</code> — 自定义歌词\n\n"
                "⚙️ 可在配置中调整默认比例/风格/情绪\n"
                "🔗 基于豆包 AI，免费免 Key"
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

    ctx.log.info("豆包多模态 v2.0.0 已就绪")


async def _get_or_create_client(ctx):
    """获取或创建客户端，登录态检查"""
    client = await _get_client(ctx)
    if client is None:
        return None
    try:
        async with client:
            me = await client.get_current_user()
            if me:
                return client
    except Exception:
        pass
    return None


async def _handle_image(ctx, client, message, prompt):
    """处理文生图"""
    if not prompt:
        await message.reply("🎨 请输入提示词，如: <code>.dt 一只柴犬</code>")
        return

    # 解析参数
    ratio = ctx.config.get("ratio", "1:1")
    wm = __import__("re").search(r"--ratio\s*([\d:]+)", prompt)
    if wm:
        ratio = wm.group(1)
        prompt = prompt.replace(wm.group(0), "")

    wait = await message.reply(f"🎨 正在生成图片: {prompt}\n⏳ 请稍候...")
    try:
        await message.delete()
    except Exception:
        pass

    try:
        db = await _get_or_create_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
            return

        async with db:
            result = await db.generate_image(prompt=prompt.strip(), ratio=ratio)
            if result.images:
                img = result.images[0]
                _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                filepath = _DOWNLOAD_DIR / f"dt_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.png"
                # 下载图片
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(img.ori_url) as r:
                        if r.status == 200:
                            filepath.write_bytes(await r.read())
                await wait.delete()
                with open(filepath, "rb") as f:
                    await client.send_photo(message.chat.id, f, caption=f"🎨 {prompt}\n{ratio}")
                if not ctx.config.get("keep_local", False):
                    filepath.unlink(missing_ok=True)
            else:
                await wait.edit_text("❌ 图片生成失败")
    except Exception as e:
        await wait.edit_text(f"❌ 生成失败: {e}")


async def _handle_video(ctx, client, message, prompt):
    """处理文生视频"""
    if not prompt:
        await message.reply("🎬 请输入提示词，如: <code>.dtv 一只柴犬奔跑</code>")
        return

    ratio = ctx.config.get("ratio", "16:9")
    timeout = int(ctx.config.get("video_timeout", 300) or 300)

    wait = await message.reply(f"🎬 正在生成视频: {prompt}\n⏳ 大约需要1-3分钟...")
    try:
        await message.delete()
    except Exception:
        pass

    try:
        db = await _get_or_create_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
            return

        async with db:
            result = await db.generate_video(prompt=prompt.strip(), ratio=ratio, timeout=timeout)
            if result.videos:
                v = result.videos[0]
                _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                filepath = _DOWNLOAD_DIR / f"dtv_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(v.video_url) as r:
                        if r.status == 200:
                            filepath.write_bytes(await r.read())
                await wait.delete()
                with open(filepath, "rb") as f:
                    await client.send_video(message.chat.id, f, caption=f"🎬 {prompt}\n{v.duration}s")
                if not ctx.config.get("keep_local", False):
                    filepath.unlink(missing_ok=True)
            else:
                await wait.edit_text("❌ 视频生成失败")
    except Exception as e:
        await wait.edit_text(f"❌ 生成失败: {e}")


async def _handle_music(ctx, client, message, cmd):
    """处理文生音乐"""
    if not cmd:
        await message.reply("🎵 请输入提示词，如: <code>.dtm 一首轻快的歌</code>")
        return

    prompt = cmd.strip()
    lyric = None
    genre = ctx.config.get("music_genre", "Pop")
    mood = ctx.config.get("music_mood", "Happy")
    gender = ctx.config.get("music_gender", "Female")

    # 解析参数
    import re
    lm = re.search(r"--lyric\s+(.+)", prompt)
    if lm:
        lyric = lm.group(1).strip()
        prompt = prompt.replace(lm.group(0), "")

    gm = re.search(r"--genre\s+(\S+)", prompt)
    if gm:
        genre = gm.group(1)
        prompt = prompt.replace(gm.group(0), "")

    mm = re.search(r"--mood\s+(\S+)", prompt)
    if mm:
        mood = mm.group(1)
        prompt = prompt.replace(mm.group(0), "")

    prompt = prompt.strip()

    wait = await message.reply(f"🎵 正在生成音乐: {prompt}\n⏳ 大约需要30-60秒...")
    try:
        await message.delete()
    except Exception:
        pass

    try:
        db = await _get_or_create_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
            return

        async with db:
            kwargs = {"prompt": prompt, "genre": genre, "mood": mood, "gender": gender}
            if lyric:
                kwargs["lyric"] = lyric
                kwargs["generation_type"] = "custome_lyric"
            result = await db.generate_music(**kwargs)
            if result.tracks:
                track = result.tracks[0]
                _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                filepath = _DOWNLOAD_DIR / f"dtm_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(track.audio_url) as r:
                        if r.status == 200:
                            filepath.write_bytes(await r.read())
                await wait.delete()
                caption = f"🎵 {track.title}\n{genre} | {mood} | {gender}\n时长: {track.duration:.0f}s"
                with open(filepath, "rb") as f:
                    await client.send_audio(message.chat.id, f, caption=caption)
                if not ctx.config.get("keep_local", False):
                    filepath.unlink(missing_ok=True)
            else:
                await wait.edit_text("❌ 音乐生成失败")
    except Exception as e:
        await wait.edit_text(f"❌ 生成失败: {e}")


async def teardown(ctx):
    global _CLIENT_INSTANCE
    _CLIENT_INSTANCE = None
    ctx.log.info("豆包多模态已卸载")