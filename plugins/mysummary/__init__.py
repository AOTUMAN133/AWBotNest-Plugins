# -*- coding: utf-8 -*-
# AWBotNest 插件：AI总结 (mysummary)

import re
import asyncio
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "AI总结",
    "id": "mysummary",
    "version": "1.0.1",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mysummary.svg",
    "author": "凹凸曼",
    "description": "群消息总结。发送 .sum [数量] 快速总结最近N条消息，支持定时总结任务。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "enable_summary": {
            "type": "boolean", "default": True, "label": "开启总结",
            "section": "基本", "help": "关闭后.sum命令不响应"
        },
    },
}

# ── Prompt ──
_SUM_PROMPT = (
    "你是 Telegram 群聊摘要助手。根据以下聊天记录，输出中文总结。\n"
    "每条消息末尾都有来源链接。每条摘要都必须附带来源链接。\n"
    "合并重复消息，忽略纯寒暄、表情、广告、机器人状态。\n"
    "总长度控制在 900-1600 字。\n\n"
    "固定输出：\n"
    "<b>📌 本次摘要</b>\n"
    "用 2-3 句话概括，末尾附来源链接。\n"
    "随后按实际内容选择栏目：\n"
    "<b>💬 主要话题</b>：日常交流、综合讨论\n"
    "<b>🧩 技术与项目</b>：技术方案、开发、排障\n"
    "<b>📰 资源分享</b>：外部链接、工具、新闻\n"
    "每个栏目使用 <blockquote expandable> 包裹。\n"
    "禁止使用 Markdown 语法。"
)


def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%Y-%m-%d %H:%M:%S")


def _parse_interval(s: str) -> str | None:
    s = s.strip().lower()
    parts = s.split()
    if len(parts) == 6:
        return s
    if len(parts) == 5:
        return f"0 {s}"
    m = re.match(r"^(\d+)(h|m)$", s)
    if m:
        val = int(m.group(1))
        if val <= 0:
            return None
        return f"0 0 */{val} * * *" if m.group(2) == "h" else f"0 */{val} * * * *"
    return None


def _parse_chat(input_str: str) -> str:
    s = input_str.strip()
    if re.match(r"^-?\d+$", s):
        return s
    m = re.search(r"t\.me/c/(\d+)", s)
    if m:
        return f"-100{m.group(1)}"
    m = re.search(r"t\.me/([a-zA-Z0-9_]+)", s)
    if m:
        return f"@{m.group(1)}"
    if s.startswith("@"):
        return s
    return s


def _build_link(chat_id: str, msg_id: int, username: str = "") -> str:
    if username:
        return f"https://t.me/{username}/{msg_id}"
    cid = chat_id.replace("-100", "").replace("-", "")
    return f"https://t.me/c/{cid}/{msg_id}"


async def _get_msgs(client, chat_id: str, count: int, time_range: int = 0) -> list:
    from pyrogram.raw.functions.messages import GetHistory
    peer = await client.resolve_peer(int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id)
    all_msgs = []
    offset = 0
    while len(all_msgs) < count:
        raw = await client.invoke(GetHistory(
            peer=peer, offset_id=offset, offset_date=0,
            add_offset=0, limit=min(count - len(all_msgs), 100),
            max_id=0, min_id=0, hash=0,
        ))
        msgs = [m for m in raw.messages if hasattr(m, "id") and hasattr(m, "message")]
        if not msgs:
            break
        for m in msgs:
            ts = getattr(m, "date", 0)
            if time_range and ts:
                msg_time = datetime.fromtimestamp(ts)
                if (datetime.now(TZ) - msg_time).total_seconds() > time_range * 3600:
                    continue
            all_msgs.append({"id": m.id, "text": m.message or "", "date": ts})
            if len(all_msgs) >= count:
                break
        offset = msgs[-1].id
        if len(msgs) < 100:
            break
    return all_msgs


async def _format_ai(chat_id: str, msgs: list, username: str = "") -> str:
    lines = []
    for m in msgs:
        link = _build_link(chat_id, m["id"], username)
        ds = _fmt_ts(m["date"]) if m.get("date") else ""
        lines.append(f"[{ds}] {m['text']}\n来源: {link}")
    return "\n---\n".join(lines)


async def _summarize(ctx, client, chat_id: str, count: int, time_range: int = 0) -> dict:
    """使用平台AI进行群消息总结"""
    if not ctx.ai.available:
        return {"success": False, "error": "平台AI未配置，请在系统设置中配置AI服务"}

    # 获取群组信息
    try:
        peer = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        entity = await client.get_chat(peer)
        username = getattr(entity, "username", "") or ""
        title = getattr(entity, "title", "") or chat_id
    except Exception:
        username = ""
        title = chat_id

    # 获取消息
    msgs = await _get_msgs(client, chat_id, count, time_range)
    if not msgs:
        return {"success": False, "error": "未找到消息"}

    formatted = await _format_ai(chat_id, msgs, username)
    prompt = _SUM_PROMPT

    # 调用平台AI
    try:
        result = await ctx.ai.chat(f"{prompt}\n\n{formatted}")
        # 清理思考标签
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r" thinking.*? response", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = result.strip()
        if not result:
            return {"success": False, "error": "AI未返回内容"}
        return {"success": True, "result": result, "title": title}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def setup(ctx):
    ctx.log.info("AI总结插件已加载")

    @ctx.on_message(ctx.filters.text)
    async def handler(client, message):
        if not ctx.config.get("enable_summary", True):
            return
        text = (message.text or "").strip()
        if not text.startswith(".sum"):
            return

        # 如果是群聊，用当前群；如果是私聊，尝试从参数解析
        cmd = text[len(".sum"):].strip()
        parts = cmd.split()
        if not parts:
            chat_id = str(message.chat.id)
            count = 50
        elif parts[0] == "add":
            # .sum add 群组 2h 100 - 添加定时总结
            if len(parts) < 3:
                help_text = (
                    "📊 <b>定时总结</b>\n\n"
                    "<code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                    "<code>.sum list</code> — 查看所有任务\n"
                    "<code>.sum run 1</code> — 立即执行任务\n"
                    "<code>.sum del 1</code> — 删除任务\n\n"
                    "<b>间隔格式</b>\n"
                    "简化: 2h, 30m\n"
                    "Cron: 0 0 9,15,21 * * *"
                )
                await message.edit(help_text)
                return
            target = _parse_chat(parts[1])
            interval = _parse_interval(parts[2])
            if not interval:
                await message.edit("❌ 间隔格式无效，用 2h 或 cron 表达式")
                return
            c = int(parts[3]) if len(parts) > 3 else 50
            tasks = ctx.kv.get("sum_tasks", [])
            tasks.append({"chat_id": target, "interval": interval, "count": c, "id": len(tasks) + 1})
            ctx.kv.set("sum_tasks", tasks)
            # 注册定时任务
            parts_cron = interval.split()
            if len(parts_cron) == 5:
                parts_cron = ["0"] + parts_cron
            try:
                ctx.schedule(lambda: _do_sum_task(ctx, client, target, c), "cron",
                            minute=parts_cron[0], hour=parts_cron[1],
                            day=parts_cron[2], month=parts_cron[3], day_of_week=parts_cron[4],
                            id=f"sum_task_{len(tasks)}")
            except Exception:
                pass
            await message.edit(f"✅ 已添加定时总结: {target} 每{parts[2]} 总结{c}条")
            return

        elif parts[0] == "list":
            tasks = ctx.kv.get("sum_tasks", [])
            if not tasks:
                await message.edit("📋 暂无定时总结任务")
                return
            lines = ["📋 <b>定时总结任务</b>\n"]
            for t in tasks:
                lines.append(f"<b>{t['id']}.</b> {t['chat_id']} 每{t['interval']} 总结{t['count']}条")
            await message.edit("\n".join(lines))
            return

        elif parts[0] == "run":
            if len(parts) < 2:
                await message.edit("❌ 用法: .sum run 1")
                return
            tasks = ctx.kv.get("sum_tasks", [])
            tid = int(parts[1])
            task = next((t for t in tasks if t["id"] == tid), None)
            if not task:
                await message.edit(f"❌ 未找到任务 {tid}")
                return
            await message.edit("⏳ 正在执行定时总结...")
            result = await _summarize(ctx, client, task["chat_id"], task["count"])
            if result["success"]:
                header = f"📊 定时总结\n{result['title']} · {_now()}\n\n"
                await client.send_message(message.chat.id, header + result["result"])
                await message.delete()
            else:
                await message.edit(f"❌ {result['error']}")
            return

        elif parts[0] == "del":
            if len(parts) < 2:
                await message.edit("❌ 用法: .sum del 1")
                return
            tasks = ctx.kv.get("sum_tasks", [])
            tid = int(parts[1])
            tasks = [t for t in tasks if t["id"] != tid]
            ctx.kv.set("sum_tasks", tasks)
            await message.edit(f"✅ 已删除任务 {tid}")
            return

        elif parts[0].isdigit():
            count = int(parts[0])
            chat_id = str(message.chat.id)
            await message.edit("⏳ 正在获取消息并总结...")
            result = await _summarize(ctx, client, chat_id, count)
            if result["success"]:
                header = f"📊 群组总结\n{result['title']} · {_now()}\n\n"
                await client.send_message(message.chat.id, header + result["result"])
                await message.delete()
            else:
                await message.edit(f"❌ {result['error']}")
            return

        else:
            help_text = (
                "📊 <b>群消息总结</b>\n\n"
                "<b>快速总结</b>\n"
                "<code>.sum 100</code> — 总结最近100条\n\n"
                "<b>定时任务</b>\n"
                "<code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                "<code>.sum list</code> — 查看任务\n"
                "<code>.sum run 1</code> — 立即执行\n"
                "<code>.sum del 1</code> — 删除任务\n\n"
                "<b>间隔格式</b>\n"
                "简化: 2h, 30m\n"
                "Cron: 0 0 9,15,21 * * *"
            )
            await message.edit(help_text)

    async def _do_sum_task(ctx, client, chat_id, count):
        result = await _summarize(ctx, client, chat_id, count)
        if result["success"]:
            apps = list(ctx.user_apps or [])
            if apps:
                header = f"📊 定时总结\n{result['title']} · {_now()}\n\n"
                await apps[0].send_message(chat_id, header + result["result"])

    ctx.log.info("AI总结已就绪")


async def teardown(ctx):
    ctx.log.info("AI总结已卸载")