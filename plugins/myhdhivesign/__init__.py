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
    "version": "2.1.3",
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
    logs = ctx.kv.get(_KV_DEBUG, [])
    logs.append({"t": datetime.now(TZ).strftime("%H:%M:%S"), "m": msg})
    ctx.kv.set(_KV_DEBUG, logs[-50:])


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


async def _fetch_action_hash(base_url: str) -> str | None:
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
                        return m.group(1)
            except Exception:
                pass
            return None
    except Exception:
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
    """执行签到"""
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
            resp = await cli.post(base_url, headers=headers, cookies=cookies, content=body)
        text = resp.text
        # 解析响应
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
                return {"success": False, "message": "Cookie 失效，请重新登录"}
            if "f" in obj and any(k in obj for k in ("error", "response", "success", "message")):
                payload = obj.get("response") or obj
                msg = str(payload.get("message") or payload.get("description") or "")
                already = any(k in msg for k in ("已经签到", "签到过", "明天再来"))
                if already:
                    return {"success": True, "message": "今日已签到"}
                if bool(payload.get("success")):
                    return {"success": True, "message": msg or "签到成功"}
                return {"success": False, "message": msg or "签到失败"}
        if resp.status_code == 200:
            return {"success": True, "message": "签到请求已发送"}
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
                _log_debug(ctx, f"{name}: 尝试自动登录到 {base_url}")
                cookie = await _login_get_token(base_url, username, password)
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
            logs.append({"time": _now(), "name": name, "mode": mode, "status": status, "message": result["message"]})
            _log_debug(ctx, f"{name}: {result['message']}")
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