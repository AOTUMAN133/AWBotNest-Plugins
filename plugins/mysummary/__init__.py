# -*- coding: utf-8 -*-
# AWBotNest 插件：AI总结 (mysummary) v2.0
# 消息存储 + 总结 + 问答 + 搜索

import os
import re
import sqlite3
import asyncio
import threading
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))
DB_PATH = os.path.join(os.path.dirname(__file__), "mysummary.db")
_local = threading.local()

def _get_db():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA busy_timeout=5000")
        _init_db(_local.conn)
    return _local.conn

def _init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            group_id TEXT NOT NULL,
            group_name TEXT DEFAULT '',
            user_name TEXT DEFAULT '',
            content TEXT DEFAULT '',
            timestamp INTEGER DEFAULT 0,
            message_id INTEGER DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_group ON messages(group_id, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp)")
    conn.commit()

def _store_msg(group_id: str, group_name: str, user_name: str, content: str, msg_id: int, ts: int):
    if not content.strip():
        return
    try:
        db = _get_db()
        uid = f"{group_id}_{msg_id}"
        db.execute(
            "INSERT OR IGNORE INTO messages(id, group_id, group_name, user_name, content, timestamp, message_id) VALUES (?,?,?,?,?,?,?)",
            (uid, group_id, group_name, user_name, content[:2000], ts, msg_id),
        )
        db.commit()
    except Exception:
        pass

def _search_msgs(group_id: str, keyword: str, limit: int = 20) -> list:
    db = _get_db()
    rows = db.execute(
        "SELECT user_name, content, timestamp, message_id FROM messages WHERE group_id=? AND content LIKE ? ORDER BY timestamp DESC LIMIT ?",
        (group_id, f"%{keyword}%", limit),
    ).fetchall()
    return [{"user": r[0], "text": r[1], "ts": r[2], "mid": r[3]} for r in rows]

def _query_msgs(group_id: str, limit: int = 100, hours: int = 0) -> list:
    db = _get_db()
    if hours:
        cutoff = int(datetime.now().timestamp()) - hours * 3600
        rows = db.execute(
            "SELECT user_name, content, timestamp, message_id FROM messages WHERE group_id=? AND timestamp>=? ORDER BY timestamp ASC LIMIT ?",
            (group_id, cutoff, limit),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT user_name, content, timestamp, message_id FROM messages WHERE group_id=? ORDER BY timestamp DESC LIMIT ?",
            (group_id, limit),
        ).fetchall()
        rows.reverse()
    return [{"user": r[0], "text": r[1], "ts": r[2], "mid": r[3]} for r in rows]

def _cleanup_old():
    """清理超过7天的消息"""
    try:
        cutoff = int(datetime.now().timestamp()) - 7 * 86400
        db = _get_db()
        db.execute("DELETE FROM messages WHERE timestamp<?", (cutoff,))
        # 每群最多保留3000条
        groups = db.execute("SELECT DISTINCT group_id FROM messages").fetchall()
        for (gid,) in groups:
            rows = db.execute("SELECT id FROM messages WHERE group_id=? ORDER BY timestamp DESC LIMIT 1 OFFSET 2999", (gid,)).fetchall()
            if rows:
                db.execute("DELETE FROM messages WHERE group_id=? AND timestamp < (SELECT MIN(timestamp) FROM (SELECT timestamp FROM messages WHERE group_id=? ORDER BY timestamp DESC LIMIT 3000))", (gid, gid))
        db.commit()
    except Exception:
        pass

def _build_link(group_id: str, msg_id: int) -> str:
    cid = str(group_id).replace("-100", "").replace("-", "")
    return f"https://t.me/c/{cid}/{msg_id}"

def _now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

def _fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%m-%d %H:%M")

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

_QA_PROMPT = (
    "你是 Telegram 群聊智能助手。根据以下群聊记录回答用户的问题。\n"
    "每条消息末尾都有来源链接。回答时必须引用来源链接。\n"
    "用中文回答，简洁明了。如果找不到相关信息，请诚实说明。\n"
    "回答格式：\n"
    "<b>📝 回答</b>\n"
    "你的回答内容，附引用链接。"
)

__plugin__ = {
    "name": "AI总结",
    "id": "mysummary",
    "version": "2.0.4",
    "icon": "https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main/plugins/icons/mysummary_v2.svg",
    "author": "凹凸曼",
    "description": "群消息存储+总结+问答+搜索。自动存储消息，支持 .sum .ask .search",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "enable_summary": {
            "type": "boolean", "default": True, "label": "开启总结",
            "section": "基本", "help": "关闭后命令不响应"
        },
        "enable_store": {
            "type": "boolean", "default": True, "label": "自动存储消息",
            "section": "基本", "help": "开启后自动存储群聊消息到本地数据库"
        },
        "monitored_groups": {
            "type": "text", "default": "", "label": "监控群组(留空=全部)",
            "section": "基本",
            "help": "只存储指定群组的消息，用逗号隔开群ID。留空则存储所有群组"
        },
        "store_limit": {
            "type": "number", "default": 3000, "label": "每群最大存储(条)",
            "section": "基本", "min": 500, "max": 10000,
            "help": "超过此数量自动清理旧消息"
        },
        "enable_auto_summary": {
            "type": "boolean", "default": False, "label": "定时自动总结",
            "section": "定时总结",
            "help": "开启后每天固定时间自动总结所有已存储的群组"
        },
        "auto_summary_time": {
            "type": "text", "default": "09:00,21:00", "label": "自动总结时间",
            "section": "定时总结",
            "help": "每天定时总结的时间，多个用逗号隔开，格式 HH:MM"
        },
        "auto_summary_count": {
            "type": "number", "default": 100, "label": "自动总结消息数",
            "section": "定时总结", "min": 20, "max": 500,
            "help": "每次总结最近N条消息"
        },
    },
}


async def setup(ctx):
    ctx.log.info("AI总结 v2.0 已加载")

    # 初始化数据库
    try:
        _get_db()
        ctx.log.info(f"消息数据库: {DB_PATH}")
    except Exception as e:
        ctx.log.error(f"数据库初始化失败: {e}")

    # ── 消息存储 ──
    @ctx.on_message(ctx.filters.text & ctx.filters.group, group=999)
    async def store_handler(client, message):
        if not ctx.config.get("enable_store", True):
            return
        try:
            gid = str(message.chat.id)
            # 检查是否在监控列表中
            monitored = ctx.config.get("monitored_groups", "").strip()
            if monitored:
                allowed = [g.strip() for g in monitored.split(",") if g.strip()]
                if allowed and gid not in allowed:
                    return
            gname = message.chat.title or ""
            uname = message.from_user.first_name if message.from_user else ""
            content = (message.text or "")[:2000]
            mid = message.id
            ts = int(message.date.timestamp()) if message.date else int(datetime.now().timestamp())
            _store_msg(gid, gname, uname, content, mid, ts)
        except Exception:
            pass

    # ── 命令处理 ──
    @ctx.on_message(ctx.filters.text, group=0)
    async def cmd_handler(client, message):
        text = (message.text or "").strip()
        if not text.startswith("."):
            return

        chat_id = str(message.chat.id)

        # .sumsm — 帮助（不受 enable_summary 限制）
        if text == ".sumsm":
            help_text = (
                "📊 <b>AI总结 v2.0</b>\n\n"
                "📌 <b>总结</b>\n"
                "  <code>.sum 50</code> — 总结最近50条\n"
                "  <code>.sum h 24</code> — 总结最近24小时\n\n"
                "🤔 <b>问答</b>\n"
                "  <code>.ask 今天聊了什么</code> — 基于存储消息回答问题\n\n"
                "🔍 <b>搜索</b>\n"
                "  <code>.search 关键词</code> — 搜索存储的消息\n\n"
                "⏰ <b>定时任务</b>\n"
                "  <code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                "  <code>.sum list</code> — 查看任务\n"
                "  <code>.sum run 1</code> — 立即执行\n"
                "  <code>.sum del 1</code> — 删除任务\n\n"
                "⚙️ 可在插件配置中开启自动存储和定时总结"
            )
            msg = await message.reply(help_text)
            try:
                await message.delete()
            except Exception:
                pass
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        if not ctx.config.get("enable_summary", True):
            return

        # .sum [数量] — 快速总结（不删⏳，直接编辑）
        m = re.match(r"^\.sum\s*(\d+)?$", text)
        if m:
            count = int(m.group(1)) if m.group(1) else 50
            wait = await message.reply("⏳ 正在总结...")
            result = await _summarize_from_db(ctx, client, chat_id, count)
            if result["success"]:
                await wait.edit_text(f"📊 {result['title']} · {_now()}\n\n{result['result']}")
            else:
                await wait.edit_text(f"❌ {result['error']}")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # .sum h 小时数 — 按时间总结（不删⏳，直接编辑）
        m = re.match(r"^\.sum\s+h\s*(\d+)$", text)
        if m:
            hours = int(m.group(1))
            wait = await message.reply("⏳ 正在总结...")
            result = await _summarize_from_db(ctx, client, chat_id, 500, hours)
            if result["success"]:
                await wait.edit_text(f"📊 {result['title']} · 最近{hours}小时\n\n{result['result']}")
            else:
                await wait.edit_text(f"❌ {result['error']}")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # .ask 问题 — 基于存储的消息回答问题（不删⏳，直接编辑）
        m = re.match(r"^\.ask\s+(.+)$", text)
        if m:
            question = m.group(1).strip()
            wait = await message.reply("⏳ 正在思考...")
            result = await _ask_question(ctx, client, chat_id, question)
            if result["success"]:
                await wait.edit_text(f"🤔 <b>问题:</b> {question}\n\n{result['result']}")
            else:
                await wait.edit_text(f"❌ {result['error']}")
            try:
                await message.delete()
            except Exception:
                pass
            return

        # .search 关键词 — 搜索存储的消息
        m = re.match(r"^\.search\s+(.+)$", text)
        if m:
            keyword = m.group(1).strip()
            results = _search_msgs(chat_id, keyword)
            if not results:
                await message.reply(f"🔍 未找到包含「{keyword}」的消息")
                try:
                    await message.delete()
                except Exception:
                    pass
                return
            lines = [f"🔍 <b>搜索「{keyword}」</b> — 共{len(results)}条\n"]
            for r in results[:15]:
                link = _build_link(chat_id, r["mid"])
                lines.append(f"[{_fmt_ts(r['ts'])}] {r['user']}: {r['text'][:80]}\n<a href=\"{link}\">🔗</a>")
            if len(results) > 15:
                lines.append(f"\n...还有{len(results)-15}条")
            await message.reply("\n".join(lines))
            try:
                await message.delete()
            except Exception:
                pass
            return

        # .sum help — 帮助（保留原命令兼容）
        if text == ".sum help":
            help_text = (
                "📊 <b>AI总结 v2.0</b>\n\n"
                "📌 <b>总结</b>\n"
                "  <code>.sum 50</code> — 总结最近50条\n"
                "  <code>.sum h 24</code> — 总结最近24小时\n\n"
                "🤔 <b>问答</b>\n"
                "  <code>.ask 今天聊了什么</code> — 基于存储消息回答问题\n\n"
                "🔍 <b>搜索</b>\n"
                "  <code>.search 关键词</code> — 搜索存储的消息\n\n"
                "⏰ <b>定时任务</b>\n"
                "  <code>.sum add 群组 2h 100</code> — 添加定时总结\n"
                "  <code>.sum list</code> — 查看任务\n"
                "  <code>.sum run 1</code> — 立即执行\n"
                "  <code>.sum del 1</code> — 删除任务\n\n"
                "⚙️ 可在插件配置中开启自动存储和定时总结"
            )
            msg = await message.reply(help_text)
            await asyncio.sleep(30)
            try:
                await msg.delete()
            except Exception:
                pass
            return

        # 原有的定时任务命令（.sum add/list/run/del）保持不变
        cmd = text[len(".sum"):].strip()
        parts = cmd.split()
        if parts and parts[0] in ("add", "list", "run", "del"):
            await _handle_schedule(ctx, client, message, parts, cmd, chat_id)

    # ── 定时自动总结 ──
    async def _auto_summary():
        if not ctx.config.get("enable_auto_summary", False):
            return
        try:
            now = datetime.now(TZ)
            times_str = ctx.config.get("auto_summary_time", "09:00,21:00")
            current = now.strftime("%H:%M")
            if current not in [t.strip() for t in times_str.split(",")]:
                return

            count = int(ctx.config.get("auto_summary_count", 100))
            db = _get_db()
            groups = db.execute("SELECT DISTINCT group_id, group_name FROM messages").fetchall()
            for gid, gname in groups:
                result = await _summarize_from_db(ctx, None, gid, count)
                if result["success"]:
                    apps = list(ctx.user_apps or [])
                    if apps:
                        header = f"📊 定时总结\n{result['title']} · {_now()}\n\n"
                        try:
                            await apps[0].send_message(gid, header + result["result"])
                        except Exception:
                            pass
        except Exception:
            pass

    ctx.schedule(_auto_summary, "interval", seconds=300, id="mysummary_auto")

    # ── 每日清理 ──
    async def _daily_cleanup():
        _cleanup_old()

    ctx.schedule(_daily_cleanup, "cron", hour=3, minute=0, id="mysummary_cleanup")

    ctx.log.info("AI总结 v2.0 已就绪")


async def _summarize_from_db(ctx, client, chat_id: str, count: int, hours: int = 0) -> dict:
    """从数据库获取消息并总结"""
    if not ctx.ai.available:
        return {"success": False, "error": "平台AI未配置"}

    msgs = _query_msgs(chat_id, count, hours)
    if not msgs:
        # 如果数据库没有，尝试从 Telegram API 拉取
        if client:
            return await _summarize_from_api(ctx, client, chat_id, count, hours)
        return {"success": False, "error": "未找到消息"}

    # 获取群组名称
    title = chat_id
    try:
        db = _get_db()
        r = db.execute("SELECT group_name FROM messages WHERE group_id=? LIMIT 1", (chat_id,)).fetchone()
        if r and r[0]:
            title = r[0]
    except Exception:
        pass

    # 格式化消息
    lines = []
    for m in msgs:
        link = _build_link(chat_id, m["mid"])
        lines.append(f"{m['user']}: {m['text']}\n来源: {link}")
    formatted = "\n---\n".join(lines)

    try:
        result = await asyncio.wait_for(ctx.ai.chat(f"{_SUM_PROMPT}\n\n{formatted}"), timeout=120)
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = re.sub(r"^.*?think.*?}", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = result.strip()
        if not result:
            return {"success": False, "error": "AI未返回内容"}
        return {"success": True, "result": result, "title": title}
    except asyncio.TimeoutError:
        return {"success": False, "error": "AI响应超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _summarize_from_api(ctx, client, chat_id: str, count: int, hours: int = 0) -> dict:
    """从 Telegram API 拉取消息并总结（原有逻辑）"""
    try:
        peer = int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id
        entity = await client.get_chat(peer)
        username = getattr(entity, "username", "") or ""
        title = getattr(entity, "title", "") or chat_id
    except Exception:
        username = ""
        title = chat_id

    from pyrogram.raw.functions.messages import GetHistory
    try:
        peer = await client.resolve_peer(int(chat_id) if chat_id.lstrip("-").isdigit() else chat_id)
    except Exception:
        return {"success": False, "error": "无法解析群组"}

    all_msgs = []
    offset = 0
    while len(all_msgs) < count:
        try:
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
                if hours and ts:
                    msg_time = datetime.fromtimestamp(ts)
                    if (datetime.now(TZ) - msg_time).total_seconds() > hours * 3600:
                        continue
                all_msgs.append({"id": m.id, "text": m.message or "", "date": ts})
                if len(all_msgs) >= count:
                    break
            offset = msgs[-1].id
            if len(msgs) < 100:
                break
        except Exception:
            break

    if not all_msgs:
        return {"success": False, "error": "未找到消息"}

    lines = []
    for m in all_msgs:
        link = _build_link(chat_id, m["id"])
        ds = _fmt_ts(m["date"]) if m.get("date") else ""
        lines.append(f"[{ds}] {m['text']}\n来源: {link}")
    formatted = "\n---\n".join(lines)

    try:
        result = await asyncio.wait_for(ctx.ai.chat(f"{_SUM_PROMPT}\n\n{formatted}"), timeout=120)
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = result.strip()
        if not result:
            return {"success": False, "error": "AI未返回内容"}
        return {"success": True, "result": result, "title": title}
    except asyncio.TimeoutError:
        return {"success": False, "error": "AI响应超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _ask_question(ctx, client, chat_id: str, question: str) -> dict:
    """基于存储的消息回答问题"""
    if not ctx.ai.available:
        return {"success": False, "error": "平台AI未配置"}

    msgs = _query_msgs(chat_id, 500)
    if not msgs:
        return {"success": False, "error": "数据库无消息，请先开启消息存储"}

    lines = []
    for m in msgs:
        link = _build_link(chat_id, m["mid"])
        lines.append(f"{m['user']}: {m['text']}\n来源: {link}")
    formatted = "\n---\n".join(lines)

    try:
        result = await asyncio.wait_for(ctx.ai.chat(f"{_QA_PROMPT}\n\n群聊记录:\n{formatted}\n\n问题: {question}"), timeout=120)
        result = re.sub(r"<thinking>.*?</thinking>", "", result, flags=re.DOTALL | re.IGNORECASE)
        result = result.strip()
        if not result:
            return {"success": False, "error": "AI未返回内容"}
        return {"success": True, "result": result}
    except asyncio.TimeoutError:
        return {"success": False, "error": "AI响应超时，请稍后重试"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _handle_schedule(ctx, client, message, parts, cmd, chat_id):
    """处理定时任务命令（原有逻辑）"""
    text = message.text or ""
    if parts[0] == "add":
        # .sum add 群组 2h 100
        if len(parts) < 3:
            return
        target = _parse_chat(parts[1])
        interval = _parse_interval(parts[2])
        if not interval:
            await message.reply("❌ 间隔格式无效")
            return
        c = int(parts[3]) if len(parts) > 3 else 50
        tasks = ctx.kv.get("sum_tasks", [])
        tasks.append({"chat_id": target, "interval": interval, "count": c, "id": len(tasks) + 1})
        ctx.kv.set("sum_tasks", tasks)
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
        await message.reply(f"✅ 已添加定时总结: {target} 每{parts[2]} 总结{c}条")
    elif parts[0] == "list":
        tasks = ctx.kv.get("sum_tasks", [])
        if not tasks:
            await message.reply("📋 暂无定时总结任务")
            return
        lines = ["📋 <b>定时总结任务</b>\n"]
        for t in tasks:
            lines.append(f"<b>{t['id']}.</b> {t['chat_id']} 每{t['interval']} 总结{t['count']}条")
        await message.reply("\n".join(lines))
    elif parts[0] == "run":
        if len(parts) < 2:
            return
        tasks = ctx.kv.get("sum_tasks", [])
        tid = int(parts[1])
        task = next((t for t in tasks if t["id"] == tid), None)
        if not task:
            return
        wait = await message.reply("⏳ 正在执行...")
        result = await _summarize_from_db(ctx, client, task["chat_id"], task["count"])
        if result["success"]:
            header = f"📊 定时总结\n{result['title']} · {_now()}\n\n"
            await client.send_message(message.chat.id, header + result["result"])
            await wait.delete()
        else:
            await wait.edit_text(f"❌ {result['error']}")
    elif parts[0] == "del":
        if len(parts) < 2:
            return
        tasks = ctx.kv.get("sum_tasks", [])
        tid = int(parts[1])
        tasks = [t for t in tasks if t["id"] != tid]
        ctx.kv.set("sum_tasks", tasks)
        await message.reply(f"✅ 已删除任务 {tid}")


def _parse_chat(s: str) -> str:
    s = s.strip()
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


async def _do_sum_task(ctx, client, chat_id, count):
    result = await _summarize_from_db(ctx, client, chat_id, count)
    if result["success"]:
        apps = list(ctx.user_apps or [])
        if apps:
            header = f"📊 定时总结\n{result['title']} · {_now()}\n\n"
            try:
                await apps[0].send_message(chat_id, header + result["result"])
            except Exception:
                pass


async def teardown(ctx):
    ctx.log.info("AI总结已卸载")