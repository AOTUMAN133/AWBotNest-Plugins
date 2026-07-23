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
    "version": "3.0.1",
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
            "type": "number", "default": 9, "label": "签到开始时间(时)",
            "section": "定时", "help": "定时签到开始的小时"
        },
        "sign_window": {
            "type": "number", "default": 2, "label": "签到时间窗口(小时)",
            "section": "定时", "help": "在开始时间后的窗口内随机签到，每个账号独立随机"
        },
        "sign_minute": {
            "type": "number", "default": 0, "label": "签到分钟",
            "section": "定时", "help": "当窗口为0时固定使用此分钟"
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

            # 第一步：查找包含 checkIn 的 hash
            for chunk_rel in chunk_urls:
                if "layout" not in chunk_rel:
                    continue
                chunk_url = f"{base_url}{chunk_rel}"
                try:
                    cr = await cli.get(chunk_url, timeout=15)
                    if cr.status_code != 200:
                        continue
                    text = cr.text
                    # 查找 createServerReference)("hash"... "checkIn")
                    m = re.search(r'createServerReference\)\s*\(\s*["\']([0-9a-f]{40,})["\'][^"\']*["\']checkIn["\']', text)
                    if m:
                        _log_debug(ctx, f"checkIn hash: {m.group(1)[:16]}...")
                        return m.group(1)
                except Exception:
                    continue

            # 第二步：从 RSC payload 中查找包含 checkIn 的 chunk
            try:
                rsc = await cli.get(base_url, headers={"User-Agent": headers["User-Agent"], "Accept": "text/x-component"})
                if rsc.status_code == 200:
                    for m in re.finditer(r'static/chunks/([^"\'\\,]+\.js)', rsc.text):
                        chunk_rel = "/_next/static/chunks/" + m.group(1)
                        if chunk_rel in chunk_urls:
                            continue
                        chunk_urls.add(chunk_rel)
                    for chunk_rel in chunk_urls:
                        chunk_url = f"{base_url}{chunk_rel}"
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
            except Exception:
                pass

            # 第三步：兜底，返回已知的 hash
            _log_debug(ctx, "使用已知 fallback hash")
            return "40ca031f4e08ca31564fb6889587933a9bb5bdea39"
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
            # 先请求首页获取 CSRF token（不传 hdh_sa_token，让服务器下发新的）
            get_cookies = {k: v for k, v in cookies.items() if k != "hdh_sa_token"}
            hr = await cli.get(base_url, headers={"User-Agent": ua}, cookies=get_cookies)
            # 此时 cli.cookies 中已有服务器下发的 hdh_sa_token

            # 从 RSC 响应中解析用户信息（RSC 格式中 JSON 是转义的）
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
            resp = await cli.post(base_url, headers=headers, content=body)
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
        """每分钟检查，在签到窗口内逐个账号签到"""
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        cfg = ctx.config
        acc_json = cfg.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        if not accounts:
            return
        sign_hour = int(cfg.get("sign_hour", 9) or 9)
        sign_window = int(cfg.get("sign_window", 2) or 2)
        now = datetime.now(TZ)
        window_end = sign_hour + sign_window
        if now.hour < sign_hour or now.hour >= window_end:
            return
        action_hash = ctx.config.get("action_hash", "") or ctx.kv.get(_KV_HASH, "")
        if not action_hash:
            action_hash = await _fetch_action_hash(base_url)
            if action_hash:
                ctx.kv.set(_KV_HASH, action_hash)
            else:
                return
        total_minutes = sign_window * 60
        today_str = now.strftime("%Y-%m-%d")
        seed_base = abs(hash(today_str))
        current_offset = (now.hour - sign_hour) * 60 + now.minute
        for i, acc in enumerate(accounts):
            seed = seed_base + i
            rng = random.Random(seed)
            offset = rng.randint(0, total_minutes - 1)
            if offset != current_offset:
                continue
            cookie = acc.get("cookie", "")
            if not cookie:
                continue
            name = acc.get("name", f"账号{i+1}")
            gamble = acc.get("gamble", False)
            mode = "赌狗" if gamble else "普通"
            last_days_key = f"last_signin_days:{cookie[:20]}"
            last_days = ctx.kv.get(last_days_key, 0)
            if last_days > 0:
                _log_debug(ctx, f"{name}: 今日已签，跳过")
                continue
            _log_debug(ctx, f"定时签到: {name}({mode})")
            result = await _do_sign(cookie, base_url, action_hash, gamble)
            if result.get("user"):
                u = result["user"]
                days = u.get("signin_days", 0)
                if days > 0:
                    ctx.kv.set(last_days_key, days)
            _log_debug(ctx, f"{name}: {result['message']}")

    sign_hour = int(ctx.config.get("sign_hour", 9) or 9)
    sign_window = int(ctx.config.get("sign_window", 2) or 2)
    # 每分钟运行一次，在签到窗口内自动处理
    ctx.schedule(_sign_tick, "interval", minutes=1, id="hdhive_sign")

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
                if days > 0:
                    ctx.kv.set(f"last_signin_days:{cookie[:20]}", days)
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

    @ctx.on_api("/get_account_status", methods=["POST"])
    async def _api_get_account_status(req):
        """获取每个账号的当前状态（积分、签到天数等）"""
        _log_debug(ctx, "获取账号状态")
        acc_json = ctx.config.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        results = []
        base_url = ctx.config.get("base_url", "https://hdhive.com")
        for acc in accounts:
            cookie = acc.get("cookie", "")
            if not cookie:
                results.append({"name": acc.get("name", ""), "points": 0, "days": 0, "error": "无Cookie"})
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
                    # 获取上次签到后记录的 days 值，判断是否已签到
                    last_days = ctx.kv.get(f"last_signin_days:{acc.get('cookie','')[:20]}", 0)
                    signed = days > last_days if last_days > 0 else False
                    results.append({"name": nick or acc.get("name", ""), "points": pts, "days": days, "signed": signed})
            except Exception as e:
                _log_debug(ctx, f"状态查询失败: {e}")
                results.append({"name": acc.get("name", ""), "points": 0, "days": 0, "error": str(e)})
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


async def teardown(ctx):
    pass