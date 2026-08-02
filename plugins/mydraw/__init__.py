# -*- coding: utf-8 -*-
# AWBotNest 插件：豆包多模态 (mydraw) v2.0.0
# 基于 doubao2api，免费文生图/视频/音乐

import asyncio
import json
import os
import time
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
_DOWNLOAD_DIR = Path("/tmp/mydraw_downloads")

__plugin__ = {
    "name": "豆包多模态",
    "id": "mydraw",
    "version": "2.2.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mydraw_v1.svg",
    "author": "凹凸曼",
    "description": "豆包 AI 多模态生成。支持 .st 文生图，.ssp 文生视频，.sy 文生音乐。免费免 Key，扫码登录豆包账号即可使用。",
    "scope": "user",
    "default_enabled": False,
    "requirements": ["aiohttp", "cloakbrowser", "playwright"],
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
    global _CLIENT_INSTANCE, _CLIENT_LOCK
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
    ctx.log.info("豆包多模态 v2.1.0 已加载")

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

        loop = asyncio.get_running_loop()
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
        await loop.run_in_executor(None, qr_ready.wait, 30)
        if not qr.qrcode_data:
            qr.cancel()
            return {"ok": False, "message": "❌ 获取二维码失败"}

        # 保存二维码到本地
        qr_path = ctx.data_dir / "doubao_qr.png"
        qr_path.write_bytes(qr.qrcode_data)
        # 发送二维码到聊天（通过平台通知）
        try:
            await ctx.bot.send_photo(ctx.owner_id, str(qr_path))
            ctx.update_config({"_login_status": "📱 二维码已发送，请用豆包 App 扫码"})
        except Exception as e:
            ctx.update_config({"_login_status": f"📱 二维码已生成（{qr_path}），但发送失败: {e}"})

        # 后台等待扫码结果
        async def _wait_scan():
            await loop.run_in_executor(None, done.wait, 120)
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

        asyncio.create_task(_wait_scan())
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
        """保存session到插件目录，供抓包用"""
        session_path = ctx.data_dir / _SESSION_FILE
        if not session_path.exists():
            return {"ok": False, "message": "❌ 未登录，请先扫码登录"}
        
        import json, os as _os, shutil
        
        # 保存 session 到插件目录
        dst = _os.path.join(_os.path.dirname(__file__), "_session.json")
        shutil.copy(str(session_path), dst)
        ctx.log.info("[抓包] session已保存到 %s", dst)
        
        # 也保存cookie到单独文件
        session = json.loads(open(str(session_path), encoding="utf-8").read())
        cookies = session.get("cookies", {})
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        cookie_path = _os.path.join(_os.path.dirname(__file__), "_cookies.txt")
        with open(cookie_path, "w", encoding="utf-8") as f:
            f.write(cookie_str)
        ctx.log.info("[抓包] cookies已保存到 %s", cookie_path)
        ctx.log.info("[抓包] cookie keys: %s", list(cookies.keys()))
        
        return {"ok": True, "message": f"✅ session已保存，请查看插件目录下的 _session.json 和 _cookies.txt\ncookie keys: {list(cookies.keys())}"}

    # ── 解析豆包对话链接，提取无水印图片 ──
    async def _parse_url(ctx, client, message, url):
        msg = await message.reply(f"🔍 正在解析豆包链接...")
        try:
            await message.delete()
        except Exception:
            pass
        try:
            from _doubao_parser import doubao_image_parse
            result = await doubao_image_parse(url)
        except Exception as e:
            await msg.edit(f"❌ 解析失败: {e}")
            return
        if not result:
            await msg.edit("❌ 未找到图片")
            return
        await msg.edit(f"⏳ 正在发送 {len(result)} 张无水印图片...")
        try:
            async with aiohttp.ClientSession() as session:
                for i, img in enumerate(result):
                    img_url = img.get("url", "")
                    if not img_url:
                        continue
                    async with session.get(img_url) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.read()
                    await client.send_photo(message.chat.id, data)
        except Exception as e:
            await msg.edit(f"❌ 发送失败: {e}")
            return
        try:
            await msg.delete()
        except Exception:
            pass

    # ── 命令处理 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        if text.startswith(".st "):
            keyword = text[4:].strip()
            if keyword.startswith("parse "):
                await _parse_url(ctx, client, message, keyword[6:].strip())
            else:
                await _handle_image(ctx, client, message, keyword)
        elif text.startswith(".ssp "):
            await _handle_video(ctx, client, message, text[5:])
        elif text.startswith(".sy "):
            await _handle_music(ctx, client, message, text[5:])
        elif text == ".st help":
            help_text = (
                "🎨 <b>豆包多模态 v2.2.0</b>\n\n"
                "📝 <b>生成图片</b>\n"
                "  <code>.st 一只柴犬</code> — 文生图\n\n"
                "🎬 <b>生成视频</b>\n"
                "  <code>.ssp 一只柴犬奔跑</code> — 文生视频（⚠️ 暂不可用）\n\n"
                "🎵 <b>生成音乐</b>\n"
                "  <code>.sy 一首轻快的歌</code> — 文生音乐\n"
                "  <code>.sy 星空之歌 --lyric 星光洒满夜空</code> — 自定义歌词\n\n"
                "⚙️ 可在配置中调整默认比例/风格/情绪\n"
                "📖 <code>.stsm</code> — 查看详细使用说明\n"
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

        elif text == ".stsm":
            sm_text = (
                "📖 <b>豆包多模态使用说明</b>\n\n"
                "1️⃣ <b>首次使用</b>\n"
                "   打开插件配置页 → 点「扫码登录豆包」\n"
                "   用豆包 App 扫码即可\n\n"
                "2️⃣ <b>生成图片</b>\n"
                "   <code>.st 一只柴犬</code>\n"
                "   <code>.st 一只猫 --ratio 16:9</code>\n\n"
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
            msg = await message.reply(sm_text)
            try:
                await message.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass

    ctx.log.info("豆包多模态 v2.1.0 已就绪")


async def _handle_image(ctx, client, message, prompt):
    if not prompt:
        await message.reply("🎨 请输入提示词，如: <code>.st 一只柴犬</code>")
        return

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
        db = await _get_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
            return

        result = await db.generate_image(prompt=prompt.strip(), ratio=ratio)
        ctx.log.info("图片生成结果: %s images", len(result.images) if result else 0)
        if result.images:
            img = result.images[0]
            # 先用 clean_url，如果没有则尝试用 doubao_parser 从对话页提取
            img_url = img.clean_url or ""
            if not img_url:
                ctx.log.info("尝试用 doubao_parser 提取无水印 URL...")
                try:
                    from _doubao_parser import doubao_image_parse
                    thread_id = getattr(db, '_last_thread_id', '')
                    if thread_id:
                        page_url = f"https://www.doubao.com/thread/{thread_id}"
                        # 复用客户端的 cookies
                        cookies = getattr(db, 'cookies', {})
                        parsed = await doubao_image_parse(page_url, cookies=cookies)
                        if parsed and parsed[0].get("url"):
                            img_url = parsed[0]["url"]
                            ctx.log.info("doubao_parser 提取成功")
                except Exception as e:
                    ctx.log.warning("doubao_parser 提取失败: %s", e)
            if not img_url:
                # 降级
                img_url = img.raw_url or img.ori_url
            _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            filepath = _DOWNLOAD_DIR / f"dt_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.png"
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                r = await sess.get(img_url)
                if r.status != 200:
                    r = await sess.get(img.ori_url)
                if r.status == 200:
                    data = await r.read()
                    filepath.write_bytes(data)
                else:
                    await wait.edit_text("❌ 图片下载失败")
                    return
            await wait.delete()
            with open(filepath, "rb") as f:
                await client.send_photo(message.chat.id, f)
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit_text("❌ 图片生成失败")
    except Exception as e:
        import traceback
        ctx.log.error("图片生成异常: %s", traceback.format_exc())
        await wait.edit_text(f"❌ 生成失败: {e}")


async def _handle_video(ctx, client, message, prompt):
    if not prompt:
        await message.reply("🎬 请输入提示词，如: <code>.ssp 一只柴犬奔跑</code>")
        return

    ratio = ctx.config.get("ratio", "16:9")
    timeout = int(ctx.config.get("video_timeout", 600) or 600)
    # 传给 generate_video 的超时，实际等待时间
    api_timeout = max(timeout, 600)

    wait = await message.reply(f"🎬 正在生成视频: {prompt}\n⏳ 大约需要1-3分钟...")
    try:
        await message.delete()
    except Exception:
        pass

    try:
        db = await _get_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
            return

        # 用浏览器方案生成视频（打字输入方式）
        try:
            import cloakbrowser
            from playwright.async_api import async_playwright as _async_pw
            import uuid
            
            session_path = ctx.data_dir / _SESSION_FILE
            if not session_path.exists():
                raise Exception("session文件不存在")
            
            session = json.loads(open(str(session_path), encoding="utf-8").read())
            cookies = session.get("cookies", {})
            
            ctx.log.info("[视频] 启动浏览器...")
            async with _async_pw() as pw:
                browser = await cloakbrowser.launch_async(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    locale="zh-CN",
                )
                bpage = await context.new_page()
                
                # 设置 cookies
                for name, value in cookies.items():
                    await context.add_cookies([{
                        "name": name, "value": str(value),
                        "domain": ".doubao.com", "path": "/",
                    }])
                
                # 捕获 SSE 响应
                sse_response = []
                async def on_response(response):
                    if "/chat/completion" in response.url:
                        try:
                            body = await response.text()
                            if body and len(body) > 100:
                                sse_response.append(body)
                        except:
                            pass
                
                bpage.on("response", on_response)
                
                # 打开豆包，让 fetch hook 注入
                await bpage.goto("https://www.doubao.com/chat", wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(5)
                
                # 等待 fetch hook 生效
                for i in range(15):
                    hooked = await bpage.evaluate("""() => {
                        try { const s = window.fetch.toString(); return !s.includes('native code'); }
                        catch(e) { return false; }
                    }""")
                    if hooked:
                        ctx.log.info("[视频] fetch hook 第%d秒生效", i+1)
                        break
                    await asyncio.sleep(1)
                
                # 找输入框，打字输入提示词
                input_selector = 'textarea[placeholder*="发消息"], textarea.semi-input-textarea'
                await bpage.wait_for_selector(input_selector, timeout=15000)
                
                video_prompt = f"生成影片：{prompt.strip()}，{ratio or '16:9'}，5秒"
                await bpage.click(input_selector)
                await bpage.type(input_selector, video_prompt, delay=30)
                await asyncio.sleep(1)
                await bpage.keyboard.press("Enter")
                ctx.log.info("[视频] 已发送提示词")
                
                # 等待响应
                await asyncio.sleep(10)
                
                if not sse_response:
                    raise Exception("未收到API响应")
                
                raw = sse_response[0]
                
                # 解析 SSE 获取 conversation_id
                conv_id = ""
                for block in raw.split("\n\n"):
                    block = block.strip()
                    if not block:
                        continue
                    for line in block.split("\n"):
                        if line.startswith("data: "):
                            try:
                                import json as _json
                                data = _json.loads(line[6:])
                                ack = data.get("ack_client_meta", {})
                                if isinstance(ack, dict) and ack.get("conversation_id"):
                                    conv_id = ack["conversation_id"]
                            except:
                                pass
                
                if not conv_id:
                    raise Exception("未获取到 conversation_id")
                
                ctx.log.info("[视频] conversation_id: %s", conv_id)
                
                # 检查是否需要确认（检查原始SSE文本，不依赖JSON解析）
                need_confirm = "确认" in raw or "确认后" in raw
                ctx.log.info("[视频] 是否需要确认: %s", need_confirm)
                
                # 如果需要确认，发送确认
                if need_confirm:
                    ctx.log.info("[视频] AI要求确认，发送确认...")
                    await bpage.click(input_selector)
                    await bpage.type(input_selector, "确认生成", delay=30)
                    await asyncio.sleep(1)
                    await bpage.keyboard.press("Enter")
                    await asyncio.sleep(10)
                    # 如果有多条响应，取最新的
                    if len(sse_response) > 1:
                        raw = sse_response[-1]
                    ctx.log.info("[视频] 已发送确认")
                
                # 构建轮询 payload
                now_ms = int(time.time() * 1000)
                poll_payload = {
                    "client_meta": {
                        "local_conversation_id": f"local_{now_ms}",
                        "conversation_id": conv_id,
                        "bot_id": "7338286299411103781",
                        "last_section_id": "",
                        "last_message_index": None,
                    },
                    "messages": [{
                        "local_message_id": str(uuid.uuid4()),
                        "content_block": [{
                            "block_type": 10000,
                            "content": {
                                "text_block": {
                                    "text": "视频完成了吗？",
                                    "icon_url": "", "icon_url_dark": "", "summary": "",
                                },
                                "pc_event_block": "",
                            },
                            "block_id": str(uuid.uuid4()),
                            "parent_id": "", "meta_info": [], "append_fields": [],
                        }],
                        "message_status": 0,
                    }],
                    "option": {
                        "send_message_scene": "", "create_time_ms": now_ms,
                        "collect_id": "", "is_audio": False,
                        "answer_with_suggest": False, "agent_mode": 2,
                        "tts_switch": False, "need_deep_think": 0,
                        "click_clear_context": False, "from_suggest": False,
                        "is_regen": False, "is_replace": False,
                        "is_from_click_option": False, "is_from_click_softlink": False,
                        "disable_sse_cache": False, "select_text_action": "",
                        "is_select_text": False, "resend_for_regen": False,
                        "scene_type": 0, "unique_key": str(uuid.uuid4()),
                        "start_seq": 0, "need_create_conversation": False,
                        "regen_query_id": [], "edit_query_id": [],
                        "regen_instruction": "", "no_replace_for_regen": False,
                        "message_from": 0, "shared_app_name": "", "shared_app_id": "",
                        "sse_recv_event_options": {"support_chunk_delta": True},
                        "is_ai_playground": False, "is_old_user": True,
                        "recovery_option": {
                            "is_recovery": False,
                            "req_create_time_sec": int(time.time()),
                            "append_sse_event_scene": 0,
                        },
                        "message_storage_type": 0,
                    },
                    "user_context": [],
                    "ext": {
                        "use_deep_think": "0", "sub_conv_firstmet_type": "1",
                        "collection_id": "",
                        "conversation_init_option": '{"need_ack_conversation":true}',
                        "commerce_credit_config_enable": "0",
                    },
                }
                
                # 轮询视频结果（通过检查页面元素 + 监听 SSE 响应）
                ctx.log.info("[视频] 等待视频生成...")
                await wait.edit_text("🎬 视频生成中，请等待（约1-5分钟）...")
                
                video_url = None
                start = time.time()
                while time.time() - start < 600:
                    await asyncio.sleep(3)
                    
                    # 1. 检查页面中的视频元素
                    try:
                        page_video = await bpage.evaluate("""() => {
                            // 查找页面中的视频 URL
                            const videos = document.querySelectorAll('video');
                            for (const v of videos) {
                                if (v.src && v.src.includes('http')) return v.src;
                            }
                            // 查找 creation 元素中的视频 URL
                            const els = document.querySelectorAll('[class*="creation"],[class*="video"]');
                            for (const el of els) {
                                const text = el.textContent || '';
                                const m = text.match(/https?:\\/\\/[^\\s"\']+\\.(mp4|webm)/i);
                                if (m) return m[0];
                            }
                            // 查找图片元素中的视频封面
                            const imgs = document.querySelectorAll('img[src*="video"]');
                            for (const img of imgs) {
                                if (img.src) return img.src.replace('cover', 'video');
                            }
                            return null;
                        }""")
                        if page_video and page_video.startswith("http"):
                            video_url = page_video
                            break
                    except:
                        pass
                    
                    # 2. 检查是否有新的 SSE 响应
                    for resp_text in sse_response:
                        try:
                            from ._doubao2api.browser_client import BrowserClient
                            bc = BrowserClient(headless=True)
                            result = bc._parse_video_result(resp_text, prompt.strip())
                            if result.get("videos"):
                                video_url = result["videos"][0].get("video_url", "")
                                break
                        except:
                            pass
                    if video_url:
                        break
                    
                    # 每30秒更新一次状态
                    elapsed = int(time.time() - start)
                    if elapsed % 30 < 3:
                        await wait.edit_text(f"🎬 视频生成中（已等待{elapsed}秒）...")
                        ctx.log.info("[视频] 等待中... %d秒", elapsed)
                
                await browser.close()
            
            if video_url:
                _DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
                filepath = _DOWNLOAD_DIR / f"dtv_{datetime.now(TZ).strftime('%Y%m%d_%H%M%S')}.mp4"
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(video_url) as r:
                        if r.status == 200:
                            with open(filepath, "wb") as f:
                                f.write(await r.read())
                            await wait.delete()
                            await client.send_video(message.chat.id, filepath, caption=f"🎬 {prompt[:50]}")
                            return
                await wait.edit_text(f"✅ 视频已生成，但下载失败")
            else:
                await wait.edit_text("❌ 视频生成超时（10分钟）")
            return
                
        except Exception as e:
            ctx.log.error("[视频] 浏览器方案失败: %s", e)
            import traceback
            ctx.log.error("[视频] 详细错误: %s", traceback.format_exc())
            await wait.edit_text(f"❌ 视频生成失败: {e}")
            return
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
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit_text("❌ 视频生成失败")
    except Exception as e:
        await wait.edit_text(f"❌ 生成失败: {e}")


async def _handle_music(ctx, client, message, cmd):
    if not cmd:
        await message.reply("🎵 请输入提示词，如: <code>.sy 一首轻快的歌</code>")
        return

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

    wait = await message.reply(f"🎵 正在生成音乐: {prompt}\n⏳ 大约需要30-60秒...")
    try:
        await message.delete()
    except Exception:
        pass

    try:
        db = await _get_client(ctx)
        if not db:
            await wait.edit_text("❌ 未登录豆包，请先扫码登录")
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
            with open(filepath, "rb") as f:
                await client.send_audio(message.chat.id, f, caption=caption)
            filepath.unlink(missing_ok=True)
        else:
            await wait.edit_text("❌ 音乐生成失败")
    except Exception as e:
        await wait.edit_text(f"❌ 生成失败: {e}")


async def teardown(ctx):
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE:
        try:
            await _CLIENT_INSTANCE.__aexit__(None, None, None)
        except Exception:
            pass
    _CLIENT_INSTANCE = None
    ctx.log.info("豆包多模态已卸载")