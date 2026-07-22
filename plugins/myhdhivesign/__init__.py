# -*- coding: utf-8 -*-
# AWBotNest 插件：影巢签到 (myhdhivesign)

import asyncio
import json
import re
import time
import httpx
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "影巢签到",
    "id": "myhdhivesign",
    "version": "2.2.7",
    "author": "凹凸曼",
    "description": "自动完成影巢(HDHive)每日签到，支持多账号、赌狗签到、失败重试。",
    "scope": "user",
    "default_enabled": True,
    "render_mode": "vue",
    "requirements": ["httpx", "playwright"],
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
        "sign_hour": {
            "type": "number", "default": 9, "label": "签到时间(时)",
            "section": "定时", "help": "0-23"
        },
        "sign_minute": {
            "type": "number", "default": 0, "label": "签到时间(分)",
            "section": "定时", "help": "0-59"
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


def _log_debug(ctx, msg: str):
    logs = ctx.kv.get(_KV_DEBUG, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_DEBUG, logs[-50:])


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


async def _fetch_action_hash(base_url: str, ctx=None) -> str | None:
    """从 Next.js chunk 中提取签到 action hash"""
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

            for chunk_rel in chunk_urls:
                chunk_url = f"{base_url}{chunk_rel}"
                try:
                    cr = await cli.get(chunk_url, timeout=15)
                    if cr.status_code != 200:
                        continue
                    text = cr.text
                    # 提取 createServerReference)("hash"
                    m = re.search(r'createServerReference\)\s*\(\s*["\']([0-9a-f]{40,})["\']', text)
                    if m:
                        return m.group(1)
                except Exception:
                    continue
            # 兜底：直接请求 layout chunk
            try:
                cr = await cli.get(f"{base_url}/_next/static/chunks/app/layout-217e777681ace273.js", timeout=15)
                if cr.status_code == 200:
                    m = re.search(r'createServerReference\)\s*\(\s*["\']([0-9a-f]{40,})["\']', cr.text)
                    if m:
                        h = m.group(1)
                        # layout chunk 里的 hash 是 encrypt/decrypt 的，不是 checkIn 的
                        # 正确 hash 在动态加载的 chunk 中，只能用已知的 fallback
                        _log_debug(ctx, f"layout hash: {h[:16]}...")
                        return "4087930a783c3dca3c375217c4de7be2e0ef7f2a91"
            except Exception:
                pass
            return None
    except Exception:
        return None


async def _login_with_playwright(base_url: str, username: str, password: str) -> str | None:
    """用 Playwright 浏览器模拟登录，返回 cookie 字符串"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await ctx.new_page()
            try:
                # 访问首页，等待 Cloudflare 验证通过
                await page.goto(f"{base_url}/", timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(10000)

                # 获取 CSRF token
                cookies = await ctx.cookies()
                csrf = ""
                for c in cookies:
                    if c["name"] == "hdh_sa_token":
                        csrf = c["value"]
                if not csrf:
                    await browser.close()
                    return None

                # 用 fetch 调 server action 登录
                js = f"""
                (async () => {{
                    const r = await fetch('/', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'text/plain;charset=UTF-8',
                            'next-action': '40b2c3190fb3396c5f003b3ca996db391fb6693f32',
                            'Accept': 'text/x-component',
                        }},
                        body: JSON.stringify([{{username: '{username}', password: '{password}', remember: true}}])
                    }});
                    return await r.text();
                }})()
                """
                await page.evaluate(js)
                await page.wait_for_timeout(5000)

                # 检查是否登录成功（有没有 token cookie）
                cookies = await ctx.cookies()
                token = ""
                for c in cookies:
                    if c["name"] == "token":
                        token = c["value"]
                await browser.close()
                if token:
                    return f"token={token}"
            except Exception:
                await browser.close()
                return None
    except Exception:
        return None
    return None


async def _login_get_token(base_url: str, username: str, password: str) -> str | None:
    """用用户名密码登录，返回完整 cookie 字符串"""
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
        except Exception as e:
            continue
    return None


async def _do_sign(cookie_str: str, base_url: str, action_hash: str, gamble: bool) -> dict:
    """执行签到，自动获取 CSRF token，返回签到结果和用户信息"""
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

    # 解析用户信息
    user_info = {"points": 0, "signin_days": 0, "nickname": "", "signed_in_today": False}

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            # 先请求首页获取 CSRF token 和用户信息
            hr = await cli.get(base_url, headers={"User-Agent": ua}, cookies=cookies)
            csrf_cookie = ""
            # 从响应头中提取 CSRF cookie（httpx 的 cookie jar 可能不捕获 HttpOnly cookie）
            for k, v in hr.headers.items():
                if k.lower() == "set-cookie" and "hdh_sa_token" in v:
                    m = re.search(r'hdh_sa_token=([^;]+)', v)
                    if m:
                        csrf_cookie = m.group(1)
                        break
            if csrf_cookie:
                cookies["hdh_sa_token"] = csrf_cookie

            # 从 RSC 响应中解析用户信息
            for line in hr.text.splitlines():
                if '"currentUser"' in line:
                    try:
                        m = re.search(r'\{[^{}]*"points"\s*:\s*(\d+)[^{}]*"signin_days_total"\s*:\s*(\d+)[^{}]*\}', line)
                        if m:
                            user_info["points"] = int(m.group(1))
                            user_info["signin_days"] = int(m.group(2))
                        m = re.search(r'"nickname"\s*:\s*"([^"]+)"', line)
                        if m:
                            user_info["nickname"] = m.group(1)
                        if '"signin"' in line.lower() or '"signed"' in line.lower():
                            user_info["signed_in_today"] = "已签到" in line or "true" in line.lower()
                    except Exception:
                        pass

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
        text = resp.text
        # 解析 RSC 响应（参考原插件 _checkin_parse_rsc_result）
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
            # 跳过 RSC 元数据行
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
                return {"success": False, "message": str(err.get("message") or err.get("description") or "签到失败")}
            # 找到有效响应
            payload = obj.get("response") or obj
            msg = str(payload.get("message") or payload.get("description") or "")
            already = any(k in msg for k in ("已经签到", "签到过", "明天再来"))
            if already:
                return {"success": True, "message": "今日已签到", "user": user_info}
            if bool(payload.get("success")):
                return {"success": True, "message": msg or "签到成功", "user": user_info}
            return {"success": False, "message": msg or "签到失败", "user": user_info}
        if redirected:
            return {"success": False, "message": "Cookie 失效，请重新登录", "user": user_info}
        if resp.status_code == 200:
            return {"success": True, "message": "签到请求已发送", "user": user_info}
        elif resp.status_code == 409:
            # 409 Conflict - 可能已签到或请求冲突
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

    async def _sign_tick():
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        acc_json = ctx.config.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        if not accounts:
            return
        action_hash = ctx.config.get("action_hash", "") or ctx.kv.get(_KV_HASH, "")
        if not action_hash:
            action_hash = await _fetch_action_hash(base_url)
            if action_hash:
                ctx.kv.set(_KV_HASH, action_hash)
            else:
                return
        logs = []
        for i, acc in enumerate(accounts):
            name = acc.get("name", f"账号{i+1}")
            cookie = acc.get("cookie", "")
            if not cookie:
                continue
            gamble = acc.get("gamble", False)
            mode = "赌狗" if gamble else "普通"
            ctx.log.info("[影巢签到] %s(%s) 签到", name, mode)
            result = await _do_sign(cookie, base_url, action_hash, gamble)
            status = "✅" if result["success"] else "❌"
            logs.append({"time": _now(), "name": name, "mode": mode, "status": status, "message": result["message"]})
            ctx.log.info("[影巢签到] %s: %s", name, result["message"])
            await asyncio.sleep(1)

    sign_hour = int(ctx.config.get("sign_hour", 9) or 9)
    sign_minute = int(ctx.config.get("sign_minute", 0) or 0)
    ctx.schedule(_sign_tick, "cron", hour=sign_hour, minute=sign_minute, id="hdhive_sign")

    async def _do_sign_all():
        _log_debug(ctx, "开始签到")
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        acc_json = ctx.config.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        if not accounts:
            _log_debug(ctx, "无账号配置")
            return {"ok": False, "message": "未配置账号"}
        _log_debug(ctx, f"账号数: {len(accounts)}")

        action_hash = ctx.config.get("action_hash", "") or ctx.kv.get(_KV_HASH, "")
        if not action_hash:
            _log_debug(ctx, f"获取action hash: {base_url}")
            action_hash = await _fetch_action_hash(base_url)
            if action_hash:
                ctx.kv.set(_KV_HASH, action_hash)
                _log_debug(ctx, f"hash: {action_hash[:16]}...")
            else:
                _log_debug(ctx, "无法获取hash，请在配置中手动填写")
                return {"ok": False, "message": "无法获取 action hash，请手动填写"}

        logs = []
        for i, acc in enumerate(accounts):
            name = acc.get("name", f"账号{i+1}")
            cookie = acc.get("cookie", "")
            username = acc.get("username", "")
            password = acc.get("password", "")
            if not cookie and username and password:
                _log_debug(ctx, f"{name}: 用 Playwright 模拟登录")
                cookie = await _login_with_playwright(base_url, username, password)
                if cookie:
                    acc["cookie"] = cookie
                    _log_debug(ctx, f"{name}: 登录成功")
                else:
                    _log_debug(ctx, f"{name}: 登录失败，请检查用户名密码或直接填Cookie")
            if not cookie:
                _log_debug(ctx, f"{name}: 缺少Cookie")
                logs.append({"time": _now(), "name": name, "status": "❌", "message": "缺少Cookie"})
                continue
            gamble = acc.get("gamble", False)
            mode = "赌狗" if gamble else "普通"
            _log_debug(ctx, f"签到: {name}({mode})")
            result = await _do_sign(cookie, base_url, action_hash, gamble)
            status = "✅" if result["success"] else "❌"
            msg = result["message"]
            if result.get("user"):
                u = result["user"]
                pts = u.get("points", 0)
                days = u.get("signin_days", 0)
                nick = u.get("nickname", "")
                if nick:
                    msg += f" | {nick} 积分={pts} 已签{days}天"
            logs.append({"time": _now(), "name": name, "mode": mode, "status": status, "message": msg})
            _log_debug(ctx, f"{name}: {msg}")
            if result.get("user"):
                u = result["user"]
                pts = u.get("points", 0)
                days = u.get("signin_days", 0)
                nick = u.get("nickname", "")
                _log_debug(ctx, f"{name}: {nick} 积分={pts} 签到天数={days}")
            await asyncio.sleep(1)

        ctx.kv.set(_KV_LOGS, logs)
        return {"ok": True, "message": "\n".join(f"{l['status']} {l['name']}({l.get('mode','')}): {l['message']}" for l in logs)}

    @ctx.action("sign_now")
    async def _api_sign_now(req=None):
        return await _do_sign_all()

    @ctx.on_api("/sign_now", methods=["POST"])
    async def _api_sign_now_api(req):
        return await _do_sign_all()

    @ctx.on_api("/get_accounts", methods=["GET"])
    async def _api_get_accounts(req):
        acc_json = ctx.config.get("accounts", "[]")
        accounts = []
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            pass
        return {"accounts": accounts}

    @ctx.on_api("/get_logs", methods=["GET"])
    async def _api_get_logs(req):
        return {"logs": ctx.kv.get(_KV_LOGS, [])}

    @ctx.on_api("/get_debug_logs", methods=["GET"])
    async def _api_get_debug_logs(req):
        return {"logs": ctx.kv.get(_KV_DEBUG, [])}


async def teardown(ctx):
    pass