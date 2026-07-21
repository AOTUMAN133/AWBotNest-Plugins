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
    "version": "1.1.7",
    "author": "凹凸曼",
    "description": "自动完成影巢(HDHive)每日签到，支持多账号、赌狗签到、失败重试。",
    "scope": "user",
    "default_enabled": True,
    "render_mode": "vue",
    "requirements": ["httpx"],
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
    """记录调试日志，最多保留50条"""
    logs = ctx.kv.get(_KV_DEBUG, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_DEBUG, logs[-50:])

_SIGN_API_CANDIDATES = [
    "/api/customer/user/login",
    "/api/customer/auth/login",
]


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


async def _fetch_action_hash(base_url: str) -> str | None:
    """从 Next.js 页面中提取签到 action hash"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient(timeout=15, verify=False, headers=headers) as cli:
            # 加载首页
            r = await cli.get(f"{base_url}/")
            if r.status_code != 200:
                return None
            html = r.text
            # 找所有 chunk URL
            chunk_urls = set()
            for m in re.finditer(r'(/_next/static/chunks/[^"\'\\s]+\.js)', html):
                chunk_urls.add(m.group(1))
            for m in re.finditer(r'(/_next/static/chunks/[^"\'\\s]+\.js)', html):
                chunk_urls.add(m.group(1))

            for chunk_rel in chunk_urls:
                chunk_url = f"{base_url}{chunk_rel}" if chunk_rel.startswith("/") else f"{base_url}/{chunk_rel}"
                try:
                    cr = await cli.get(chunk_url, timeout=15)
                    if cr.status_code != 200:
                        continue
                    text = cr.text
                    # 找 createServerReference("hash"
                    m = re.search(r'createServerReference\s*\(\s*["\']([0-9a-f]{40,})["\']', text)
                    if m:
                        return m.group(1)
                except Exception:
                    continue
            return None
    except Exception:
        return None


async def _login_get_token(base_url: str, username: str, password: str) -> tuple[str, str] | None:
    """用用户名密码登录，返回 (cookie_str, token)"""
    apis = ["/api/customer/user/login", "/api/customer/auth/login"]
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    for api in apis:
        try:
            async with httpx.AsyncClient(timeout=15, verify=False) as cli:
                r = await cli.post(f"{base_url}{api}", json={"username": username, "password": password}, headers=headers)
                if r.status_code == 200:
                    data = r.json()
                    token = data.get("data", {}).get("token") or data.get("token", "")
                    if token:
                        return f"token={token}", token
        except Exception:
            continue
    return None


async def _ensure_account_ready(account: dict) -> dict:
    """确保账号有有效cookie，必要时自动登录"""
    base_url = account.get("base_url", "https://hdhive.in").rstrip("/")
    cookie = account.get("cookie", "")
    username = account.get("username", "")
    password = account.get("password", "")

    # 已经有cookie，直接返回
    if cookie and "token" in cookie:
        return account

    # 有用户名密码，尝试登录
    if username and password:
        result = await _login_get_token(base_url, username, password)
        if result:
            cookie_str, token = result
            account["cookie"] = cookie_str
            return account

    return account


async def _do_sign(account: dict, action_hash: str) -> dict:
    """执行单账号签到"""
    base_url = account.get("base_url", "https://hdhive.in").rstrip("/")
    gamble = account.get("gamble", False)
    cookie_str = account.get("cookie", "")
    token = ""
    cookies = {}

    for item in cookie_str.split(";"):
        if "=" in item:
            k, v = item.strip().split("=", 1)
            cookies[k] = v
            if k == "token":
                token = v

    if not token:
        return {"success": False, "message": "未登录，请配置账号密码或 Cookie"}

    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    headers = {
        "User-Agent": ua,
        "Accept": "text/x-component",
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": base_url,
        "Referer": f"{base_url}/",
        "next-action": action_hash,
        "Authorization": f"Bearer {token}",
    }
    body = json.dumps([gamble])

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            resp = await cli.post(
                base_url,
                headers=headers,
                cookies=cookies,
                content=body,
            )
        text = resp.text
        # 解析响应
        result = _parse_rsc_result(text)
        if result is None:
            if resp.status_code == 200:
                return {"success": True, "message": "签到请求已发送"}
            return {"success": False, "message": f"HTTP {resp.status_code}"}

        payload = result.get("response") or result
        message = str(payload.get("message") or "")
        description = str(payload.get("description") or "")
        display = description or message or "未知结果"

        already = any(k in message + description for k in ("已经签到", "签到过", "明天再来"))
        success = bool(payload.get("success")) or already
        if already:
            display = "今日已签到"
        return {"success": success, "message": display}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _parse_rsc_result(text: str) -> dict | None:
    """解析 Next.js RSC 响应"""
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
        if "login" in str(obj):
            continue
        if "f" in obj and any(k in obj for k in ("error", "response", "success", "message")):
            return obj
    return None


async def setup(ctx):
    _log_debug(ctx, "插件加载完成")
    # 初始化定时签到
    async def _sign_tick():
        acc_json = ctx.config.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        if not accounts:
            return
        base_url = accounts[0].get("base_url", "https://hdhive.in").rstrip("/")
        # 获取 action hash
        action_hash = ctx.kv.get(_KV_HASH, "")
        if not action_hash:
            _log_debug(ctx, f"获取action hash: {base_url}")
            ctx.log.info("[影巢签到] 获取 action hash: %s", base_url)
            action_hash = await _fetch_action_hash(base_url)
            if action_hash:
                ctx.kv.set(_KV_HASH, action_hash)
                ctx.log.info("[影巢签到] action hash 获取成功: %s", action_hash[:20])
            else:
                ctx.log.warning("[影巢签到] 无法获取 action hash")
                return

        logs = []
        for i, acc in enumerate(accounts):
            name = acc.get("name", f"账号{i+1}")
            mode = "赌狗" if acc.get("gamble") else "普通"
            ctx.log.info("[影巢签到] %s(%s) 签到", name, mode)
            # 确保已登录
            acc = await _ensure_account_ready(acc)
            result = await _do_sign(acc, action_hash)
            status = "✅" if result["success"] else "❌"
            logs.append({"time": _now(), "name": name, "mode": mode, "status": status, "message": result["message"]})
            ctx.log.info("[影巢签到] %s: %s", name, result["message"])
            await asyncio.sleep(2)

        ctx.kv.set(_KV_LOGS, logs)

    sign_hour = int(ctx.config.get("sign_hour", 9) or 9)
    sign_minute = int(ctx.config.get("sign_minute", 0) or 0)
    ctx.schedule(_sign_tick, "cron", hour=sign_hour, minute=sign_minute, id="hdhive_sign")

    # 同步 accounts 配置到 KV
    acc_json = ctx.config.get("accounts", "[]")
    try:
        parsed = json.loads(acc_json) if isinstance(acc_json, str) else acc_json
        ctx.kv.set(_KV_ACCOUNTS, parsed if isinstance(parsed, list) else [])
    except Exception:
        pass

    async def _do_sign_all():
        """执行所有账号签到"""
        _log_debug(ctx, "开始签到")
        acc_json = ctx.config.get("accounts", "[]")
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            accounts = []
        if not accounts:
            _log_debug(ctx, "无账号配置")
            return {"ok": False, "message": "未配置账号"}
        _log_debug(ctx, f"账号数: {len(accounts)}")
        base_url = accounts[0].get("base_url", "https://hdhive.in").rstrip("/")
        action_hash = ctx.config.get("action_hash", "") or ctx.kv.get(_KV_HASH, "")
        if not action_hash:
            _log_debug(ctx, f"获取action hash: {base_url}")
            action_hash = await _fetch_action_hash(base_url)
            if action_hash:
                ctx.kv.set(_KV_HASH, action_hash)
                _log_debug(ctx, f"hash获取成功: {action_hash[:16]}...")
            else:
                _log_debug(ctx, "无法获取action hash，请在配置中手动填写")
                return {"ok": False, "message": "无法获取 action hash，请在配置中手动填写"}
        else:
            _log_debug(ctx, f"使用hash: {action_hash[:16]}...")
        for i, acc in enumerate(accounts):
            name = acc.get("name", f"账号{i+1}")
            mode = "赌狗" if acc.get("gamble") else "普通"
            acc = await _ensure_account_ready(acc)
            result = await _do_sign(acc, action_hash)
            status = "✅" if result["success"] else "❌"
            logs.append({"time": _now(), "name": name, "mode": mode, "status": status, "message": result["message"]})
            await asyncio.sleep(2)

        ctx.kv.set(_KV_LOGS, logs)
        return {"ok": True, "message": "\n".join(f"{l['status']} {l['name']}({l.get('mode','')}): {l['message']}" for l in logs)}

    @ctx.action("sign_now")
    async def _api_sign_now(req=None):
        return await _do_sign_all()

    @ctx.on_api("/sign_now", methods=["POST"])
    async def _api_sign_now_api(req):
        return await _do_sign_all()

    @ctx.action("refresh_hash")
    async def _api_refresh_hash(req=None):
        accounts = ctx.kv.get(_KV_ACCOUNTS, [])
        base_url = accounts[0].get("base_url", "https://hdhive.in") if accounts else "https://hdhive.in"
        h = await _fetch_action_hash(base_url)
        if h:
            ctx.kv.set(_KV_HASH, h)
            return {"ok": True, "message": f"Hash 已更新: {h[:16]}..."}
        return {"ok": False, "message": "获取失败"}

    @ctx.on_api("/get_accounts", methods=["GET"])
    async def _api_get_accounts(req):
        acc_json = ctx.config.get("accounts", "[]")
        accounts = []
        try:
            accounts = json.loads(acc_json) if isinstance(acc_json, str) else (acc_json if isinstance(acc_json, list) else [])
        except Exception:
            pass
        # 脱敏，不返回密码和完整cookie
        safe = []
        for a in accounts:
            s = dict(a)
            if s.get("password"):
                s["password"] = "******"
            if s.get("cookie"):
                c = s["cookie"]
                s["cookie"] = c[:20] + "..." if len(c) > 20 else c
            s["login_method"] = "cookie" if a.get("cookie") else "密码"
            safe.append(s)
        return {"accounts": safe}

    @ctx.on_api("/save_accounts", methods=["POST"])
    async def _api_save_accounts(req):
        try:
            data = await req.json()
        except Exception:
            data = req if isinstance(req, dict) else {}
        accounts = data.get("accounts", [])
        if not accounts:
            return {"ok": False, "message": "未收到账号数据"}
        ctx.log.info("[影巢签到] 保存 %d 个账号", len(accounts))
        # 尝试自动登录获取cookie
        for acc in accounts:
            if not acc.get("cookie") and acc.get("username") and acc.get("password"):
                result = await _login_get_token(
                    acc.get("base_url", "https://hdhive.in").rstrip("/"),
                    acc["username"], acc["password"]
                )
                if result:
                    acc["cookie"] = result[0]
        ctx.kv.set(_KV_ACCOUNTS, accounts)
        return {"ok": True, "message": f"已保存 {len(accounts)} 个账号"}

    @ctx.on_api("/get_logs", methods=["GET"])
    async def _api_get_logs(req):
        return {"logs": ctx.kv.get(_KV_LOGS, [])}

    @ctx.on_api("/get_debug_logs", methods=["GET"])
    async def _api_get_debug_logs(req):
        return {"logs": ctx.kv.get(_KV_DEBUG, [])}


async def teardown(ctx):
    pass