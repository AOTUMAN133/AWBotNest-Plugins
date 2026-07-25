# -*- coding: utf-8 -*-
# AWBotNest 插件：DC助手 (mydc)

import asyncio
import json
import time
import httpx
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "DC助手",
    "id": "mydc",
    "version": "1.1.0",
    "author": "凹凸曼",
    "description": "配合 DockerCopilot 实现容器自动更新、清理、备份。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
    "config_schema": {
        "host": {
            "type": "string", "default": "http://192.168.1.33:12712", "label": "DockerCopilot 地址",
            "section": "连接", "help": "DockerCopilot 的访问地址，含端口"
        },
        "secret_key": {
            "type": "password", "default": "", "label": "Secret Key",
            "section": "连接", "help": "DockerCopilot 的 secretKey"
        },
        "auto_update_cron": {
            "type": "string", "default": "0 4 * * *", "label": "自动更新定时",
            "section": "自动更新", "help": "cron 表达式，默认每天凌晨4点"
        },
        "auto_update_include": {
            "type": "text", "default": "", "label": "更新容器列表",
            "section": "自动更新", "help": "留空=更新所有容器。填写容器名，每行一个，只更新这些"
        },
        "auto_update_immediate": {
            "type": "text", "default": "", "label": "发现更新立即执行",
            "section": "自动更新", "help": "这些容器发现有新版本时不等待定时，立即更新。每行一个容器名"
        },
        "auto_update_notify": {
            "type": "boolean", "default": True, "label": "更新通知",
            "section": "自动更新"
        },
        "delete_images": {
            "type": "boolean", "default": True, "label": "更新后清理旧镜像",
            "section": "自动更新"
        },
        "backup_cron": {
            "type": "string", "default": "0 5 * * 0", "label": "自动备份定时",
            "section": "备份", "help": "cron 表达式，默认每周日凌晨5点"
        },
        "backup_notify": {
            "type": "boolean", "default": True, "label": "备份通知",
            "section": "备份"
        },
        "_status": {
            "type": "info", "label": "运行状态", "section": "状态"
        },
        "check_now": {
            "type": "action", "label": "🔍 检查可更新容器", "section": "操作",
            "action": "check_updatable"
        },
        "list_all": {
            "type": "action", "label": "📋 列出所有容器", "section": "操作",
            "action": "list_containers"
        },
        "update_all": {
            "type": "action", "label": "▶ 更新全部容器", "section": "操作",
            "action": "update_all", "danger": True
        },
        "backup_now": {
            "type": "action", "label": "💾 立即备份", "section": "操作",
            "action": "backup_now"
        },
        "clean_images": {
            "type": "action", "label": "🧹 清理未使用镜像", "section": "操作",
            "action": "clean_images", "danger": True
        },
    },
}

_KV_STATUS = "mydc_status"
_KV_LOGS = "mydc_logs"


def _now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _log(ctx, msg: str):
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": _now(), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-50:])


def _parse_container_list(raw: str) -> list[str]:
    """解析容器名列表（每行一个，逗号分隔也行）"""
    names = []
    for line in (raw or "").replace("，", ",").split(","):
        line = line.strip()
        if line:
            names.append(line)
    return names


def _filter_containers(containers: list, include_list: list[str]) -> list:
    """根据include列表过滤容器"""
    if not include_list:
        return containers
    return [c for c in containers if c.get("name", "") in include_list]


async def _api_call(ctx, method: str, path: str, **kwargs) -> dict | None:
    """调用 DockerCopilot API（JWT 认证）"""
    host = ctx.config.get("host", "").rstrip("/")
    secret = ctx.config.get("secret_key", "")
    if not host or not secret:
        return None
    try:
        # 获取 JWT token
        jwt_token = ctx.kv.get("mydc_jwt", "")
        if not jwt_token:
            async with httpx.AsyncClient(timeout=15, verify=False) as cli:
                ar = await cli.post(f"{host}/api/auth", data={"secretKey": secret})
                if ar.status_code == 200:
                    data = ar.json()
                    jwt_token = data.get("data", {}).get("jwt", "")
                    if jwt_token:
                        ctx.kv.set("mydc_jwt", jwt_token)
                        _log(ctx, "JWT token 获取成功")
        if not jwt_token:
            _log(ctx, "获取 JWT token 失败")
            return None
        headers = {"Authorization": f"Bearer {jwt_token}"}
        if kwargs.get("headers"):
            headers.update(kwargs.pop("headers"))
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            url = f"{host}/api{path}"
            r = await cli.request(method, url, headers=headers, **kwargs)
            if r.status_code == 200:
                return r.json()
            # token 过期，重新获取
            if r.status_code == 401:
                ctx.kv.set("mydc_jwt", "")
                return await _api_call(ctx, method, path, **kwargs)
            _log(ctx, f"API错误 {method} {path}: {r.status_code}")
            return None
    except Exception as e:
        _log(ctx, f"请求失败 {path}: {e}")
        return None


async def setup(ctx):
    ctx.log.info("DC助手插件已加载")

    @ctx.action("check_updatable")
    async def _check(req=None):
        host = ctx.config.get("host", "").rstrip("/")
        secret = ctx.config.get("secret_key", "")
        if not host or not secret:
            ctx.update_config({"_status": "❌ 未配置连接信息"})
            return {"ok": False, "message": "请先配置 DockerCopilot 地址和 Secret Key"}
        _log(ctx, "检查可更新容器...")
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            ctx.update_config({"_status": "❌ 无法连接 DockerCopilot"})
            return {"ok": False, "message": "连接 DockerCopilot 失败"}
        containers = data.get("data") or data.get("containers") or []
        include_list = _parse_container_list(ctx.config.get("auto_update_include", ""))
        imm_list = _parse_container_list(ctx.config.get("auto_update_immediate", ""))
        filtered = _filter_containers(containers, include_list)
        updatable = [c for c in filtered if c.get("haveUpdate") or c.get("updatable") or c.get("can_update")]
        immediate = [c for c in updatable if c.get("name", "") in imm_list]
        scheduled = [c for c in updatable if c.get("name", "") not in imm_list]
        ctx.update_config({"_status": f"可更新: {len(updatable)}/{len(filtered)} 个容器"})
        msg_parts = []
        if updatable:
            if immediate:
                names = [c.get("name", "?")[:20] for c in immediate]
                msg_parts.append(f"立即更新: {', '.join(names)}")
            if scheduled:
                names = [c.get("name", "?")[:20] for c in scheduled]
                msg_parts.append(f"等待定时: {', '.join(names)}")
            _log(ctx, "; ".join(msg_parts))
            return {"ok": True, "message": "; ".join(msg_parts) if msg_parts else "无更新"}
        else:
            _log(ctx, "所有容器已是最新")
            return {"ok": True, "message": "所有容器已是最新 ✅"}

    @ctx.action("list_containers")
    async def _list_all(req=None):
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取容器列表失败"}
        containers = data.get("data") or data.get("containers") or []
        include_list = _parse_container_list(ctx.config.get("auto_update_include", ""))
        msg = f"📋 共 {len(containers)} 个容器"
        for c in containers:
            name = c.get("name", "?")
            flag = " ✅" if name in include_list else ""
            upd = " 🔄" if c.get("haveUpdate") else ""
            msg += f"\n{name}{flag}{upd}"
        return {"ok": True, "message": msg}

    @ctx.action("update_all")
    async def _update_all(req=None):
        _log(ctx, "开始更新全部容器...")
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取容器列表失败"}
        containers = data.get("data") or data.get("containers") or []
        updatable = [c for c in containers if c.get("haveUpdate") or c.get("updatable") or c.get("can_update")]
        if not updatable:
            return {"ok": True, "message": "没有需要更新的容器"}
        updated = 0
        for c in updatable:
            cid = c.get("id") or c.get("containerId") or c.get("name")
            if not cid:
                continue
            r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", "")})
            if r:
                updated += 1
                _log(ctx, f"更新完成: {c.get('name', cid)}")
            await asyncio.sleep(2)
        # 清理旧镜像
        if ctx.config.get("delete_images", True) and updated > 0:
            await _clean_images(ctx)
        msg = f"更新完成: {updated}/{len(updatable)} 个容器"
        ctx.update_config({"_status": f"✅ {msg}"})
        if ctx.config.get("auto_update_notify", True):
            await ctx.notify(f"🔄 {msg}")
        return {"ok": True, "message": msg}

    @ctx.action("backup_now")
    async def _backup(req=None):
        _log(ctx, "开始备份容器配置...")
        r = await _api_call(ctx, "POST", "/container/backup")
        if r:
            _log(ctx, "备份完成")
            if ctx.config.get("backup_notify", True):
                await ctx.notify("💾 Docker 容器配置备份完成")
            return {"ok": True, "message": "备份完成 ✅"}
        return {"ok": False, "message": "备份失败"}

    @ctx.action("clean_images")
    async def _clean(req=None):
        return await _clean_images(ctx, notify=True)

    async def _clean_images(ctx, notify=False):
        _log(ctx, "清理未使用镜像...")
        data = await _api_call(ctx, "GET", "/images")
        if not data:
            return {"ok": False, "message": "获取镜像列表失败"}
        images = data.get("data") or data.get("images") or []
        removed = 0
        for img in images:
            tag = img.get("tag", "") or ""
            if not tag or tag == "<none>:<none>" or ":" not in tag:
                sha = img.get("id") or img.get("sha")
                if sha:
                    r = await _api_call(ctx, "DELETE", f"/image/{sha}?force=false")
                    if r:
                        removed += 1
        msg = f"已清理 {removed} 个未使用镜像"
        _log(ctx, msg)
        if notify:
            return {"ok": True, "message": msg}
        return None

    # 定时自动更新
    async def _auto_update_tick():
        if not ctx.config.get("secret_key"):
            return
        _log(ctx, "定时自动更新开始...")
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return
        containers = data.get("data") or data.get("containers") or []
        include_list = _parse_container_list(ctx.config.get("auto_update_include", ""))
        imm_list = _parse_container_list(ctx.config.get("auto_update_immediate", ""))
        filtered = _filter_containers(containers, include_list)
        # 立即更新的：发现可更新就马上更新
        immediate_containers = [c for c in filtered if c.get("name", "") in imm_list and (c.get("haveUpdate") or c.get("updatable") or c.get("can_update"))]
        if immediate_containers:
            for c in immediate_containers:
                cid = c.get("id") or c.get("containerId") or c.get("name")
                if not cid:
                    continue
                r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", "")})
                if r:
                    _log(ctx, f"立即更新完成: {c.get('name', cid)}")
                await asyncio.sleep(2)
        # 定时更新的：按cron调度
        now = datetime.now(TZ)
        cron = ctx.config.get("auto_update_cron", "0 4 * * *")
        parts = cron.split()
        if len(parts) == 5:
            cron_hour = int(parts[1])
            cron_minute = int(parts[0])
            if now.hour == cron_hour and now.minute == cron_minute:
                scheduled = [c for c in filtered if c.get("name", "") not in imm_list and (c.get("haveUpdate") or c.get("updatable") or c.get("can_update"))]
                if not scheduled:
                    _log(ctx, "定时检查: 无容器需要更新")
                    return
                updated = 0
                for c in scheduled:
                    cid = c.get("id") or c.get("containerId") or c.get("name")
                    if not cid:
                        continue
                    r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", "")})
                    if r:
                        updated += 1
                    await asyncio.sleep(2)
                if ctx.config.get("delete_images", True) and updated > 0:
                    await _clean_images(ctx)
                msg = f"定时更新完成: {updated}/{len(scheduled)} 个容器"
                _log(ctx, msg)
                if ctx.config.get("auto_update_notify", True):
                    await ctx.notify(f"🔄 {msg}")

    # 定时备份
    async def _backup_tick():
        if not ctx.config.get("secret_key"):
            return
        _log(ctx, "定时备份开始...")
        r = await _api_call(ctx, "POST", "/container/backup")
        if r and ctx.config.get("backup_notify", True):
            await ctx.notify("💾 Docker 容器配置定时备份完成")

    # 注册定时任务
    auto_cron = ctx.config.get("auto_update_cron", "0 4 * * *")
    parts = auto_cron.split()
    if len(parts) == 5:
        try:
            ctx.schedule(_auto_update_tick, "cron",
                        minute=parts[0], hour=parts[1],
                        day=parts[2], month=parts[3], day_of_week=parts[4],
                        id="DC助手-自动更新")
        except Exception:
            ctx.schedule(_auto_update_tick, "cron", hour=4, minute=0, id="DC助手-自动更新")
    else:
        ctx.schedule(_auto_update_tick, "cron", hour=4, minute=0, id="DC助手-自动更新")

    backup_cron = ctx.config.get("backup_cron", "0 5 * * 0")
    parts = backup_cron.split()
    if len(parts) == 5:
        try:
            ctx.schedule(_backup_tick, "cron",
                        minute=parts[0], hour=parts[1],
                        day=parts[2], month=parts[3], day_of_week=parts[4],
                        id="DC助手-自动备份")
        except Exception:
            ctx.schedule(_backup_tick, "cron", hour=5, minute=0, day_of_week="sun", id="DC助手-自动备份")
    else:
        ctx.schedule(_backup_tick, "cron", hour=5, minute=0, day_of_week="sun", id="DC助手-自动备份")

    _log(ctx, "DC助手已就绪")
    ctx.update_config({"_status": "✅ 运行中"})


async def teardown(ctx):
    _log(ctx, "DC助手已卸载")