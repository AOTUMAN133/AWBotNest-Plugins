# -*- coding: utf-8 -*-
# AWBotNest 插件：历史消息转发 (myforward)

import asyncio
import re
from datetime import datetime, timezone, timedelta

__plugin__ = {
    "name": "历史消息转发",
    "id": "myforward",
    "version": "0.1.2",
    "author": "凹凸曼",
    "description": "将指定频道的历史消息，从最早到最新，按顺序转发到目标频道，带速度控制。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "source_chat": {
            "type": "number", "default": 0, "label": "来源频道ID",
            "section": "转发", "help": "从哪个频道读取历史消息", "order": 1
        },
        "target_chat": {
            "type": "number", "default": 0, "label": "目标频道/群ID",
            "section": "转发", "help": "转发到哪里", "order": 2
        },
        "delay": {
            "type": "number", "default": 3, "label": "间隔(秒)",
            "section": "速度控制", "min": 1, "max": 60, "help": "每条消息间的间隔秒数", "order": 3
        },
        "batch_size": {
            "type": "number", "default": 50, "label": "每批条数",
            "section": "速度控制", "min": 10, "max": 500, "help": "每次从API拉取多少条，越大越快但占用越高", "order": 4
        },
        "_status": {
            "type": "info", "label": "状态",
            "section": "状态"
        },
        "start_forward": {
            "type": "action", "label": "▶ 开始转发",
            "section": "状态", "action": "start_forward", "danger": True
        },
        "stop_forward": {
            "type": "action", "label": "⏹ 停止转发",
            "section": "状态", "action": "stop_forward", "danger": True
        },
        "reset_forward": {
            "type": "action", "label": "🔄 重置进度",
            "section": "状态", "action": "reset_forward", "danger": True
        },
    },
}

TZ_SH = timezone(timedelta(hours=8))

def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"

async def setup(ctx):
    ctx.update_config({"_status": "就绪"})

    _running = False
    _stop_flag = False

    @ctx.action("start_forward")
    async def _start(req=None):
        nonlocal _running, _stop_flag
        if _running:
            return {"ok": False, "message": "转发进行中，请先停止"}
        cfg = ctx.config
        src = int(cfg.get("source_chat", 0) or 0)
        dst = int(cfg.get("target_chat", 0) or 0)
        if not src:
            return {"ok": False, "message": "未设置来源频道"}
        if not dst:
            return {"ok": False, "message": "未设置目标频道"}
        _stop_flag = False
        _running = True
        ctx.update_config({"_status": "转发中…"})
        # 在后台运行
        asyncio.create_task(_do_forward(ctx, src, dst))
        return {"ok": True, "message": "开始转发"}

    @ctx.action("stop_forward")
    async def _stop(req=None):
        nonlocal _stop_flag, _running
        _stop_flag = True
        _running = False
        ctx.kv.set("myforward_stop", True)
        ctx.update_config({"_status": "已停止"})
        return {"ok": True, "message": "已停止"}

    @ctx.action("reset_forward")
    async def _reset(req=None):
        nonlocal _stop_flag, _running
        _stop_flag = True
        _running = False
        ctx.kv.set("myforward_stop", True)
        ctx.kv.set("myforward_last_id", 0)
        ctx.kv.set("myforward_total", 0)
        ctx.update_config({"_status": "已重置"})
        return {"ok": True, "message": "进度已重置"}

    # 状态推送
    async def status_pusher():
        last_id = int(ctx.kv.get("myforward_last_id", 0) or 0)
        total = int(ctx.kv.get("myforward_total", 0) or 0)
        if _running:
            ctx.update_config({"_status": f"转发中… 已转发{total}条，最后消息ID={last_id}"})
        else:
            ctx.update_config({"_status": f"已转发{total}条，最后消息ID={last_id}"})

    ctx.schedule(status_pusher, "interval", seconds=10, id="myforward_status")


async def _do_forward(ctx, src, dst):
    """执行转发任务"""
    try:
        apps = list(ctx.user_apps or [])
        if not apps:
            ctx.log.error("[转发] 没有可用用户账号")
            ctx.update_config({"_status": "失败：无可用账号"})
            return
        client = apps[0]

        cfg = ctx.config
        delay = int(cfg.get("delay", 3) or 3)
        batch = int(cfg.get("batch_size", 50) or 50)
        last_id = int(ctx.kv.get("myforward_last_id", 0) or 0)
        total = int(ctx.kv.get("myforward_total", 0) or 0)

        ctx.log.info("[转发] 开始: 来源%s → 目标%s, 从ID=%s起, 每批%s条, 间隔%s秒",
                      src, dst, last_id or "最旧", batch, delay)

        # 如果没有记录 last_id，先找到最旧消息
        if not last_id:
            ctx.log.info("[转发] 无记录，获取最旧消息…")
            all_msgs = []
            offset = 0
            while True:
                chunk = []
                async for m in client.get_chat_history(src, limit=batch, offset_id=offset):
                    chunk.append(m)
                if not chunk:
                    break
                all_msgs.extend(chunk)
                offset = chunk[-1].id
                ctx.log.info("[转发] 已收集%s条消息…", len(all_msgs))
                if len(chunk) < batch:
                    break
            all_msgs.reverse()
            ctx.log.info("[转发] 共收集%s条消息，开始转发", len(all_msgs))
        else:
            ctx.log.info("[转发] 继续转发，从ID=%s之后", last_id)
            all_msgs = []
            offset = 0
            while True:
                chunk = []
                async for m in client.get_chat_history(src, limit=batch, offset_id=offset):
                    chunk.append(m)
                if not chunk:
                    break
                new_msgs = [m for m in chunk if m.id > last_id]
                all_msgs.extend(new_msgs)
                oldest = chunk[-1]
                if oldest.id <= last_id:
                    break
                offset = oldest.id
                ctx.log.info("[转发] 已收集%s条新消息…", len(all_msgs))
                if len(chunk) < batch:
                    break
            all_msgs.sort(key=lambda m: m.id)

        # 开始转发
        ctx.log.info("[转发] 开始转发%s条", len(all_msgs))
        forwarded = 0
        for msg in all_msgs:
            if ctx.kv.get("myforward_stop", False):
                ctx.log.info("[转发] 收到停止信号")
                break
            try:
                await msg.forward(dst)
                forwarded += 1
                total += 1
                last_id = msg.id
            except Exception as e:
                ctx.log.warning("[转发] 消息%s转发失败: %r", msg.id, e)
                last_id = msg.id
            await asyncio.sleep(delay)
            # 每10条保存一次进度
            if forwarded % 10 == 0:
                ctx.kv.set("myforward_last_id", last_id)
                ctx.kv.set("myforward_total", total)

        ctx.kv.set("myforward_last_id", last_id)
        ctx.kv.set("myforward_total", total)
        ctx.update_config({"_status": f"完成: 共转发{total}条"})
        ctx.log.info("[转发] ✅ 完成, 共转发%s条", total)

    except Exception as e:
        ctx.log.error("[转发] 异常: %r", e)
        ctx.update_config({"_status": f"异常: {e}"})


async def teardown(ctx):
    pass