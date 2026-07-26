# -*- coding: utf-8 -*-
# AWBotNest 插件：天空自动答题 (myskyanswer)

import asyncio
import json
import random
import re
import time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "天空自动答题",
    "id": "myskyanswer",
    "version": "1.0.1",
    "author": "凹凸曼",
    "description": "自动发言 + 自动答题。在指定群组定时发送短语，自动回复机器人的数学题。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "enable_auto_say": {
            "type": "boolean", "default": False, "label": "开启自动发言",
            "section": "自动发言", "order": 1
        },
        "auto_say_chat_ids": {
            "type": "text", "default": "", "label": "发言群组",
            "section": "自动发言", "help": "群ID逗号分隔，必填", "order": 2
        },
        "auto_say_min_minutes": {
            "type": "number", "default": 5, "label": "间隔最小",
            "section": "自动发言", "min": 1, "max": 120, "help": "分钟", "order": 3
        },
        "auto_say_max_minutes": {
            "type": "number", "default": 8, "label": "间隔最大",
            "section": "自动发言", "min": 1, "max": 240, "help": "分钟", "order": 4
        },
        "auto_say_phrases": {
            "type": "text", "default": "", "label": "发言词条",
            "section": "自动发言", "help": "每行一条，随机选2条发送", "order": 5
        },
        "auto_say_use_lyrics": {
            "type": "boolean", "default": True, "label": "混入随机歌词",
            "section": "自动发言", "order": 6
        },
        "auto_say_time_start": {
            "type": "string", "default": "07:00", "label": "发言时段开始",
            "section": "自动发言", "help": "HH:MM 格式", "order": 7
        },
        "auto_say_time_end": {
            "type": "string", "default": "00:00", "label": "发言时段结束",
            "section": "自动发言", "help": "HH:MM 格式，跨天", "order": 8
        },
        "enable_reward_answer": {
            "type": "boolean", "default": False, "label": "开启答题奖励",
            "section": "答题奖励", "order": 1
        },
        "reward_bot_ids": {
            "type": "string", "default": "", "label": "答题机器人",
            "section": "答题奖励", "help": "@机器人用户名，逗号分隔", "order": 2
        },
        "reward_delay_min": {
            "type": "number", "default": 2, "label": "延迟最小",
            "section": "答题奖励", "min": 1, "max": 30, "help": "秒", "order": 3
        },
        "reward_delay_max": {
            "type": "number", "default": 5, "label": "延迟最大",
            "section": "答题奖励", "min": 1, "max": 60, "help": "秒", "order": 4
        },
        "test_say": {
            "type": "action", "label": "🎤 立即发言", "section": "操作",
            "action": "test_say"
        },
    },
}

_KV_NEXT_TS = "auto_say_next_ts"
_KV_PENDING = "auto_say_pending_rewards"

# 内置歌词
_LYRICS = [
    "终于你做了别人的小三，我也知道那不是因为爱",
    "城市套路深，我要回农村",
    "我们还能不能能不能再见面",
    "我在佛前苦苦求了几千年",
    "出卖我的爱，逼着我离开",
    "后来我总算学会了如何去爱",
    "可惜你早已远去消失在人海",
    "爱情不是你想卖想买就能卖",
    "让我用心把你留下来",
    "你是我的小呀小苹果",
    "怎么也飞不出花花的世界",
    "原来我是一只酒醉的蝴蝶",
    "老公老公我爱你",
    "我爱你就像老鼠爱大米",
    "妹妹你坐船头，哥哥在岸上走",
    "我和你缠缠绵绵翩翩飞",
    "因为爱情，不会轻易悲伤",
    "我在这儿等着你回来",
    "你是风儿我是沙",
    "让我们红尘作伴活得潇潇洒洒",
    "死了都要爱，不淋漓尽致不痛快",
    "那就这样吧，再爱都曲终人散",
    "有一种爱叫做放手",
    "遇见你是最美的意外",
    "我和我的祖国一刻也不能分割",
    "送你送到小村外，有句话儿要交代",
    "大河向东流，天上的星星参北斗",
    "路见不平一声吼，该出手时就出手",
    "狼爱上羊啊，爱得疯狂",
    "我爱你中国，亲爱的母亲",
    "我要从南走到北，我还要从白走到黑",
    "曾梦想仗剑走天涯",
    "没有什么能够阻挡",
    "轻轻的我将离开你",
    "请把我的歌带回你的家",
    "我的热情好像一把火",
    "你存在我深深的脑海里",
    "你是我的情歌，唱了一半",
    "不想不想长大，长大后就没童话",
    "简单点，说话的方式简单点",
    "该配合你演出的我演视而不见",
    "因为刚好遇见你，留下足迹才美丽",
    "随风奔跑自由是方向",
    "速度七十迈，心情是自由自在",
    "我要飞的更高，飞的更高",
    "我的未来不是梦",
    "明天会更好",
    "阳光总在风雨后",
    "不经历风雨怎么见彩虹",
    "男人哭吧哭吧不是罪",
    "再回首，云遮断归途",
    "心若在，梦就在",
    "天地之间，还有真爱",
    "我是一只小小鸟",
    "飞得更高，摔得更惨",
    "爱情不是你想买，想买就能买",
    "我的家在东北，松花江上啊",
    "啊，牡丹，百花丛中最鲜艳",
    "你是我天边最美的云彩",
    "苍茫的天涯是我的爱",
    "最炫民族风，永远不落伍",
    "我在仰望，月亮之上",
    "有多少梦想在自由的飞翔",
    "你是我心中最美的云彩",
    "让我用心把你留下来留下来",
    "留下来，永远不分开",
    "你是我的玫瑰你是我的花",
    "爱情是流动的，不由人的",
    "突然好想你，你会在哪里",
    "我怀念的，是无话不说",
    "你不是真正的快乐",
    "伤心的人别听慢歌",
    "人生已经如此的艰难",
    "有些事情，你现在不必问",
    "走吧走吧，人总要学着自己长大",
    "不是因为寂寞才想你",
    "想你时你在天边，想你时你在眼前",
    "宁愿相信我们前世有约",
    "今生的爱情故事不会再改变",
    "爱就一个字，我只说一次",
    "我吹过你吹过的晚风",
    "我们之间，隔着万水千山",
    "其实不想走，其实我想留",
    "留下来陪你，每个春夏秋冬",
    "容易受伤的女人",
    "女人花，摇曳在红尘中",
    "夜太美，尽管再危险",
    "丑八怪，能否别把灯打开",
    "我们不一样，每个人都有不同的境遇",
    "我的滑板鞋，时尚时尚最时尚",
    "摩擦摩擦，在光滑的地上摩擦",
    "出卖我的爱，你背了良心债",
    "就算付出再多，也换不回来",
    "爱情不是你想卖，想买就能卖",
    "让我挣开，让我明白",
    "放手你的爱，不要再回来",
]


def _parse_ids(raw) -> list[int]:
    """解析逗号/换行分隔的ID列表"""
    out = []
    for c in str(raw or "").replace("\n", ",").split(","):
        c = c.strip()
        if not c:
            continue
        try:
            out.append(int(c))
        except ValueError:
            pass
    return out


async def setup(ctx):
    ctx.log.info("天空自动答题插件已加载")

    # ── 自动发言 ──
    async def auto_say_tick():
        if not ctx.config.get("enable_auto_say", False):
            return
        cids = _parse_ids(ctx.config.get("auto_say_chat_ids", ""))
        if not cids:
            return
        phrases_raw = str(ctx.config.get("auto_say_phrases", "") or "").strip()
        user_phrases = [p.strip() for p in phrases_raw.replace("\r\n", "\n").split("\n") if p.strip()]
        use_lyrics = ctx.config.get("auto_say_use_lyrics", True)
        if not user_phrases and not use_lyrics:
            return

        class PoolItem:
            __slots__ = ("text", "next_text")
        pool = []
        for p in user_phrases:
            item = PoolItem()
            item.text = p
            item.next_text = None
            pool.append(item)

        if use_lyrics and _LYRICS:
            for l in random.sample(list(_LYRICS), min(10, len(_LYRICS))):
                parts = None
                for sep in ("，", "。", "；", "！", "？", ",", "?"):
                    if sep in l:
                        s = l.split(sep, 1)
                        parts = (s[0].strip(), s[1].strip())
                        break
                if parts and parts[0]:
                    item = PoolItem()
                    item.text = parts[0]
                    item.next_text = parts[1] if parts[1] else None
                    pool.append(item)
                elif l:
                    item = PoolItem()
                    item.text = l
                    item.next_text = None
                    pool.append(item)
        if len(pool) < 1:
            return

        # 时间区间检查
        try:
            t_start = str(ctx.config.get("auto_say_time_start", "00:00") or "00:00")
            t_end = str(ctx.config.get("auto_say_time_end", "23:59") or "23:59")
            from datetime import datetime as _dt
            now_str = _dt.now().strftime("%H:%M")
            if t_start <= t_end:
                ok = t_start <= now_str <= t_end
            else:
                ok = now_str >= t_start or now_str <= t_end
            if not ok:
                return
        except Exception:
            pass

        now = time.time()
        next_ts = ctx.kv.get(_KV_NEXT_TS, None)
        lo = max(1, int(ctx.config.get("auto_say_min_minutes", 5) or 5))
        hi = int(ctx.config.get("auto_say_max_minutes", 8) or 8)
        if hi < lo:
            hi = lo
        if next_ts is None:
            ctx.kv.set(_KV_NEXT_TS, now + random.uniform(lo, hi) * 60)
            return
        if now < next_ts:
            return
        ctx.kv.set(_KV_NEXT_TS, now + random.uniform(lo, hi) * 60)

        apps = list(ctx.user_apps or [])
        if not apps:
            return
        client = apps[0]

        chosen = random.sample(pool, min(random.randint(1, 3), len(pool)))
        for chat_id in cids:
            msgs = []
            for item in chosen:
                msgs.append(item.text)
                if item.next_text:
                    msgs.append(item.next_text)
            for i, msg in enumerate(msgs):
                try:
                    sent = await client.send_message(chat_id, msg)
                    ctx.log.info("[天空答题] 自动发言 group=%s: %s", chat_id, msg[:30])
                    # 保存发言消息ID，用于检测答题奖励回复
                    pending = ctx.kv.get(_KV_PENDING, [])
                    pending.append({"chat_id": chat_id, "msg_id": sent.id, "time": time.time()})
                    ctx.kv.set(_KV_PENDING, pending[-20:])
                except Exception as e:
                    ctx.log.warning("[天空答题] 自动发言发送失败 group=%s: %r", chat_id, e)
                if i < len(msgs) - 1:
                    await asyncio.sleep(random.uniform(15, 20))
            await asyncio.sleep(1)

    # 注册自动发言定时
    if ctx.config.get("enable_auto_say", False):
        say_min = int(ctx.config.get("auto_say_min_minutes", 5) or 5)
        ctx.schedule(auto_say_tick, "interval", minutes=say_min, id="天空自动发言")
        ctx.log.info("天空自动发言已注册")

    # ── 记录用户自己发的消息，用于答题奖励 ──
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=3)
    async def _user_msg_handler(client, message):
        if not ctx.config.get("enable_reward_answer", False):
            return
        cids = _parse_ids(ctx.config.get("auto_say_chat_ids", ""))
        if cids and message.chat.id not in cids:
            return
        pending = ctx.kv.get(_KV_PENDING, [])
        pending.append({"chat_id": message.chat.id, "msg_id": message.id, "time": time.time()})
        ctx.kv.set(_KV_PENDING, pending[-20:])

    # ── 答题奖励 ──
    @ctx.on_message(ctx.filters.group & ctx.filters.text, group=5)
    async def _reward_handler(client, message):
        if not ctx.config.get("enable_reward_answer", False):
            return
        if not message.reply_to_message_id:
            return
        cids = _parse_ids(ctx.config.get("auto_say_chat_ids", ""))
        if cids and message.chat.id not in cids:
            return
        # 检查是否来自指定机器人
        reward_bots = str(ctx.config.get("reward_bot_ids", "") or "").strip()
        if reward_bots:
            bot_ids = [b.strip().lstrip("@") for b in reward_bots.replace("，", ",").split(",") if b.strip()]
            sender_id = str(message.from_user.id) if message.from_user else ""
            sender_name = (message.from_user.username or "") if message.from_user else ""
            if bot_ids and sender_id not in bot_ids and sender_name not in bot_ids:
                return
        # 检查是否回复了我们的自动发言
        pending = ctx.kv.get(_KV_PENDING, [])
        matched = [p for p in pending if p["chat_id"] == message.chat.id and p["msg_id"] == message.reply_to_message_id]
        if not matched:
            return
        # 清理过期记录
        now = time.time()
        ctx.kv.set(_KV_PENDING, [p for p in pending if now - p.get("time", 0) < 300])

        text = (message.text or "").strip()
        m = re.search(r"(\d+)\s*([+\-×xX*/])\s*(\d+)\s*=\s*(?:\?|？|多少\s*[?？]|)\s*$", text)
        if not m:
            m = re.search(r"(\d+)\s*([+\-×xX*/])\s*(\d+)\s*=\s*多少\s*[?？]", text)
        if not m:
            m = re.search(r"(\d+)\s*([+\-×xX*/])\s*(\d+)\s*=\s*多少\s*[?？]", text)
        if not m:
            return
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        if op in ("+",):
            ans = a + b
        elif op in ("-",):
            ans = a - b
        elif op in ("×", "x", "X", "*"):
            ans = a * b
        elif op in ("/",):
            ans = a // b if b != 0 else 0
        else:
            return
        ctx.log.info("[天空答题] 答题: %d %s %d = %d", a, op, b, ans)
        d_min = int(ctx.config.get("reward_delay_min", 2) or 2)
        d_max = int(ctx.config.get("reward_delay_max", 5) or 5)
        if d_min >= d_max:
            d_max = d_min + 1
        await asyncio.sleep(random.uniform(d_min, d_max))
        await client.send_message(message.chat.id, str(ans))
        # 暂停自动发言
        ctx.kv.set(_KV_NEXT_TS, time.time() + 60)
        ctx.log.info("[天空答题] 答题完成，60秒后继续自动发言")

    ctx.log.info("天空自动答题已就绪")

    # ── 测试按钮 ──
    @ctx.action("test_say")
    async def _test_say(req=None):
        if not ctx.config.get("enable_auto_say", False):
            return {"ok": False, "message": "请先开启自动发言"}
        cids = _parse_ids(ctx.config.get("auto_say_chat_ids", ""))
        if not cids:
            return {"ok": False, "message": "请先配置发言群组"}
        apps = list(ctx.user_apps or [])
        if not apps:
            return {"ok": False, "message": "无可用账号"}
        client = apps[0]

        # 构建发言池（同自动发言逻辑）
        phrases_raw = str(ctx.config.get("auto_say_phrases", "") or "").strip()
        user_phrases = [p.strip() for p in phrases_raw.replace("\r\n", "\n").split("\n") if p.strip()]
        use_lyrics = ctx.config.get("auto_say_use_lyrics", True)

        class PoolItem:
            __slots__ = ("text", "next_text")
        pool = []
        for p in user_phrases:
            item = PoolItem()
            item.text = p
            item.next_text = None
            pool.append(item)

        if use_lyrics and _LYRICS:
            for l in random.sample(list(_LYRICS), min(10, len(_LYRICS))):
                parts = None
                for sep in ("，", "。", "；", "！", "？", ",", "?"):
                    if sep in l:
                        s = l.split(sep, 1)
                        parts = (s[0].strip(), s[1].strip())
                        break
                if parts and parts[0]:
                    item = PoolItem()
                    item.text = parts[0]
                    item.next_text = parts[1] if parts[1] else None
                    pool.append(item)
                elif l:
                    item = PoolItem()
                    item.text = l
                    item.next_text = None
                    pool.append(item)

        if len(pool) < 1:
            pool.append(PoolItem())
            pool[0].text = "🎤 测试发言"
            pool[0].next_text = None

        chosen = random.sample(pool, min(random.randint(1, 3), len(pool)))
        sent = 0
        for chat_id in cids[:3]:
            msgs = []
            for item in chosen:
                msgs.append(item.text)
                if item.next_text:
                    msgs.append(item.next_text)
            for msg in msgs:
                try:
                    await client.send_message(chat_id, msg)
                    sent += 1
                except Exception as e:
                    ctx.log.warning("测试发言发送失败 group=%s: %r", chat_id, e)
                await asyncio.sleep(random.uniform(15, 20))
        return {"ok": True, "message": f"测试发言完成，发送 {sent} 条消息"}


def _effective_cfg(ctx):
    """合并默认值和用户配置"""
    cfg = {
        "enable_auto_say": False,
        "auto_say_chat_ids": "",
        "auto_say_min_minutes": 5,
        "auto_say_max_minutes": 8,
        "auto_say_phrases": "",
        "auto_say_use_lyrics": True,
        "auto_say_time_start": "07:00",
        "auto_say_time_end": "00:00",
        "enable_reward_answer": False,
        "reward_bot_ids": "",
        "reward_delay_min": 2,
        "reward_delay_max": 5,
    }
    cfg.update(dict(ctx.config or {}))
    return cfg


async def teardown(ctx):
    ctx.log.info("天空自动答题已卸载")