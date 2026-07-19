# -*- coding: utf-8 -*-
# AWBotNest 插件：历史消息转发 (myforward)

import asyncio
import re
from datetime import datetime, timezone, timedelta

__plugin__ = {
    "name": "历史消息转发",
    "id": "myforward",
    "version": "0.1.3",
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
            "type": "number", "default": 200, "label": "每批条数",
            "section": "速度控制", "min": 50, "max": 1000, "help": "每次从API拉取多少条，越大越快但占用越高。默认200", "order": 4
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
        batch = int(cfg.get("batch_size", 200) or 200)
        last_id = int(ctx.kv.get("myforward_last_id", 0) or 0)
        total = int(ctx.kv.get("myforward_total", 0) or 0)

        ctx.log.info("[转发] 开始: 来源%s → 目标%s, 从ID=%s起, 每批%s条, 间隔%s秒",
                      src, dst, last_id or "最旧", batch, delay)

        # 从最新消息往前翻，边翻边转
        forward_queue = []
        offset = 0
        reached_end = False

        while not reached_end:
            if ctx.kv.get("myforward_stop", False):
                ctx.log.info("[转发] 收到停止信号")
                break

            # 拉一批
            chunk = []
            async for m in client.get_chat_history(src, limit=batch, offset_id=offset):
                chunk.append(m)
            if not chunk:
                break

            # 如果是首次，或者没有 last_id，收集到最旧的消息
            if not last_id:
                forward_queue = chunk + forward_queue  # 新拉的在前面，拼到前面
            else:
                new_msgs = [m for m in chunk if m.id > last_id]
                forward_queue = new_msgs + forward_queue
                if chunk[-1].id <= last_id:
                    reached_end = True

            offset = chunk[-1].id
            ctx.log.info("[转发] 已缓存%s条待转发", len(forward_queue))

            if len(chunk) < batch:
                reached_end = True  # 到底了

            # 每收集到一批，转一批（从队列头部取，保证顺序）
            while forward_queue:
                msg = forward_queue.pop(0)
                if ctx.kv.get("myforward_stop", False):
                    break
                try:
                    await msg.forward(dst)
                    total += 1
                    last_id = msg.id
                except Exception as e:
                    ctx.log.warning("[转发] 消息%s转发失败: %r", msg.id, e)
                    last_id = msg.id
                await asyncio.sleep(delay)
                # 每10条存一次进度
                if total % 10 == 0:
                    ctx.kv.set("myforward_last_id", last_id)
                    ctx.kv.set("myforward_total", total)

        # 把队列里剩余的转完
        while forward_queue:
            msg = forward_queue.pop(0)
            if ctx.kv.get("myforward_stop", False):
                break
            try:
                await msg.forward(dst)
                total += 1
                last_id = msg.id
            except Exception as e:
                ctx.log.warning("[转发] 消息%s转发失败: %r", msg.id, e)
                last_id = msg.id
            await asyncio.sleep(delay)
            if total % 10 == 0:
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