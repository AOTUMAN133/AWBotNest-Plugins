# -*- coding: utf-8 -*-
# AWBotNest V2 插件：豆包多模态 (mydraw) v2.0.0
# 基于 doubao2api，免费文生图/视频/音乐

import asyncio
import json
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path("/tmp/mydraw_downloads")

__plugin__ = {
    "name": "豆包多模态",
    "id": "mydraw",
    "version": "2.0.1",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mydraw_v1.svg",
    "author": "凹凸曼",
    "description": "豆包 AI 多模态生成。支持 .st 文生图，.ssp 文生视频，.sy 文生音乐。免费免 Key，扫码登录豆包账号即可使用。",
    "tags": ["AI生图", "豆包"],
    "scope": "user",
    "requirements": ["aiohttp"],
    "plugin_api_version": 2,
    "resources": {
        "timeout_seconds": 180,
        "max_concurrency": 8,
        "max_background_tasks": 16,
        "failure_threshold": 5,
    },
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
            "type": "number", "default": 600, "label": "视频生成超时(秒)",
            "section": "生成", "min": 60, "max": 1800,
        },
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
        "_test_video": {
            "type": "action", "label": "🎬 测试视频生成", "section": "调试",
            "action": "test_video", "danger": False,
        },
    },
}

_SESSION_FILE = "doubao_session.json"
_CLIENT_INSTANCE = None
_CLIENT_LOCK = asyncio.Lock()


async def _get_client(ctx) -> object | None:
    """获取客户端，自动管理 session 生命周期"""
    global _CLIENT_INSTANCE
    session_path = ctx.data_dir / _SESSION_FILE
    if not session_path.exists():
        return None
    async with _CLIENT_LOCK:
        if _CLIENT_INSTANCE is None:
            try:
                from ._doubao2api import DoubaoChatClient
                _CLIENT_INSTANCE = DoubaoChatClient.from_session(str(session_path))
                _CLIENT_INSTANCE._session_path = session_path
                # 预创建 session
                await _CLIENT_INSTANCE.__aenter__()
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
            from ._doubao2api.session import load_session
            session = load_session(str(session_path))
            if session.get("cookies", {}).get("sessionid"):
                ctx.update_config({"_login_status": "✅ 已登录"})
        except Exception:
            pass

    # ── 扫码登录 ──
    @ctx.action("qr_login")
    async def _qr_login(req=None):
        from ._doubao2api.qr_login import QRLogin, QRStatus

        qr = QRLogin()
        result_holder = {}
        qr_ready = threading.Event()
        done = threading.Event()

        def on_status(status, msg):
            if status == QRStatus.FETCHING_QR and msg == "qr_ready":
                qr_ready.set()

        def on_done(result):
            result_holder["result"] = result
            done.set()

        qr.start(on_status=on_status, on_done=on_done)

        # 等待 QR 码就绪（最多 30 秒）
        await asyncio.get_running_loop().run_in_executor(None, qr_ready.wait, 30)
        if not qr.qrcode_data:
            qr.cancel()
            return {"ok": False, "message": "❌ 获取二维码失败"}

        # 保存二维码到本地
        qr_path = ctx.data_dir / "doubao_qr.png"
        qr_path.write_bytes(qr.qrcode_data)
        # 发送二维码到聊天（通过平台 Bot 通知）
        try:
            await ctx.bot.send_file(ctx.owner_id, str(qr_path))
            ctx.update_config({"_login_status": "📱 二维码已发送，请用豆包 App 扫码"})
        except Exception as e:
            ctx.update_config({"_login_status": f"📱 二维码已生成（{qr_path}），但发送失败: {e}"})

        # 后台等待扫码结果（ctx.create_task：停用自动取消）
        async def _wait_scan():
            await asyncio.get_running_loop().run_in_executor(None, done.wait, 120)
            result = result_holder.get("result")
            if result and result.status == QRStatus.CONFIRMED and result.cookies:
                session_data = {"cookies": result.cookies, "params": {}}
                session_path = ctx.data_dir / _SESSION_FILE
                session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False), encoding="utf-8")
                ctx.update_config({"_login_status": "✅ 已登录"})
                global _CLIENT_INSTANCE
                _CLIENT_INSTANCE = None
                try:
                    await ctx.bot.send(ctx.owner_id, "✅ 豆包登录成功！")
                except Exception:
                    pass
            else:
                ctx.update_config({"_login_status": "❌ 登录失败"})

        ctx.create_task(_wait_scan(), name="mydraw-qr-wait-scan")
        return {"ok": True, "message": f"📱 二维码已生成（{qr_path}），请用豆包 App 扫码"}

    @ctx.action("check_login")
    async def _check_login(req=None):
        session_path = ctx.data_dir / _SESSION_FILE
        if session_path.exists():
            try:
                from ._doubao2api.session import load_session
                session = load_session(str(session_path))
                if session.get("cookies", {}).get("sessionid"):
                    ctx.update_config({"_login_status": "✅ 已登录"})
                    return {"ok": True, "message": "✅ 已登录"}
            except Exception:
                pass
        ctx.update_config({"_login_status": "❌ 未登录"})
        return {"ok": False, "message": "❌ 未登录，请先扫码登录"}

    @ctx.action("test_video")
    async def _test_video(req=None):
        """测试视频生成功能"""
        client = await _get_client(ctx)
        if not client:
            return {"ok": False, "message": "❌ 未登录，请先扫码登录"}
        try:
            from ._doubao2api.client import DoubaoChatClient
            # 先试生成，捕获详细错误
            try:
                result = await client.generate_video(
                    prompt="一只可爱的柴犬在草地上奔跑",
                    timeout=120,
                )
            except Exception as e:
                ctx.log.error("[测试视频] 生成异常: %s", e)
                return {"ok": False, "message": f"❌ 异常: {e}\n详情见日志"}

            if result and result.videos:
                urls = [v.video_url for v in result.videos]
                return {"ok": True, "message": f"✅ 成功！{len(result.videos)} 个视频\n首条URL: {urls[0][:100]}"}

            # 没有 videos 但也没抛异常 - 检查 result 结构
            info = {
                "has_result": result is not None,
                "type": str(type(result)),
                "videos": str(getattr(result, "videos", "N/A")),
                "prompt": getattr(result, "prompt", ""),
                "error": getattr(result, "error", ""),
            }
            ctx.log.info("[测试视频] 返回为空: %s", json.dumps(info, ensure_ascii=False))
            return {"ok": False, "message": f"❌ 返回为空\n{json.dumps(info, ensure_ascii=False, indent=2)}"}
        except Exception as e:
            ctx.log.error("[测试视频] 外层异常: %s", e)
            return {"ok": False, "message": f"❌ 异常: {e}"}

    # ── 命令处理（V2: Telethon 单参 event，命令在函数内用 event.text 判断）──
    @ctx.on_message(outgoing=True)
    async def cmd_handler(event):
        text = (event.text or "").strip()
        if not text.startswith("."):
            return

        if text.startswith(".st "):
            prompt = text[4:].strip()
            if await event.get_reply_message():
                await _handle_image_reply(ctx, event, prompt)
            else:
                await _handle_image(ctx, event, prompt)
        elif text == ".st":
            if await event.get_reply_message():
                await _handle_image_reply(ctx, event, "")
            else:
                # 无回复直接 .st，提示用法
                msg = await event.reply("🎨 请回复文字或图片后使用 <code>.st</code>\n或直接 <code>.st 提示词</code> 文生图")
                try:
                    await event.delete()
                except Exception:
                    pass
                await asyncio.sleep(10)
                try:
                    await msg.delete()
                except Exception:
                    pass
        elif text.startswith(".ssp "):
            await _handle_video(ctx, event, text[5:])
        elif text.startswith(".sy "):
            await _handle_music(ctx, event, text[5:])
        elif text == ".st help":
            help_text = (
                "🎨 <b>豆包多模态 v2.0.0</b>\n\n"
                "📝 <b>生成图片</b>\n"
                "  <code>.st 一只柴犬</code> — 文生图\n"
                "  <code>.st</code> 回复文字 — 用被回复文字作提示词\n\n"
                "🎬 <b>生成视频</b>\n"
                "  <code>.ssp 一只柴犬奔跑</code> — 文生视频（⚠️ 暂不可用）\n\n"
                "🎵 <b>生成音乐</b>\n"
                "  <code>.sy 一首轻快的歌</code> — 文生音乐\n"
                "  <code>.sy 星空之歌 --lyric 星光洒满夜空</code> — 自定义歌词\n\n"
                "⚙️ 可在配置中调整默认比例/风格/情绪\n"
                "📖 <code>.stsm</code> — 查看详细使用说明\n"
                "🔗 基于豆包 AI，免费免 Key"
            )
            msg = await event.reply(help_text)
            try:
                await event.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass

        elif text == ".stsm":
            sm_text = (
                "📖 <b>豆包多模态使用说明</b>\n\n"
                "1️⃣ <b>首次使用</b>\n"
                "   打开插件配置页 → 点「扫码登录豆包」\n"
                "   用豆包 App 扫码即可\n\n"
                "2️⃣ <b>生成图片</b>\n"
                "   <code>.st 一只柴犬</code> — 文生图\n"
                "   <code>.st 一只猫 --ratio 16:9</code> — 自定义比例\n"
                "   <code>.st</code> 回复文字 — 用被回复文字文生图\n\n"
                "3️⃣ <b>生成音乐</b>\n"
                "   <code>.sy 一首轻快的歌</code>\n"
                "   <code>.sy 星空之歌 --lyric 星光洒满夜空</code>\n"
                "   <code>.sy 摇滚 --genre Rock --mood Excited</code>\n\n"
                "4️⃣ <b>生成视频</b>（⚠️ 暂不可用）\n"
                "   <code>.ssp 一只柴犬奔跑</code>\n\n"
                "5️⃣ <b>配置</b>\n"
                "   在插件配置页可调整：\n"
                "   • 默认比例（1:1/16:9/9:16）\n"
                "   • 音乐风格/情绪/歌手性别\n"
                "   • 视频超时时间\n\n"
                "🔗 基于豆包 AI，免费免 Key"
            )
            msg = await event.reply(sm_text)
            try:
                await event.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass

    ctx.log.info("豆包多模态 v2.0.0 已就绪")


async def _handle_image(ctx, event, prompt):
    if not prompt:
        await event.reply("🎨 请输入提示词，如: <code>.st 一只柴犬</code>")
        return

    client = event.client
    ratio = ctx.config.get("ratio", "1:1")
    wm = __import__("re").search(r"--ratio\s*([\d:]+)", prompt)
    if wm:
        ratio = wm.group(1)
        prompt = prompt.replace(wm.group(0), "")

    wait = await event.reply(f"🎨 正在生成图片: {prompt}\n⏳ 请稍候...")
    try:
        await event.delete()
    except Exception:
        pass

    try:
        db = await _get_client(ctx)
        if not db:
            await wait.edit("❌ 未登录豆包，请先扫码登录")
            return

        result = await db.generate_image(prompt=prompt.strip(), ratio=ratio)
        if result.images:
            img = result.images[0]
            # 尝试去除水印：去掉 URL 中的 _watermark 后缀
            img_url = img.ori_url.replace("_watermark", "")
            _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            filepath = _DOWNLOAD_DIR / f"dt_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.png"
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                # 先尝试无水印URL，失败则用原URL
                r = await sess.get(img_url)
                if r.status != 200:
                    r = await sess.get(img.ori_url)
                if r.status == 200:
                    data = await r.read()
                    # 用 OpenCV 去除水印
                    try:
                        import cv2
                        import numpy as np
                        img_arr = np.frombuffer(data, np.uint8)
                        img_cv = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                        if img_cv is not None:
                            h, w = img_cv.shape[:2]
                            mw = max(w // 4, 200)
                            mh = max(h // 12, 60)
                            mask = np.zeros((h, w), dtype=np.uint8)
                            mask[h-mh:h, w-mw:w] = 255
                            cleaned = cv2.inpaint(img_cv, mask, 5, cv2.INPAINT_TELEA)
                            _, buf = cv2.imencode(".png", cleaned)
                            data = buf.tobytes()
                    except ImportError:
                        pass
                    filepath.write_bytes(data)
                else:
                    await wait.edit("❌ 图片下载失败")
                    return
            await wait.delete()
            await client.send_file(event.chat_id, str(filepath))
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit("❌ 图片生成失败")
    except Exception as e:
        ctx.log.error("图片生成异常: %s", e)
        await wait.edit(f"❌ 生成失败: {e}")


async def _handle_image_reply(ctx, event, prompt):
    """处理回复消息的 .st 命令。

    回复文字消息 → 用被回复文字作提示词，文生图
    回复图片消息 → 无操作（豆包不支持图生图）
    """
    reply = await event.get_reply_message()
    if not reply:
        await _handle_image(ctx, event, prompt)
        return

    reply_text = (reply.text or reply.caption or "").strip()

    # 回复文字消息 → 文生图
    if reply_text and not reply.photo and not reply.document:
        final_prompt = prompt if prompt else reply_text
        await _handle_image(ctx, event, final_prompt)
        return

    # 回复图片消息 → 无操作，静默删除命令消息
    try:
        await event.delete()
    except Exception:
        pass


async def _handle_video(ctx, event, prompt):
    if not prompt:
        await event.reply("🎬 请输入提示词，如: <code>.ssp 一只柴犬奔跑</code>")
        return

    client = event.client
    ratio = ctx.config.get("ratio", "16:9")
    timeout = int(ctx.config.get("video_timeout", 600) or 600)
    # 传给 generate_video 的超时，实际等待时间
    api_timeout = max(timeout, 600)

    wait = await event.reply(f"🎬 正在生成视频: {prompt}\n⏳ 大约需要1-3分钟...")
    try:
        await event.delete()
    except Exception:
        pass

    try:
        db = await _get_client(ctx)
        if not db:
            await wait.edit("❌ 未登录豆包，请先扫码登录")
            return

        result = await db.generate_video(prompt=prompt.strip(), ratio=ratio, timeout=api_timeout)
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
            await client.send_file(event.chat_id, str(filepath), caption=f"🎬 {prompt}\n{v.duration}s")
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit("❌ 视频生成失败")
    except Exception as e:
        await wait.edit(f"❌ 生成失败: {e}")


async def _handle_music(ctx, event, cmd):
    if not cmd:
        await event.reply("🎵 请输入提示词，如: <code>.sy 一首轻快的歌</code>")
        return

    client = event.client
    prompt = cmd.strip()
    lyric = None
    genre = ctx.config.get("music_genre", "Pop")
    mood = ctx.config.get("music_mood", "Happy")
    gender = ctx.config.get("music_gender", "Female")

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

    wait = await event.reply(f"🎵 正在生成音乐: {prompt}\n⏳ 大约需要30-60秒...")
    try:
        await event.delete()
    except Exception:
        pass

    try:
        db = await _get_client(ctx)
        if not db:
            await wait.edit("❌ 未登录豆包，请先扫码登录")
            return

        kwargs = {"prompt": prompt, "genre": genre, "mood": mood, "gender": gender}
        if lyric:
            kwargs["lyric"] = lyric
            kwargs["generation_type"] = "custome_lyric"
        result = await db.generate_music(**kwargs)
        if result.tracks:
            track = result.tracks[0]
            _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            filepath = _DOWNLOAD_DIR / f"dtm_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.m4a"
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.get(track.audio_url) as r:
                    if r.status == 200:
                        filepath.write_bytes(await r.read())
            await wait.delete()
            caption = f"🎵 {track.title}\n{genre} | {mood} | {gender}\n时长: {track.duration:.0f}s"
            # Telethon: 音频用 send_file + DocumentAttributeAudio 标记为音频
            from telethon.tl.types import DocumentAttributeAudio
            await client.send_file(
                event.chat_id, str(filepath), caption=caption,
                attributes=[DocumentAttributeAudio(duration=int(track.duration), title=track.title, performer=genre, voice=False)],
            )
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit("❌ 音乐生成失败")
    except Exception as e:
        await wait.edit(f"❌ 生成失败: {e}")


async def teardown(ctx):
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE:
        try:
            await _CLIENT_INSTANCE.__aexit__(None, None, None)
        except Exception:
            pass
    _CLIENT_INSTANCE = None
    ctx.log.info("豆包多模态已卸载")