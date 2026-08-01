# -*- coding: utf-8 -*-
# AWBotNest 插件：影巢签到 (myhdhivesign)

import asyncio
import json
import re
import time
import random
import hashlib
import httpx
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "影巢签到",
    "id": "myhdhivesign",
    "version": "3.7.0",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/myhdhivesign_v2.svg",
    "author": "凹凸曼",
    "description": "自动完成影巢(HDHive)每日签到，支持多账号、赌狗签到、失败重试。",
    "scope": "user",
    "default_enabled": True,
    "render_mode": "vue",
    "config_schema": {
        "accounts": {
            "type": "text", "default": "[]", "label": "账号配置(JSON)",
            "section": "账号", "help": "无需手动填写，在界面中添加账号后自动保存"
        },
        "action_hash": {
            "type": "string", "default": "", "label": "Action Hash(留空自动获取)",
            "section": "哈希", "help": "如果自动获取失败，可打开浏览器F12→网络→点签到→找next-action请求头，复制值填这里"
        },
        "sign_now": {
            "type": "action", "label": "▶ 立即签到", "section": "操作",
            "action": "sign_now", "danger": False
        },
        "notify_on_sign": {
            "type": "boolean", "default": True, "label": "推送签到结果",
            "section": "通知", "help": "定时签到和手动签到后推送结果通知"
        },
        "checkin_hour": {
            "type": "slider", "default": 9, "label": "签到小时",
            "min": 0, "max": 23, "step": 1, "section": "定时",
        },
        "checkin_minute": {
            "type": "slider", "default": 0, "label": "签到分钟",
            "min": 0, "max": 59, "step": 1, "section": "定时",
        },
        "_logs": {
            "type": "info", "label": "运行日志", "section": "日志"
        },
    },
}

_KV_ACCOUNTS = "hdhive_accounts"
_KV_LOGS = "hdhive_logs"
_KV_HASH = "hdhive_action_hash"
_KV_DEBUG = "hdhive_debug_logs"

_LOG_FILE = "/tmp/hdhive_sign.log"
_run_lock = None

def _log_debug(ctx, msg: str):
    ctx.log.info("[影巢签到] %s", msg)
    logs = ctx.kv.get(_KV_DEBUG, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_DEBUG, logs[-50:])
    _log_file(msg)

def _log_file(msg: str):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now(TZ).strftime('%H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def _get_accounts(ctx) -> list:
    acc_json = ctx.config.get("accounts", "[]")
    try:
        accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
    except Exception:
        accounts = []
    return accounts

async def _fetch_action_hash(base_url: str, ctx=None) -> str | None:
    if ctx:
        _log_debug(ctx, "获取action hash...")
    from urllib.parse import quote
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(timeout=15, verify=False, headers=headers) as cli:
            r = await cli.get(f"{base_url}/")
            if r.status_code != 200:
                return None
            html = r.text
            chunk_urls = set()
            for m in re.finditer(r'(/_next/static/chunks/[^"\'\\s]+\.js)', html):
                chunk_urls.add(m.group(1))
            try:
                rsc = await cli.get(base_url, headers={"User-Agent": headers["User-Agent"], "Accept": "text/x-component"})
                if rsc.status_code == 200:
                    for m in re.finditer(r'static/chunks/([^"\'\\,]+\.js)', rsc.text):
                        chunk_rel = "/_next/static/chunks/" + m.group(1)
                        chunk_urls.add(chunk_rel)
            except Exception:
                pass
            for chunk_rel in sorted(chunk_urls):
                if "layout" not in chunk_rel:
                    continue
                encoded = quote(chunk_rel, safe='/:')
                chunk_url = f"{base_url}{encoded}"
                try:
                    cr = await cli.get(chunk_url, timeout=15)
                    if cr.status_code != 200:
                        continue
                    text = cr.text
                    m = re.search(r'createServerReference\)\s*\(\s*["\']([0-9a-f]{40,})["\'][^"\']*["\']checkIn["\']', text)
                    if m:
                        _log_debug(ctx, f"checkIn hash: {m.group(1)[:16]}...")
                        return m.group(1)
                except Exception:
                    continue
            for chunk_rel in chunk_urls:
                encoded = quote(chunk_rel, safe='/:')
                chunk_url = f"{base_url}{encoded}"
                try:
                    cr = await cli.get(chunk_url, timeout=15)
                    if cr.status_code != 200:
                        continue
                    text = cr.text
                    m = re.search(r'createServerReference\)\s*\(\s*["\']([0-9a-f]{40,})["\'][^"\']*["\']checkIn["\']', text)
                    if m:
                        _log_debug(ctx, f"checkIn hash: {m.group(1)[:16]}...")
                        return m.group(1)
                except Exception:
                    continue
            _log_debug(ctx, "使用已知 fallback hash")
            return "40ca031f4e08ca31564fb6889587933a9bb5bdea39"
    except Exception:
        return None

async def _login_with_playwright(base_url: str, username: str, password: str) -> str | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    # 优先用 cloakbrowser（更强，二进制级补丁），没有则用我们的 stealth 模块兜底
    has_cloak = False
    try:
        import cloakbrowser
        has_cloak = True
    except ImportError:
        pass

    if not has_cloak:
        try:
            from ._playwright_stealth import create_stealth_context, STEALTH_LAUNCH_ARGS
        except ImportError:
            return None

    try:
        async with async_playwright() as p:
            if has_cloak:
                browser = await cloakbrowser.launch_async(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                    locale="zh-CN",
                    timezone="Asia/Shanghai",
                )
                ctx = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080},
                    locale="zh-CN",
                    timezone_id="Asia/Shanghai",
                )
            else:
                browser = await p.chromium.launch(
                    headless=True,
                    args=STEALTH_LAUNCH_ARGS,
                )
                ctx = await create_stealth_context(browser)
            page = await ctx.new_page()
            page.set_default_timeout(60000)
            await page.goto(f"{base_url}/login", wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            max_wait = 60
            start = time.time()
            while time.time() - start < max_wait:
                content = await page.content()
                if "Checking your browser" in content or "Just a moment" in content:
                    await asyncio.sleep(3)
                    continue
                try:
                    if await page.locator('input[name="username"]').count() > 0:
                        break
                except Exception:
                    pass
                await asyncio.sleep(3)
            try:
                await page.fill('input[name="username"]', username, timeout=30000)
                await asyncio.sleep(1)
                await page.fill('input[type="password"]', password, timeout=30000)
                await asyncio.sleep(1)
                await page.click('button[type="submit"]', timeout=30000)
                await asyncio.sleep(5)
            except Exception:
                pass
            cookies = await ctx.cookies()
            cookie_parts = []
            for c in cookies:
                cookie_parts.append(f"{c['name']}={c['value']}")
            await browser.close()
            return "; ".join(cookie_parts) if "token" in "; ".join(cookie_parts) else None
    except Exception:
        return None

async def _login_get_token(base_url: str, username: str, password: str) -> str | None:
    apis = ["/api/customer/user/login", "/api/customer/auth/login"]
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    for api in apis:
        try:
            async with httpx.AsyncClient(timeout=15, verify=False, headers=headers) as cli:
                url = f"{base_url}{api}"
                r = await cli.post(url, json={"username": username, "password": password})
                if r.status_code == 200:
                    data = r.json()
                    token = data.get("data", {}).get("token") or data.get("token", "")
                    if token:
                        return f"token={token}"
        except Exception:
            continue
    return None

async def _do_sign(cookie_str: str, base_url: str, action_hash: str, gamble: bool) -> dict:
    token = ""
    cookies = {}
    for item in cookie_str.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies[k] = v
            if k == "token":
                token = v
    if not token:
        return {"success": False, "message": "Cookie 缺少 token"}
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    body = json.dumps([gamble])
    user_info = {"points": 0, "signin_days": 0, "nickname": "", "signed_in_today": False}
    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            get_cookies = {k: v for k, v in cookies.items() if k != "hdh_sa_token"}
            hr = await cli.get(base_url, headers={"User-Agent": ua}, cookies=get_cookies)
            csrf = ""
            for k, v in hr.headers.items():
                if k.lower() == "set-cookie" and "hdh_sa_token" in v:
                    m = re.search(r'hdh_sa_token=([^;]+)', v)
                    if m:
                        csrf = m.group(1)
                        break
            if not csrf:
                for c in cli.cookies:
                    if c.name == "hdh_sa_token":
                        csrf = c.value
                        break
            if csrf:
                cookies["hdh_sa_token"] = csrf
            text_raw = hr.text
            m = re.search(r'\\"nickname\\"\s*:\s*\\"([^"]+)\\"', text_raw)
            if m:
                try:
                    user_info["nickname"] = json.loads('"' + m.group(1) + '"')
                except Exception:
                    user_info["nickname"] = m.group(1)
            m = re.search(r'\\"points\\"\s*:\s*(\d+)', text_raw)
            if m:
                user_info["points"] = int(m.group(1))
            m = re.search(r'\\"signin_days_total\\"\s*:\s*(\d+)', text_raw)
            if m:
                user_info["signin_days"] = int(m.group(1))
            headers = {
                "User-Agent": ua,
                "Accept": "text/x-component",
                "Content-Type": "text/plain;charset=UTF-8",
                "Origin": base_url,
                "Referer": f"{base_url}/",
                "next-action": action_hash,
                "Authorization": f"Bearer {token}",
            }
            resp = await cli.post(base_url, headers=headers, cookies=cookies, content=body)
        if resp.status_code == 200:
            try:
                hr2 = await cli.get(base_url, headers={"User-Agent": ua}, cookies=cookies)
                t2 = hr2.text
                m = re.search(r'\\"points\\"\s*:\s*(\d+)', t2)
                if m:
                    user_info["points"] = int(m.group(1))
                m = re.search(r'\\"signin_days_total\\"\s*:\s*(\d+)', t2)
                if m:
                    user_info["signin_days"] = int(m.group(1))
            except Exception:
                pass
        text = resp.text
        redirected = False
        for line in text.splitlines():
            m = re.match(r"^\d+:(\{.*\})\s*$", line)
            if not m:
                continue
            try:
                obj = json.loads(m.group(1))
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            keys = set(obj.keys())
            if keys <= {"a", "f", "b", "q", "i", "S"}:
                if "login" in str(obj):
                    redirected = True
                continue
            if "f" in obj and not any(k in obj for k in ("error", "response", "success", "message", "description")):
                if "login" in str(obj):
                    redirected = True
                continue
            if "error" in obj and isinstance(obj["error"], dict):
                err = obj["error"]
                return {"success": False, "message": str(err.get("message") or err.get("description") or "签到失败"), "user": user_info}
            payload = obj.get("response") or obj
            msg = str(payload.get("message") or payload.get("description") or "")
            already = any(k in msg for k in ("已经签到", "签到过", "明天再来"))
            if already:
                user_info["signed_in_today"] = True
                return {"success": True, "message": "今日已签到", "user": user_info}
            if bool(payload.get("success")):
                user_info["signed_in_today"] = True
                return {"success": True, "message": msg or "签到成功", "user": user_info}
            return {"success": False, "message": msg or "签到失败", "user": user_info, "raw": text[:200]}
        if redirected:
            return {"success": False, "message": "Cookie 失效，请重新登录", "user": user_info}
        if resp.status_code == 200:
            user_info["signed_in_today"] = True
            return {"success": True, "message": "签到请求已发送", "user": user_info}
        elif resp.status_code == 409:
            try:
                body = resp.json()
                msg = body.get("message") or body.get("error") or str(body)
            except Exception:
                msg = resp.text[:200]
            return {"success": False, "message": f"HTTP 409: {msg}"}
        return {"success": False, "message": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


async def setup(ctx):
    _log_debug(ctx, "插件加载完成")

    # 启动时清理过期 signed_today 标记（防止跨天残留）
    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
    accounts = _get_accounts(ctx)
    for acc in accounts:
        cookie = acc.get("cookie", "")
        if not cookie:
            continue
        sk = f"signed_today:{cookie[:20]}"
        st = ctx.kv.get(sk, "")
        if st and st != today_str:
            _log_debug(ctx, f"清理过期签到标记: {acc.get('name','?')} ({st} → 待签到)")
            ctx.kv.set(sk, "")

    async def _sign_account(ctx, acc, base_url, action_hash):
        """签到单个账号，返回结果，失败自动重试"""
        name = acc.get("name", "未知")
        cookie = acc.get("cookie", "")
        if not cookie:
            return {"name": name, "success": False, "message": "缺少Cookie"}
        gamble = acc.get("gamble", False)
        mode = "赌狗" if gamble else "普通"
        _log_debug(ctx, f"签到: {name}({mode})")
        # 失败自动重试，最多3次
        max_retries = 3
        last_result = None
        for attempt in range(1, max_retries + 1):
            result = await _do_sign(cookie, base_url, action_hash, gamble)
            if result["success"]:
                last_result = result
                break
            # 网络类错误才重试（server disconnected / timeout / connection error）
            msg = result.get("message", "")
            is_network_error = any(k in msg.lower() for k in (
                "closed connection", "incomplete", "chunked", "timeout",
                "connection", "reset", "eof", "read timed out",
                "remote", "disconnect", "broken", "transport"
            ))
            if not is_network_error:
                # 非网络错误（如Cookie失效、已签到）不重试
                last_result = result
                break
            _log_debug(ctx, f"{name}: 第{attempt}次失败({msg})，{10 if attempt < max_retries else 0}秒后重试...")
            last_result = result
            if attempt < max_retries:
                await asyncio.sleep(10)
        result = last_result
        msg = result["message"]
        if result.get("user"):
            u = result["user"]
            pts = u.get("points", 0)
            days = u.get("signin_days", 0)
            nick = u.get("nickname", "")
            if nick:
                msg += f" | {nick} 积分={pts} 已签{days}天"
            if days > 0:
                ctx.kv.set(f"last_signin_days:{cookie[:20]}", days)
        _log_debug(ctx, f"{name}: {msg}")
        if result.get("user"):
            u = result["user"]
            _log_debug(ctx, f"{name}: {u.get('nickname','')} 积分={u.get('points',0)} 签到天数={u.get('signin_days',0)}")
        # 只有签到成功才标记已签到，失败不标记（允许重试）
        if result["success"]:
            ctx.kv.set(f"signed_today:{cookie[:20]}", datetime.now(TZ).strftime("%Y-%m-%d"))
        return {"name": name, "mode": mode, "success": result["success"], "message": msg}

    async def _get_action_hash(ctx, base_url):
        """获取 action hash"""
        action_hash = await _fetch_action_hash(base_url, ctx)
        if not action_hash:
            _log_debug(ctx, "自动获取hash失败，使用配置中的hash")
            action_hash = ctx.config.get("action_hash", "") or ctx.kv.get(_KV_HASH, "")
        if action_hash:
            ctx.kv.set(_KV_HASH, action_hash)
            _log_debug(ctx, f"使用hash: {action_hash[:16]}...")
        return action_hash

    async def _do_sign_all(source="定时"):
        """签到所有账号，source 为 '定时' 或 '手动'"""
        _log_debug(ctx, f"开始{source}签到")
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        accounts = _get_accounts(ctx)
        if not accounts:
            _log_debug(ctx, "无账号配置")
            return {"ok": False, "message": "未配置账号"}

        action_hash = await _get_action_hash(ctx, base_url)
        if not action_hash:
            return {"ok": False, "message": "无法获取 action hash，请手动填写"}

        logs = []
        notify_lines = []
        for i, acc in enumerate(accounts):
            name = acc.get("name", f"账号{i+1}")
            cookie = acc.get("cookie", "")
            username = acc.get("username", "")
            password = acc.get("password", "")

            # 检查今日是否已签到
            today_str = datetime.now(TZ).strftime("%Y-%m-%d")
            if cookie:
                signed_key = f"signed_today:{cookie[:20]}"
                if ctx.kv.get(signed_key, "") == today_str:
                    _log_debug(ctx, f"{name}: 今日已签到，跳过")
                    logs.append({"time": _now(), "name": name, "status": "✅", "message": "今日已签到"})
                    notify_lines.append(f"✅ {name}: 今日已签到")
                    continue

            # 无Cookie时尝试用账号密码登录
            if not cookie and username and password:
                saved = ctx.kv.get(f"cookie:{acc.get('name', '')}", "")
                if saved:
                    cookie = saved
                    acc["cookie"] = saved
                    _log_debug(ctx, f"{name}: 使用已保存的Cookie")
                else:
                    _log_debug(ctx, f"{name}: 用 Playwright 模拟登录")
                    cookie = await _login_with_playwright(base_url, username, password)
                    if cookie:
                        acc["cookie"] = cookie
                        ctx.kv.set(f"cookie:{acc.get('name', '')}", cookie)
                        _log_debug(ctx, f"{name}: 登录成功")
                    else:
                        _log_debug(ctx, f"{name}: 登录失败")

            if not cookie:
                logs.append({"time": _now(), "name": name, "status": "❌", "message": "缺少Cookie"})
                notify_lines.append(f"❌ {name}: 缺少Cookie")
                continue

            r = await _sign_account(ctx, acc, base_url, action_hash)

            # Cookie 失效时自动重新登录
            if not r["success"] and "Cookie 失效" in r.get("message", "") and username and password:
                _log_debug(ctx, f"{name}: Cookie 失效，尝试重新登录")
                new_cookie = await _login_with_playwright(base_url, username, password)
                if new_cookie:
                    acc["cookie"] = new_cookie
                    ctx.kv.set(f"cookie:{acc.get('name', '')}", new_cookie)
                    _log_debug(ctx, f"{name}: 重新登录成功，重试签到")
                    r = await _sign_account(ctx, acc, base_url, action_hash)
                else:
                    _log_debug(ctx, f"{name}: 重新登录失败")

            logs.append({"time": _now(), "name": r["name"], "mode": r.get("mode", ""), "status": "✅" if r["success"] else "❌", "message": r["message"]})
            icon = "✅" if r["success"] else "❌"
            notify_lines.append(f"{icon} {r['name']}({r.get('mode','')}): {r['message']}")
            await asyncio.sleep(1)

        if logs:
            ctx.kv.set(_KV_LOGS, logs)
        if ctx.config.get("notify_on_sign", True):
            has_errors = any("❌" in l for l in notify_lines)
            level = "error" if all("❌" in l for l in notify_lines) else ("warning" if has_errors else "success")
            await ctx.notify(f"📋 影巢签到结果\n" + "\n".join(notify_lines), level=level, category="影巢签到")

        return {"ok": True, "message": "\n".join(f"{l['status']} {l['name']}({l.get('mode','')}): {l['message']}" for l in logs)}

    # 注册定时签到（参考 GPT-GOD 的 cron 模式）
    checkin_hour = int(ctx.config.get("checkin_hour", 9) or 9)
    checkin_minute = int(ctx.config.get("checkin_minute", 0) or 0)

    async def _scheduled_checkin():
        ctx.log.info("[影巢签到] 定时任务已触发")
        await _do_sign_all("定时")

    ctx.schedule(
        _scheduled_checkin,
        "cron",
        hour=checkin_hour,
        minute=checkin_minute,
        id="影巢签到-每日签到",
    )
    _log_debug(ctx, f"已注册每日签到任务: {checkin_hour:02d}:{checkin_minute:02d}")

    # 启动时立即检查一次（补签今天错过的窗口）
    asyncio.create_task(_do_sign_all("启动"))

    @ctx.action("sign_now")
    async def _api_sign_now(req=None):
        return await _do_sign_all()

    @ctx.on_api("/sign_now", methods=["POST"])
    async def _api_sign_now_api(req):
        return await _do_sign_all()

    @ctx.on_api("/get_accounts", methods=["GET"])
    async def _api_get_accounts(req):
        accounts = _get_accounts(ctx)
        for acc in accounts:
            if not acc.get("cookie"):
                saved = ctx.kv.get(f"cookie:{acc.get('name', '')}", "")
                if saved:
                    acc["cookie"] = saved
        return {"accounts": accounts}

    @ctx.on_api("/get_account_status", methods=["POST"])
    async def _api_get_account_status(req):
        _log_debug(ctx, "获取账号状态")
        accounts = _get_accounts(ctx)
        results = []
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        for acc in accounts:
            cookie = acc.get("cookie", "")
            if not cookie:
                results.append({"name": acc.get("name", ""), "points": 0, "days": 0, "signed": False, "error": "无Cookie"})
                continue
            try:
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                cookies = {}
                for item in cookie.split(";"):
                    if "=" in item:
                        k, v = item.strip().split("=", 1)
                        cookies[k] = v
                get_cookies = {k: v for k, v in cookies.items() if k != "hdh_sa_token"}
                async with httpx.AsyncClient(timeout=15, verify=False) as cli:
                    hr = await cli.get(base_url, headers={"User-Agent": ua}, cookies=get_cookies)
                    text = hr.text
                    pts = 0; days = 0; nick = ""
                    m = re.search(r'\\"nickname\\"\s*:\s*\\"([^"]+)\\"', text)
                    if m:
                        try:
                            nick = json.loads('"' + m.group(1) + '"')
                        except Exception:
                            nick = m.group(1)
                    m = re.search(r'\\"points\\"\s*:\s*(\d+)', text)
                    if m:
                        pts = int(m.group(1))
                    m = re.search(r'\\"signin_days_total\\"\s*:\s*(\d+)', text)
                    if m:
                        days = int(m.group(1))
                    # 检查签到状态：比较当前signin_days_total与上次记录
                    today_str = datetime.now(TZ).strftime("%Y-%m-%d")
                    last_days = ctx.kv.get(f"last_signin_days:{acc.get('cookie','')[:20]}", 0)
                    signed = days > last_days if last_days > 0 else False
                    # 如果signed_today记录存在也作为辅助判断
                    signed_today = ctx.kv.get(f"signed_today:{acc.get('cookie','')[:20]}", "")
                    if signed_today == today_str:
                        signed = True
                    results.append({"name": nick or acc.get("name", ""), "points": pts, "days": days, "signed": signed})
            except Exception as e:
                _log_debug(ctx, f"状态查询失败: {e}")
                results.append({"name": acc.get("name", ""), "points": 0, "days": 0, "signed": False, "error": str(e)})
        _log_debug(ctx, "状态: " + " | ".join(
            f'{r["name"]}:{r["points"]}分/{r["days"]}天{"✅" if r.get("signed") else "⏳"}'
            for r in results))
        return {"results": results}

    @ctx.on_api("/get_logs", methods=["GET"])
    async def _api_get_logs(req):
        return {"logs": ctx.kv.get(_KV_LOGS, [])}

    @ctx.on_api("/get_debug_logs", methods=["GET"])
    async def _api_get_debug_logs(req):
        return {"logs": ctx.kv.get(_KV_DEBUG, [])}

    @ctx.on_api("/save_accounts", methods=["POST"])
    async def _api_save_accounts(req):
        try:
            body = req.json if hasattr(req, 'json') else {}
            accounts = body.get("accounts", []) if isinstance(body, dict) else []
            if not accounts:
                return {"ok": False, "message": "无账号数据"}
            # 更新配置
            try:
                ctx.update_config({"accounts": json.dumps(accounts, ensure_ascii=False)})
            except Exception:
                _log_debug(ctx, "update_config 失败，尝试直接保存")
                import json as _json
                cfg = dict(ctx.config or {})
                cfg["accounts"] = _json.dumps(accounts, ensure_ascii=False)
                ctx.update_config(cfg)
            _log_debug(ctx, f"已保存 {len(accounts)} 个账号")
            return {"ok": True, "message": f"已保存 {len(accounts)} 个账号"}
        except Exception as e:
            _log_debug(ctx, f"保存账号失败: {e}")
            return {"ok": False, "message": str(e)}


async def teardown(ctx):
    pass