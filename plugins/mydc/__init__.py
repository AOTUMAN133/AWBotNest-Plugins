# -*- coding: utf-8 -*-
# AWBotNest 插件：DC助手 (mydc)

import asyncio
import json
import httpx
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "DC助手",
    "id": "mydc",
    "version": "1.2.3",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mydc.svg?v=2",
    "author": "凹凸曼",
    "description": "配合 DockerCopilot 实现容器自动更新、清理、备份。",
    "scope": "user",
    "default_enabled": False,
    "render_mode": "vue",
    "config_schema": {
        "host": {
            "type": "string", "default": "http://192.168.1.33:13001", "label": "DockerCopilot 地址",
            "section": "连接", "help": "DockerCopilot 的访问地址，含端口"
        },
        "secret_key": {
            "type": "password", "default": "", "label": "Secret Key",
            "section": "连接", "help": "DockerCopilot 的 secretKey"
        },
        "auto_update_include": {
            "type": "text", "default": "", "label": "更新容器列表",
            "section": "容器选择", "help": "点下方「刷新容器列表」查看所有容器名，把要更新的填到这里，每行一个"
        },
        "auto_update_immediate": {
            "type": "text", "default": "", "label": "发现更新立即执行",
            "section": "容器选择", "help": "这些容器不等待定时，发现新版本立即更新。每行一个容器名"
        },
        "auto_update_cron": {
            "type": "string", "default": "0 4 * * *", "label": "定时更新 (cron)",
            "section": "定时", "help": "cron 表达式，默认每天凌晨4点"
        },
        "auto_update_notify": {
            "type": "boolean", "default": True, "label": "更新通知",
            "section": "定时"
        },
        "delete_images": {
            "type": "boolean", "default": True, "label": "更新后清理旧镜像",
            "section": "定时"
        },
        "backup_cron": {
            "type": "string", "default": "0 5 * * 0", "label": "备份定时 (cron)",
            "section": "备份", "help": "cron 表达式，默认每周日凌晨5点"
        },
        "backup_notify": {
            "type": "boolean", "default": True, "label": "备份通知",
            "section": "备份"
        },
        "_status": {
            "type": "info", "label": "运行状态", "section": "状态"
        },
        "list_containers": {
            "type": "action", "label": "📋 刷新容器列表", "section": "操作",
            "action": "list_containers"
        },
        "check_now": {
            "type": "action", "label": "🔍 检查可更新", "section": "操作",
            "action": "check_updatable"
        },
        "update_all": {
            "type": "action", "label": "▶ 更新全部", "section": "操作",
            "action": "update_all", "danger": True
        },
        "backup_now": {
            "type": "action", "label": "💾 立即备份", "section": "操作",
            "action": "backup_now"
        },
        "clean_images": {
            "type": "action", "label": "🧹 清理镜像", "section": "操作",
            "action": "clean_images", "danger": True
        },
    },
}

_KV_LOGS = "mydc_logs"


def _now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _log(ctx, msg: str):
    logs = ctx.kv.get(_KV_LOGS, [])
    logs.append({"t": _now(), "m": msg})
    ctx.kv.set(_KV_LOGS, logs[-50:])


async def _api_call(ctx, method: str, path: str, **kwargs) -> dict | None:
    host = ctx.config.get("host", "").rstrip("/")
    secret = ctx.config.get("secret_key", "")
    if not host or not secret:
        return None
    try:
        jwt_token = ctx.kv.get("mydc_jwt", "")
        if not jwt_token:
            async with httpx.AsyncClient(timeout=15, verify=False) as cli:
                ar = await cli.post(f"{host}/api/auth", data={"secretKey": secret})
                if ar.status_code == 200:
                    data = ar.json()
                    jwt_token = data.get("data", {}).get("jwt", "")
                    if jwt_token:
                        ctx.kv.set("mydc_jwt", jwt_token)
        if not jwt_token:
            return None
        headers = {"Authorization": f"Bearer {jwt_token}"}
        if kwargs.get("headers"):
            headers.update(kwargs.pop("headers"))
        async with httpx.AsyncClient(timeout=30, verify=False) as cli:
            url = f"{host}/api{path}"
            r = await cli.request(method, url, headers=headers, **kwargs)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 401:
                ctx.kv.set("mydc_jwt", "")
                return await _api_call(ctx, method, path, **kwargs)
            return None
    except Exception:
        return None


def _parse_list(raw: str) -> list[str]:
    names = []
    for line in (raw or "").replace("，", ",").split(","):
        line = line.strip()
        if line:
            names.append(line)
    return names


async def setup(ctx):
    ctx.log.info("DC助手插件已加载")

    @ctx.on_api("/containers", methods=["GET"])
    async def _api_containers(req):
        """获取容器列表"""
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取失败"}
        containers = data.get("data") or data.get("containers") or []
        include = ctx.kv.get("mydc_include", [])
        immediate = ctx.kv.get("mydc_immediate", [])
        result = []
        for c in containers:
            name = c.get("name", "?")
            result.append({
                "name": name,
                "status": c.get("status", ""),
                "image": c.get("usingImage", ""),
                "haveUpdate": c.get("haveUpdate", False),
                "selected": name in include,
                "immediate": name in immediate,
            })
        return {"ok": True, "containers": result}

    @ctx.on_api("/save_selection", methods=["POST"])
    async def _api_save(req):
        """保存容器选择"""
        body = req.json
        selected = body.get("selected", [])
        immediate = body.get("immediate", [])
        ctx.kv.set("mydc_include", selected)
        ctx.kv.set("mydc_immediate", immediate)
        _log(ctx, f"容器选择已保存: {len(selected)}个选中, {len(immediate)}个立即更新")
        return {"ok": True, "message": "已保存"}

    @ctx.on_api("/selection", methods=["GET"])
    async def _api_selection(req):
        """获取当前选择"""
        return {
            "selected": ctx.kv.get("mydc_include", []),
            "immediate": ctx.kv.get("mydc_immediate", []),
        }

    @ctx.action("list_containers")
    async def _list(req=None):
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取容器列表失败。请检查连接信息是否正确"}
        containers = data.get("data") or data.get("containers") or []
        include = _parse_list(ctx.config.get("auto_update_include", ""))
        msg = f"📋 共 {len(containers)} 个容器\n\n"
        for c in containers:
            name = c.get("name", "?")
            flag = " ✅" if name in include else ""
            upd = " 🔄" if c.get("haveUpdate") else ""
            msg += f"{name}{flag}{upd}\n"
        msg += "\n把要更新的容器名填到「更新容器列表」里"
        return {"ok": True, "message": msg}

    @ctx.action("check_updatable")
    async def _check(req=None):
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            ctx.update_config({"_status": "❌ 无法连接 DockerCopilot"})
            return {"ok": False, "message": "连接 DockerCopilot 失败"}
        containers = data.get("data") or data.get("containers") or []
        # 检查可更新
        include = ctx.kv.get("mydc_include", [])
        imm = ctx.kv.get("mydc_immediate", [])
        filtered = [c for c in containers if not include or c.get("name", "") in include]
        updatable = [c for c in filtered if c.get("haveUpdate") or c.get("updatable") or c.get("can_update")]
        has_imm = [c for c in updatable if c.get("name", "") in imm]
        has_sch = [c for c in updatable if c.get("name", "") not in imm]
        total = len(filtered)
        msg = f"可更新 {len(updatable)}/{total} 个"
        if has_imm:
            msg += f"\n⚡立即: {', '.join(c['name'] for c in has_imm)}"
        if has_sch:
            msg += f"\n⏰定时: {', '.join(c['name'] for c in has_sch)}"
        if not updatable:
            msg = "所有容器已是最新 ✅"
        ctx.update_config({"_status": msg})
        return {"ok": True, "message": msg}

    @ctx.action("update_all")
    async def _update(req=None):
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return {"ok": False, "message": "获取容器列表失败"}
        containers = data.get("data") or data.get("containers") or []
        include = _parse_list(ctx.config.get("auto_update_include", ""))
        filtered = [c for c in containers if not include or c.get("name", "") in include]
        updatable = [c for c in filtered if c.get("haveUpdate") or c.get("updatable") or c.get("can_update")]
        if not updatable:
            return {"ok": True, "message": "没有需要更新的容器"}
        updated = 0
        for c in updatable:
            cid = c.get("id") or c.get("containerId") or c.get("name")
            if not cid:
                continue
            r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", ""), "containerName": c.get("name", "")})
            if r:
                updated += 1
            await asyncio.sleep(2)
        if ctx.config.get("delete_images", True) and updated > 0:
            await _clean_images(ctx)
        msg = f"更新完成: {updated}/{len(updatable)} 个容器"
        if ctx.config.get("auto_update_notify", True):
            await ctx.notify(f"🔄 {msg}")
        return {"ok": True, "message": msg}

    @ctx.action("backup_now")
    async def _backup(req=None):
        r = await _api_call(ctx, "POST", "/container/backup")
        if r:
            if ctx.config.get("backup_notify", True):
                await ctx.notify("💾 Docker 容器配置备份完成")
            return {"ok": True, "message": "备份完成 ✅"}
        return {"ok": False, "message": "备份失败"}

    @ctx.action("clean_images")
    async def _clean(req=None):
        return await _clean_images(ctx, notify=True)

    async def _clean_images(ctx, notify=False):
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
        if notify:
            return {"ok": True, "message": msg}
        return None

    # 定时任务：每分钟检查，立即更新立即执行，定时更新按cron
    async def _auto_tick():
        if not ctx.config.get("secret_key"):
            return
        data = await _api_call(ctx, "GET", "/containers")
        if not data:
            return
        containers = data.get("data") or data.get("containers") or []
        include = ctx.kv.get("mydc_include", [])
        imm = ctx.kv.get("mydc_immediate", [])
        filtered = [c for c in containers if not include or c.get("name", "") in include]

        # 立即更新：每分钟检查，发现可更新容器就执行
        imm_updated = 0
        for c in filtered:
            if c.get("name", "") in imm and (c.get("haveUpdate") or c.get("updatable") or c.get("can_update")):
                cid = c.get("id") or c.get("containerId") or c.get("name")
                if cid:
                    r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", ""), "containerName": c.get("name", "")})
                    if r:
                        imm_updated += 1
                        ctx.log.info(f"立即更新: {c.get('name', cid)}")
                    await asyncio.sleep(2)
        if imm_updated > 0 and ctx.config.get("auto_update_notify", True):
            await ctx.notify(f"🔄 立即更新: {imm_updated} 个容器")

        # 定时更新：只在cron时间点执行
        now = datetime.now(TZ)
        cron = ctx.config.get("auto_update_cron", "0 4 * * *")
        parts = cron.split()
        if len(parts) == 5:
            try:
                if int(parts[1]) == now.hour and int(parts[0]) == now.minute:
                    scheduled = [c for c in filtered if c.get("name", "") not in imm and (c.get("haveUpdate") or c.get("updatable") or c.get("can_update"))]
                    if not scheduled:
                        return
                    updated = 0
                    for c in scheduled:
                        cid = c.get("id") or c.get("containerId") or c.get("name")
                        if cid:
                            r = await _api_call(ctx, "POST", f"/container/{cid}/update", data={"imageNameAndTag": c.get("usingImage", ""), "containerName": c.get("name", "")})
                            if r:
                                updated += 1
                            await asyncio.sleep(2)
                    if ctx.config.get("delete_images", True) and updated > 0:
                        await _clean_images(ctx)
                    if ctx.config.get("auto_update_notify", True):
                        await ctx.notify(f"🔄 定时更新: {updated} 个容器")
            except Exception:
                pass

    async def _backup_tick():
        r = await _api_call(ctx, "POST", "/container/backup")
        if r and ctx.config.get("backup_notify", True):
            await ctx.notify("💾 Docker 容器配置定时备份完成")

    # 注册定时：只有配置了连接信息才注册
    if ctx.config.get("secret_key"):
        ctx.schedule(_auto_tick, "interval", minutes=1, id="DC助手-自动更新")
        ctx.log.info("DC助手-自动更新 已注册")

        bc = ctx.config.get("backup_cron", "0 5 * * 0")
        parts = bc.split()
        if len(parts) == 5:
            try:
                ctx.schedule(_backup_tick, "cron", minute=parts[0], hour=parts[1],
                            day=parts[2], month=parts[3], day_of_week=parts[4], id="DC助手-自动备份")
            except Exception:
                ctx.schedule(_backup_tick, "cron", hour=5, minute=0, day_of_week="sun", id="DC助手-自动备份")
        else:
            ctx.schedule(_backup_tick, "cron", hour=5, minute=0, day_of_week="sun", id="DC助手-自动备份")
        ctx.log.info("DC助手-自动备份 已注册")
    else:
        ctx.log.info("DC助手未配置连接信息，定时任务未注册")

    ctx.log.info("DC助手已就绪")


async def teardown(ctx):
    ctx.log.info("DC助手已卸载")