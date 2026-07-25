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
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "配合 DockerCopilot 实现容器自动更新、清理、备份。",
    "scope": "user",
    "default_enabled": False,
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
    _log(ctx, "DC助手插件已加载")

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
        updatable = [c for c in containers if c.get("updatable") or c.get("can_update")]
        ctx.update_config({"_status": f"可更新: {len(updatable)}/{len(containers)} 个容器"})
        if updatable:
            names = [c.get("name", c.get("id", "?"))[:20] for c in updatable]
            _log(ctx, f"可更新容器: {', '.join(names)}")
            return {"ok": True, "message": f"可更新 {len(updatable)} 个容器: {', '.join(names)}"}
        else:
            _log(ctx, "所有容器已是最新")
            return {"ok": True, "message": "所有容器已是最新 ✅"}

    @ctx.action("update_all")
    async def _update_all(req=None):
        _log(ctx, "开始更新全部容器...")
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取容器列表失败"}
        containers = data.get("data") or data.get("containers") or []
        updatable = [c for c in containers if c.get("updatable") or c.get("can_update")]
        if not updatable:
            return {"ok": True, "message": "没有需要更新的容器"}
        updated = 0
        for c in updatable:
            cid = c.get("id") or c.get("containerId") or c.get("name")
            if not cid:
                continue
            r = await _api_call(ctx, "POST", f"/container/{cid}/update")
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
        updatable = [c for c in containers if c.get("updatable") or c.get("can_update")]
        if not updatable:
            _log(ctx, "定时检查: 无容器需要更新")
            return
        updated = 0
        for c in updatable:
            cid = c.get("id") or c.get("containerId") or c.get("name")
            if not cid:
                continue
            r = await _api_call(ctx, "POST", f"/container/{cid}/update")
            if r:
                updated += 1
            await asyncio.sleep(2)
        if ctx.config.get("delete_images", True) and updated > 0:
            await _clean_images(ctx)
        msg = f"定时更新完成: {updated}/{len(updatable)} 个容器"
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