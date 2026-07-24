# -*- coding: utf-8 -*-
# 炸金花监控插件 - myzjh

import re
import json
import time
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

__plugin__ = {
    "name": "炸金花监控",
    "id": "myzjh",
    "version": "1.0.0",
    "author": "凹凸曼",
    "description": "监控 HDSky 群天空小秘的炸金花结算信息，记录每局数据，支持统计查询。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "chat_id": {
            "type": "number", "default": -1001326208894, "label": "监控群组ID",
            "section": "基本设置", "help": "HDSky Official Group 的群组ID"
        },
        "bot_name": {
            "type": "string", "default": "天空小秘", "label": "机器人名称",
            "section": "基本设置", "help": "发炸金花消息的机器人名字"
        },
        "max_records": {
            "type": "slider", "default": 500, "min": 100, "max": 2000, "step": 100,
            "label": "最大记录数", "section": "基本设置",
            "help": "最多保存多少局记录，超出自动清理最旧的"
        },
        "info": {
            "type": "info", "label": "使用说明", "section": "命令",
            "text": "插件启用后自动监控群里的炸金花结算消息。\n发送 /jh 查看统计概览\n发送 /jhd 查看最近20局详情"
        },
    },
}

_KV_DATA = "zjh_records"
_KV_STATS = "zjh_stats_cache"


def _normalize(name: str) -> str:
    """统一玩家名格式，去掉多余空格"""
    import unicodedata
    return unicodedata.normalize("NFKC", name.strip())


def _now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _clean_name(name: str) -> str:
    """清理玩家名，去掉卡牌符号"""
    import re
    # 去掉末尾所有卡牌：如 "wg358963 10♦" → "wg358963"
    # 也处理 "抽奖不再慢一拍 Q♣ 10♣" → "抽奖不再慢一拍"
    while True:
        cleaned = re.sub(r"\s+\S*[♠♥♦♣]\S*$", "", name)
        if cleaned == name:
            break
        name = cleaned
    return name.strip()


def parse_settlement(text: str) -> dict | None:
    """解析炸金花结算消息，返回结构化数据"""
    # 局号
    m = re.search(r"炸金花结算\s*#(\d+)", text)
    if not m:
        return None
    game_id = int(m.group(1))
    
    # 总下注
    total_bet = 0
    m = re.search(r"总下注[：:]\s*([\d,]+)\s*银元", text)
    if m:
        total_bet = int(m.group(1).replace(",", ""))
    
    # 赢家
    winner = ""
    m = re.search(r"赢家[：:]\s*(.+)", text)
    if m:
        winner = _normalize(m.group(1))
    
    # 赢家返还
    winner_return = 0
    m = re.search(r"赢家返还[：:]\s*([\d,]+)\s*银元", text)
    if m:
        winner_return = int(m.group(1).replace(",", ""))
    
    # 抽水
    rake = 0
    m = re.search(r"抽水[：:]\s*([\d,]+)\s*银元", text)
    if m:
        rake = int(m.group(1).replace(",", ""))
    
    # 玩家列表
    players = []
    for line in text.split("\n"):
        line = line.strip()
        # 🏆 赢家带手牌: "🏆 元宝 A♠ 6♣ 4♦ → 散牌"
        m2 = re.search(r"^🏆\s+(.+?)\s+(?:\S+?[♠♥♦♣]\s*)+→", line)
        if m2:
            players.append({"name": _clean_name(_normalize(m2.group(1))), "result": "win", "detail": line.strip()})
            continue
        # ❌ 输家带手牌
        m2 = re.search(r"^❌\s+(.+?)\s+(?:\S+?[♠♥♦♣]\s*)+→", line)
        if m2:
            players.append({"name": _normalize(m2.group(1)), "result": "lose", "detail": line.strip()})
            continue
        # 🏳️ 弃牌
        m2 = re.search(r"^🏳️\s+(.+?)\s+已弃牌", line)
        if m2:
            players.append({"name": _normalize(m2.group(1)), "result": "fold", "detail": line.strip()})
            continue
        # 🏆 获胜（其余玩家弃牌）
        m2 = re.search(r"^🏆\s+(.+?)\s+获胜", line)
        if m2:
            players.append({"name": _clean_name(_normalize(m2.group(1))), "result": "win", "detail": line.strip()})
            continue
    
    return {
        "game_id": game_id,
        "time": _now(),
        "total_bet": total_bet,
        "winner": winner,
        "winner_return": winner_return,
        "rake": rake,
        "players": players,
    }


async def setup(ctx):
    chat_id = int(ctx.config.get("chat_id", -1001326208894))
    bot_name = ctx.config.get("bot_name", "天空小秘")
    max_records = int(ctx.config.get("max_records", 500) or 500)
    
    @ctx.on_message(ctx.filters.text & ~ctx.filters.outgoing, group=0)
    async def monitor(client, message):
        """监控群消息，抓取炸金花结算"""
        if message.chat.id != chat_id:
            return
        sender = message.from_user
        if not sender or bot_name not in (sender.first_name or ""):
            return
        text = message.text or ""
        if "炸金花结算" not in text:
            return
        
        data = parse_settlement(text)
        if not data:
            return
        
        ctx.log.info(f"抓到炸金花结算 #{data['game_id']}")
        records = ctx.kv.get(_KV_DATA, [])
        # 去重
        for r in records:
            if r.get("game_id") == data["game_id"]:
                return
        records.append(data)
        # 限制数量
        if len(records) > max_records:
            records = records[-max_records:]
        ctx.kv.set(_KV_DATA, records)
        # 清除统计缓存
        ctx.kv.delete(_KV_STATS)
    
    @ctx.on_message(ctx.filters.outgoing & ctx.filters.text, group=6)
    async def cmd_stats(client, message):
        """命令：/zj 查看统计"""
        text = (message.text or "").strip()
        if text not in ("/jh", ".jh", "/jhd", ".jhd"):
            return
        
        records = ctx.kv.get(_KV_DATA, [])
        if not records:
            await message.edit("📭 还没有炸金花记录，等待下一局结算吧。")
            return
        
        # 清理旧数据中可能带卡牌的名字
        cleaned = False
        for r in records:
            for p in r.get("players", []):
                clean = _clean_name(p["name"])
                if clean != p["name"]:
                    p["name"] = clean
                    cleaned = True
            w_clean = _clean_name(r.get("winner", ""))
            if w_clean != r.get("winner", ""):
                r["winner"] = w_clean
                cleaned = True
        if cleaned:
            ctx.kv.set(_KV_DATA, records)
        
        if text in ("/jhd", ".jhd"):
            # 显示最近5局详情（太多会被Telegram截断）
            recent = records[-5:]
            lines = [f"📊 **炸金花最近{len(recent)}局**\n"]
            for r in reversed(recent):
                win_icon = "🏆" if r.get("winner") else "❌"
                gid = r['game_id']
                tm = r['time'][5:16]
                bet = f"{r['total_bet']:,}"
                rake = f"{r['rake']:,}"
                w = r['winner']
                ret = f"{r['winner_return']:,}"
                lines.append(f"{win_icon} **#{gid}** {tm}  下注{bet} 抽水{rake}")
                lines.append(f"  赢家 {w} 得 {ret}")
                for p in r.get("players", []):
                    icon = {"win": "🏆", "lose": "❌", "fold": "🏳️"}.get(p["result"], "❓")
                    mark = " ⬅️" if p["name"] == "滴滴答答💋" else ""
                    lines.append(f"  {icon} {p['name']}{mark}")
                    # 显示手牌
                    detail = p.get("detail", "")
                    if detail and "→" in str(detail):
                        parts = str(detail).split("→")
                        cards_part = parts[0].strip()
                        hand_type = parts[1].strip() if len(parts) > 1 else ""
                        cm = re.search(r"((?:\S+?[♠♥♦♣]\s*)+)$", cards_part)
                        if cm:
                            line = f"  [{cm.group(1).strip()}"
                            if hand_type:
                                line += f" {hand_type}"
                            line += "]"
                            lines[-1] += line
                lines.append("")
            await message.edit("\n".join(lines))
            return
        
        # 统计概况
        player_stats = {}
        for r in records:
            for p in r.get("players", []):
                name = p["name"]
                if name not in player_stats:
                    player_stats[name] = {"total": 0, "win": 0, "lose": 0, "fold": 0}
                player_stats[name]["total"] += 1
                if p["result"] == "win":
                    player_stats[name]["win"] += 1
                elif p["result"] == "lose":
                    player_stats[name]["lose"] += 1
                elif p["result"] == "fold":
                    player_stats[name]["fold"] += 1
        
        # 排序
        sorted_players = sorted(player_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        
        total_bet = sum(r.get("total_bet", 0) for r in records)
        total_rake = sum(r.get("rake", 0) for r in records)
        
        lines = [f"📊 **炸金花统计**　共 {len(records)} 局"]
        lines.append(f"💰 总下注 {total_bet:,}  | 💸 抽水 {total_rake:,}\n")
        
        for name, s in sorted_players:
            win_rate = s["win"] / s["total"] * 100 if s["total"] > 0 else 0
            medal = "👑" if name == "滴滴答答💋" else "▫️"
            win_str = f"🏆{s['win']}" if s['win'] > 0 else ""
            lose_str = f"❌{s['lose']}" if s['lose'] > 0 else ""
            fold_str = f"🏳️{s['fold']}" if s['fold'] > 0 else ""
            parts = [x for x in [win_str, lose_str, fold_str] if x]
            record_str = " ".join(parts) if parts else "—"
            lines.append(f"{medal} **{name}**　{s['total']}局　🎯{win_rate:.0f}%")
            lines.append(f"   {record_str}")
        
        me = "滴滴答答💋"
        if me in player_stats:
            s = player_stats[me]
            lines.append(f"\n👑 **我**：{s['total']}局 {s['win']}胜 {s['lose']}负 {s['fold']}弃　胜率 {s['win']/s['total']*100:.0f}%")
        
        lines.append(f"\n📝 /jhd 查看详情")
        
        await message.edit("\n".join(lines))
    
    ctx.log.info("炸金花监控插件已启动")


async def teardown(ctx):
    ctx.log.info("炸金花监控插件已卸载")