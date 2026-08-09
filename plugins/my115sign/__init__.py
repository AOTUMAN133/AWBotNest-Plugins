# -*- coding: utf-8 -*-
# AWBotNest 插件：115签到 (my115sign)
# 支持扫码登录获取 Cookie

import asyncio
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone, timedelta

import httpx

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "115签到",
    "id": "my115sign",
    "version": "1.2.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/my115sign_v1.svg",
    "author": "凹凸曼",
    "description": "115网盘每日自动签到，支持多账号、WxPusher推送、扫码登录。用法: .115sign 签到 / .115login 扫码登录",
    "scope": "user",
    "default_enabled": True,
    "requirements": ["httpx"],
    "config_schema": {
        "cookies": {
            "type": "textarea",
            "default": "",
            "label": "115 Cookie（每行一个账号）",
            "section": "账号",
            "help": "多个账号用换行分隔，每行一个 Cookie。Cookie 需包含 UID、CID、SEID 等完整字段。",
        },
        "scan_device": {
            "type": "select",
            "default": "alipaymini",
            "label": "扫码登录设备类型",
            "section": "扫码登录",
            "options": {
                "alipaymini": "115生活(支付宝小程序)",
                "web": "网页版",
                "android": "115生活(Android端)",
                "115android": "115(Android端)",
                "ios": "115生活(iOS端)",
                "115ipad": "115(iPad端)",
                "tv": "115网盘(Android电视端)",
                "wechatmini": "115生活(微信小程序)",
                "qandroid": "115管理(Android端)",
                "115ios": "115(iOS端)",
                "harmony": "115(Harmony端)",
                "linux": "Linux",
                "mac": "Mac",
                "windows": "Windows",
            },
            "help": "选择扫码登录时模拟的设备类型。推荐使用「115生活(支付宝小程序)」，扫码后 Cookie 不易失效。",
        },
        "scan_timeout": {
            "type": "number",
            "default": 120,
            "label": "扫码等待超时（秒）",
            "min": 30,
            "max": 300,
            "section": "扫码登录",
            "help": "生成二维码后等待用户扫码的最长时间。",
        },
        "wxpusher_spt": {
            "type": "text",
            "default": "",
            "label": "WxPusher SPT（推送令牌）",
            "section": "推送",
            "help": "留空则不推送。可在 WxPusher 官网申请，用于接收签到结果通知。",
        },
        "notify_on_sign": {
            "type": "boolean",
            "default": False,
            "label": "签到结果推送通知",
            "section": "推送",
            "help": "定时签到和手动签到后，将结果推送到 WxPusher（需配置上方 SPT）。",
        },
        "checkin_hour": {
            "type": "slider",
            "default": 9,
            "label": "签到小时",
            "min": 0,
            "max": 23,
            "step": 1,
            "section": "定时",
        },
        "checkin_minute": {
            "type": "slider",
            "default": 0,
            "label": "签到分钟",
            "min": 0,
            "max": 59,
            "step": 1,
            "section": "定时",
        },
        "sign_now": {
            "type": "action",
            "label": "▶ 立即签到",
            "section": "操作",
            "action": "sign_now",
            "danger": False,
        },
        "scan_now": {
            "type": "action",
            "label": "📱 扫码登录",
            "section": "操作",
            "action": "scan_now",
            "danger": False,
            "help": "点击后生成二维码，用 115 APP 扫码获取 Cookie。",
        },
    },
}

SIGN_URL = "https://proapi.115.com/android/2.0/user/points_sign"
APP_UA = "Mozilla/5.0 115disk/36.2.28"
ACCOUNT_INTERVAL = 2

_run_lock = None

# ── 扫码登录相关 ──

QR_STATUS_LABELS = {
    0: "等待扫码",
    1: "已扫码",
    2: "登录成功",
    -1: "已失效",
    -2: "已取消",
}

SCANNED_COOKIES_KV_KEY = "my115sign_scanned_cookies"


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def parse_cookie_map(cookie: str) -> dict:
    result = {}
    for part in cookie.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def extract_user_id(cookie: str):
    cookies = parse_cookie_map(cookie)
    uid = cookies.get("UID") or cookies.get("uid")
    if not uid:
        raise ValueError("Cookie 中缺少 UID，无法生成签到 token")
    user_id = uid.split("_", 1)[0]
    if not str(user_id).isdigit():
        raise ValueError(f"无法从 UID 解析 user_id: {uid}")
    return int(user_id)


def build_sign_payload(user_id: int) -> dict:
    token_time = int(time.time())
    raw = f"{user_id}-Points_Sign@#115-{token_time}".encode("utf-8")
    token = hashlib.sha1(raw).hexdigest()
    return {"token": token, "token_time": token_time}


def pick_message(result: dict) -> str:
    for key in ("message", "error", "msg", "err_msg", "errno"):
        value = result.get(key)
        if value not in (None, ""):
            return str(value)
    data = result.get("data")
    if isinstance(data, dict):
        for key in ("message", "msg", "tip", "is_signed"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value)
    return "未知"


# ── Cookie 加载（合并配置 + 扫码获取的 Cookie）──

def _load_cookies(ctx) -> list:
    # 从配置读取
    raw = ctx.config.get("cookies", "") or ""
    if isinstance(raw, str):
        parts = raw.replace("\r", "\n").split("\n")
    else:
        parts = [str(raw)]
    cookies = [c.strip() for c in parts if c.strip()]
    # 兼容 & 分隔
    if len(cookies) == 1 and "&" in cookies[0]:
        cookies = [c.strip() for c in cookies[0].split("&") if c.strip()]

    # 合并扫码获取的 Cookie
    scanned = _load_scanned_cookies(ctx)
    for sc in scanned:
        if sc not in cookies:
            cookies.append(sc)

    return cookies


def _load_scanned_cookies(ctx) -> list:
    try:
        raw = ctx.kv.get(SCANNED_COOKIES_KV_KEY, "[]") or "[]"
        if isinstance(raw, str):
            return json.loads(raw)
        return list(raw) if isinstance(raw, list) else []
    except Exception:
        return []


def _save_scanned_cookies(ctx, cookies: list):
    ctx.kv.set(SCANNED_COOKIES_KV_KEY, json.dumps(cookies, ensure_ascii=False))


# ── 签到逻辑 ──


async def _do_sign(ctx, cookie: str) -> str:
    try:
        user_id = extract_user_id(cookie)
        payload = build_sign_payload(user_id)
    except Exception as e:
        msg = f"❌ 参数准备失败: {e}"
        ctx.log.info("[115签到] %s", msg)
        return msg

    headers = {
        "User-Agent": APP_UA,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
        "Cookie": cookie,
        "Referer": "https://proapi.115.com/",
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(SIGN_URL, headers=headers, data=payload)
        try:
            result = response.json()
        except Exception:
            ctx.log.info("[115签到] 解析 JSON 失败: %s", response.text[:200] or ("HTTP %s" % response.status_code))
            return f"❌ user_id={user_id} 解析 JSON 失败"

        ctx.log.info("[115签到] 返回: %s", json.dumps(result, ensure_ascii=False)[:300])

        state = result.get("state")
        code = result.get("code")
        message = pick_message(result)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}

        if state in (True, 1) or code in (0, 200):
            continuous = (data.get("continuous_day") or data.get("continuous")
                          or data.get("sign_count") or data.get("days"))
            points = (data.get("points_num") or data.get("points")
                      or data.get("integral") or data.get("reward"))
            extra = []
            if continuous not in (None, ""):
                extra.append(f"连续签到={continuous}")
            if points not in (None, ""):
                extra.append(f"奖励={points}")
            suffix = f" ({', '.join(extra)})" if extra else ""
            msg = f"✅ user_id={user_id} 签到成功{suffix}"
            ctx.log.info("[115签到] %s", msg)
            return msg

        if any(x in message for x in ("已签到", "已经签到", "重复签到", "signed")):
            msg = f"⚠️ user_id={user_id} 今日已签到 ({message})"
            ctx.log.info("[115签到] %s", msg)
            return msg

        msg = f"⚠️ user_id={user_id} 签到失败 ({message})"
        ctx.log.info("[115签到] %s", msg)
        return msg

    except Exception as e:
        err_msg = str(e) or f"{type(e).__name__}"
        msg = f"❌ user_id={user_id} 网络请求异常: {err_msg}"
        ctx.log.info("[115签到] %s", msg)
        return msg


def _send_wxpusher_spt(spt_raw: str, title: str, content: str) -> bool:
    if not spt_raw:
        return False
    spt_list = [x.strip() for x in re.split(r"[\n,]+", spt_raw) if x.strip()]
    if not spt_list:
        return False

    ok_any = False
    body = f"{title}\n{content}".strip()
    for spt in spt_list:
        try:
            payload = {
                "content": body,
                "summary": (title or "通知")[:100],
                "contentType": 1,
                "spt": spt,
            }
            resp = httpx.post("https://wxpusher.zjiecode.com/api/send/message/simple-push",
                              json=payload, timeout=15)
            data = {}
            try:
                data = resp.json()
            except Exception:
                pass
            code = data.get("code")
            success = data.get("success")
            if resp.status_code == 200 and (success is True or code in (0, 1000)):
                ok_any = True
                continue
            # 兜底 GET 方式
            from urllib.parse import quote
            get_url = ("https://wxpusher.zjiecode.com/api/send/message/"
                       f"{quote(spt, safe='')}/{quote(body[:900], safe='')}")
            resp2 = httpx.get(get_url, timeout=15)
            text2 = resp2.text or ""
            low = text2.lower()
            if resp2.status_code == 200 and ("成功" in text2 or '"code":1000' in text2
                                             or '"code": 1000' in text2
                                             or '"success":true' in low
                                             or '"success": true' in low):
                ok_any = True
        except Exception:
            continue
    return ok_any


async def _notify(ctx, title: str, content: str):
    spt = (ctx.config.get("wxpusher_spt") or "").strip()
    if not spt:
        return False
    try:
        ok = await asyncio.get_event_loop().run_in_executor(
            None, _send_wxpusher_spt, spt, title, content)
        return ok
    except Exception:
        return False


async def _do_sign_all(ctx, source="手动"):
    global _run_lock
    if _run_lock is None:
        _run_lock = asyncio.Lock()
    if _run_lock.locked():
        ctx.log.info("[115签到] 已有签到任务在运行，跳过本次")
        return {"ok": False, "message": "已有签到任务在运行，请稍候"}

    async with _run_lock:
        cookies = _load_cookies(ctx)
        if not cookies:
            msg = "未配置115 Cookie，请使用 .115login 扫码登录或手动配置 Cookie"
            ctx.log.info("[115签到] %s", msg)
            return {"ok": False, "message": msg}

        results = []
        for index, cookie in enumerate(cookies, start=1):
            line = await _do_sign(ctx, cookie)
            results.append(f"[账号 {index}] {line}")
            if index < len(cookies):
                await asyncio.sleep(ACCOUNT_INTERVAL)

        ok = sum(1 for r in results if "✅" in r)
        signed = sum(1 for r in results if "已签到" in r)
        fail = len(results) - ok - signed
        title = f"115签到({source})：成功{ok}/已签{signed}/失败{fail}"
        content = "\n".join(results)

        notify_enabled = ctx.config.get("notify_on_sign", False)
        notified = False
        if notify_enabled:
            notified = await _notify(ctx, title, content)

        # 平台内通知（TG/飞书）
        lines = []
        if ok: lines.append(f"✅ 成功 {ok} 个")
        if signed: lines.append(f"⚠️ 已签到 {signed} 个")
        if fail: lines.append(f"❌ 失败 {fail} 个")
        level = "error" if ok == 0 and fail > 0 else ("warning" if fail > 0 else "success")
        await ctx.notify(f"📋 {title}\n" + "\n".join(results), level=level, category="115签到")

        return {"ok": True, "message": title, "results": results, "wxpusher": notified}


# ── 扫码登录 API ──

async def _check_api_error(resp, name: str, desc: str):
    status = resp.status_code
    if status == 405:
        raise RuntimeError(f"检测到 405 错误，一般是因为被服务器风控，请等待30分钟后再尝试")
    if 400 <= status < 500:
        raise RuntimeError(f"检测到 {status} 错误，请检查请求参数是否正确")
    if 500 <= status < 600:
        raise RuntimeError(f"检测到 {status} 错误，服务器内部错误，请稍后再试")


async def _get_qrcode_token(client, device: str) -> dict:
    url = f"https://qrcodeapi.115.com/api/1.0/{device}/1.0/token/"
    resp = await client.get(url)
    await _check_api_error(resp, "getQrcodeToken", "获取二维码登录token失败")
    return resp.json()


async def _get_qrcode_image(client, device: str, uid: str) -> bytes:
    url = f"https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid={uid}"
    resp = await client.get(url)
    await _check_api_error(resp, "getQrcode", "获取二维码图片失败")
    return resp.content


async def _poll_qrcode_status(client, uid: str, time_str: str, sign: str) -> dict:
    params = {"uid": uid, "time": time_str, "sign": sign}
    url = "https://qrcodeapi.115.com/get/status/"
    resp = await client.get(url, params=params)
    await _check_api_error(resp, "getQrcodeStatus", "获取扫码状态失败")
    return resp.json()


async def _post_qrcode_login(client, uid: str, device: str) -> dict:
    url = f"https://passportapi.115.com/app/1.0/{device}/1.0/login/qrcode/"
    data = {"app": device, "account": uid}
    resp = await client.post(url, data=data)
    await _check_api_error(resp, "postQrcodeResult", "获取二维码登录结果失败")
    return resp.json()


def _cookie_data_to_str(cookie_data: dict) -> str:
    parts = [
        f"UID={cookie_data.get('UID', '')}",
        f"CID={cookie_data.get('CID', '')}",
        f"SEID={cookie_data.get('SEID', '')}",
    ]
    kid = cookie_data.get("KID")
    if kid:
        parts.append(f"KID={kid}")
    return "; ".join(parts)


_DEVICE_LABELS = {
    "web": "网页版",
    "android": "115生活(Android端)",
    "115android": "115(Android端)",
    "ios": "115生活(iOS端)",
    "115ipad": "115(iPad端)",
    "tv": "115网盘(Android电视端)",
    "alipaymini": "115生活(支付宝小程序)",
    "wechatmini": "115生活(微信小程序)",
    "qandroid": "115管理(Android端)",
    "115ios": "115(iOS端)",
    "harmony": "115(Harmony端)",
    "linux": "Linux",
    "mac": "Mac",
    "windows": "Windows",
}


async def _do_qrcode_login(ctx, client, message, device: str = None):
    """执行扫码登录流程"""
    if device is None:
        device = str(ctx.config.get("scan_device", "alipaymini") or "alipaymini")
    timeout = int(ctx.config.get("scan_timeout", 120) or 120)
    device_label = _DEVICE_LABELS.get(device, device)

    await message.reply(f"📱 正在获取 115 扫码登录二维码...\n设备类型: {device_label}")

    try:
        # 使用同一个 client 保持 cookie（acw_tc 等反爬校验）
        async with httpx.AsyncClient(timeout=20, trust_env=True) as http:
            # 1. 获取 token
            token_resp = await _get_qrcode_token(http, device)
            token_data = token_resp.get("data", {})
            uid = token_data.get("uid")
            if not uid:
                raise RuntimeError(f"获取 token 失败: {token_resp}")

            ctx.log.info("[115签到] 扫码登录 token 获取成功, uid=%s", uid)

            # 2. 获取二维码图片
            qr_bytes = await _get_qrcode_image(http, device, uid)

            # 3. 保存到临时文件并发送
            tmp_dir = tempfile.mkdtemp(prefix="115qrcode_")
            qr_path = os.path.join(tmp_dir, f"115_qrcode_{uid}.png")
            with open(qr_path, "wb") as f:
                f.write(qr_bytes)

            # 尝试发送图片
            try:
                await client.send_photo(message.chat.id, qr_path)
            except Exception:
                try:
                    await client.send_document(message.chat.id, qr_path)
                except Exception:
                    await message.reply("⚠️ 无法发送二维码图片，请手动访问以下链接获取二维码：")
                    await message.reply(f"https://qrcodeapi.115.com/api/1.0/web/1.0/qrcode?uid={uid}")

            # 4. 轮询扫码状态
            time_str = str(token_data.get("time", ""))
            sign = token_data.get("sign", "")
            status_msg = await message.reply(
                f"⏳ 等待扫码中...（设备: {device_label}）\n"
                f"请用 115 APP 扫描上方二维码\n"
                f"超时时间: {timeout}秒"
            )

            poll_interval = 2
            elapsed = 0
            last_status = None

            while elapsed < timeout:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    poll_resp = await _poll_qrcode_status(http, uid, time_str, sign)
                    status = poll_resp.get("data", {}).get("status")
                except Exception as e:
                    ctx.log.warning("[115签到] 轮询状态异常: %s", e)
                    continue

                status_label = QR_STATUS_LABELS.get(status, f"未知({status})")

                if status != last_status:
                    try:
                        await status_msg.edit(
                            f"📱 扫码登录（{device_label}）\n"
                            f"状态: {status_label}\n"
                            f"已等待: {elapsed}秒"
                        )
                    except Exception:
                        pass
                    last_status = status

                if status == 2:
                    # 登录成功，获取 Cookie
                    try:
                        login_resp = await _post_qrcode_login(http, uid, device)
                        login_data = login_resp.get("data", {})
                        cookie_data = login_data.get("cookie", {})

                        if not cookie_data:
                            raise RuntimeError(f"获取 Cookie 失败: {login_resp}")

                        cookie_str = _cookie_data_to_str(cookie_data)

                        # 保存到 kv
                        scanned = _load_scanned_cookies(ctx)
                        # 去重：如果已有相同 UID 的 Cookie，替换
                        new_uid = parse_cookie_map(cookie_str).get("UID", "")
                        filtered = []
                        for c in scanned:
                            if parse_cookie_map(c).get("UID", "") != new_uid:
                                filtered.append(c)
                        filtered.append(cookie_str)
                        _save_scanned_cookies(ctx, filtered)

                        # 提取 user_id 显示
                        try:
                            uid_num = extract_user_id(cookie_str)
                            uid_display = f"user_id={uid_num}"
                        except Exception:
                            uid_display = f"UID={new_uid}"

                        success_msg = (
                            f"✅ 扫码登录成功！\n"
                            f"设备: {device_label}\n"
                            f"{uid_display}\n\n"
                            f"Cookie 已保存（共 {len(filtered)} 个扫码账号）\n"
                            f"可使用 .115sign 签到测试"
                        )
                        await message.reply(success_msg)
                        ctx.log.info("[115签到] 扫码登录成功: %s", uid_display)

                        # 清理临时文件
                        try:
                            os.remove(qr_path)
                            os.rmdir(tmp_dir)
                        except Exception:
                            pass

                        return cookie_str

                    except Exception as e:
                        err_text = str(e) or f"{type(e).__name__}"
                        await message.reply(
                            f"❌ 获取 Cookie 失败: {err_text}\n\n"
                            f"💡 扫码已完成，但无法自动获取 Cookie。\n"
                            f"请打开浏览器访问 115.com，按 F12 打开开发者工具\n"
                            f"在 Application -> Cookies 中复制 UID/CID/SEID 值\n"
                            f"然后手动添加到插件配置中。"
                        )
                        ctx.log.error("[115签到] 扫码登录获取 Cookie 失败: %s", err_text)
                        return None

                elif status in (-1, -2):
                    reason = "二维码已失效" if status == -1 else "用户已取消"
                    await message.reply(f"❌ {reason}，请重新发送 .115login")
                    return None

            # 超时
            await message.reply(f"⏰ 扫码超时（{timeout}秒），请重新发送 .115login")
            return None

    except Exception as e:
        err_text = str(e) or f"{type(e).__name__}"
        ctx.log.error("[115签到] 扫码登录异常: %s", err_text)
        await message.reply(f"❌ 扫码登录失败: {err_text}")
        return None


# ── 设置 ──


async def setup(ctx):
    # 统一命令处理（避免同组多 handler 的 propagation 阻断）
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=0)
    async def _cmd_handler(client, message):
        text = (message.text or "").strip()
        low = text.lower()

        # ── 手动签到 ──
        if text in (".115sign", ".115", ".qd"):
            ctx.log.info("[115签到] 收到手动签到命令")
            await message.reply("🔄 正在签到，请稍候...")
            result = await _do_sign_all(ctx, "手动")
            summary = result.get("message", "签到完成")
            await message.reply(f"📋 {summary}")
            return

        # ── 扫码登录选设备（纯数字回复）──
        _PENDING_KEY = "my115sign_pending_select"
        if text.isdigit():
            pending = ctx.kv.get(_PENDING_KEY, 0) or 0
            if pending and time.time() - pending < 120:
                ctx.kv.set(_PENDING_KEY, 0)
                valid_devices = list(_DEVICE_LABELS.keys())
                idx = int(text) - 1
                if 0 <= idx < len(valid_devices):
                    device = valid_devices[idx]
                    await _do_qrcode_login(ctx, client, message, device)
                else:
                    await message.reply(f"❌ 序号超出范围（1-{len(valid_devices)}）")
                return

        # ── 扫码登录 ──
        if low == ".115login":
            # 不带参数：列出设备让用户选
            devices = list(_DEVICE_LABELS.items())
            lines = ["📱 请选择扫码登录设备：\n"]
            for i, (dev, label) in enumerate(devices, 1):
                lines.append(f"  {i}. `{dev}` -> {label}")
            lines.append("\n💡 直接回复序号即可，或发送 `.115login 设备名`")
            lines.append(f"  ⭐ 推荐: 7 `alipaymini`（Cookie 不易失效）")
            ctx.kv.set(_PENDING_KEY, time.time())
            await message.reply("\n".join(lines))
            return
        m = re.match(r"^\.115login\s+(\S+)", low)
        if m:
            choice = m.group(1)
            valid_devices = list(_DEVICE_LABELS.keys())
            # 支持序号选择
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(valid_devices):
                    device = valid_devices[idx]
                else:
                    await message.reply(f"❌ 序号超出范围（1-{len(valid_devices)}）")
                    return
            elif choice in valid_devices:
                device = choice
            else:
                await message.reply(
                    f"❌ 不支持的设备类型: {choice}\n"
                    f"可用设备: {', '.join(valid_devices)}\n"
                    f"或使用 .115login 查看列表"
                )
                return
            ctx.kv.set(_PENDING_KEY, 0)
            await _do_qrcode_login(ctx, client, message, device)
            return

        # ── 设备列表 ──
        if text == ".115devices":
            lines = ["📱 可用扫码设备列表：\n"]
            for dev, label in _DEVICE_LABELS.items():
                lines.append(f"  `{dev}` -> {label}")
            lines.append("\n💡 使用方法: `.115login <设备名>`")
            lines.append("  例: `.115login alipaymini`")
            lines.append("  留空则使用默认设备")
            await message.reply("\n".join(lines))
            return

        # ── 查看 Cookie 列表 ──
        if text == ".115cookies":
            scanned = _load_scanned_cookies(ctx)
            config_cookies = _load_cookies(ctx)
            config_count = len(config_cookies) - len(scanned)
            lines = ["🍪 Cookie 列表：\n"]
            if config_count > 0:
                lines.append(f"📋 配置列表: {config_count} 个账号")
            if scanned:
                lines.append(f"📱 扫码登录: {len(scanned)} 个账号")
                for i, c in enumerate(scanned, 1):
                    uid = parse_cookie_map(c).get("UID", "?")
                    lines.append(f"  {i}. UID={uid}")
            else:
                lines.append("  (无扫码登录的 Cookie)")
            lines.append("\n💡 使用 `.115login` 扫码添加新账号")
            await message.reply("\n".join(lines))
            return

    # 定时签到（无条件注册，运行时检查是否有 Cookie）
    checkin_hour = int(ctx.config.get("checkin_hour", 9) or 9)
    checkin_minute = int(ctx.config.get("checkin_minute", 0) or 0)

    async def _scheduled_sign():
        if not _load_cookies(ctx):
            ctx.log.info("[115签到] 定时触发但无 Cookie，跳过")
            return
        ctx.log.info("[115签到] 定时任务已触发")
        await _do_sign_all(ctx, "定时")

    ctx.schedule(
        _scheduled_sign,
        "cron",
        hour=checkin_hour,
        minute=checkin_minute,
        id="115签到-每日签到",
    )
    ctx.log.info("[115签到] 已注册每日签到任务: %02d:%02d", checkin_hour, checkin_minute)

    # 立即签到 action
    @ctx.action("sign_now")
    async def _api_sign_now(req=None):
        return await _do_sign_all(ctx, "手动")

    # 扫码登录 action
    @ctx.action("scan_now")
    async def _api_scan_now(req=None):
        return {"ok": False, "message": "扫码登录请使用命令 .115login 在聊天中操作"}


async def teardown(ctx):
    pass