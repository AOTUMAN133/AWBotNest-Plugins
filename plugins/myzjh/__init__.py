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


def _now():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


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
        winner = m.group(1).strip()
    
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
        m2 = re.search(r"^🏆\s+(.+?)\s+(?:\S[♠♥♦♣]\s*)+→", line)
        if m2:
            players.append({"name": m2.group(1).strip(), "result": "win", "detail": line.strip()})
            continue
        # ❌ 输家带手牌
        m2 = re.search(r"^❌\s+(.+?)\s+(?:\S[♠♥♦♣]\s*)+→", line)
        if m2:
            players.append({"name": m2.group(1).strip(), "result": "lose", "detail": line.strip()})
            continue
        # 🏳️ 弃牌
        m2 = re.search(r"^🏳️\s+(.+?)\s+已弃牌", line)
        if m2:
            players.append({"name": m2.group(1).strip(), "result": "fold", "detail": line.strip()})
            continue
        # 🏆 获胜（其余玩家弃牌）
        m2 = re.search(r"^🏆\s+(.+?)\s+获胜", line)
        if m2:
            players.append({"name": m2.group(1).strip(), "result": "win", "detail": line.strip()})
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
        
        if text in ("/jhd", ".jhd"):
            # 显示最近10局详情（太多会超Telegram长度限制）
            recent = records[-10:]
            lines = [f"📊 **炸金花最近{len(recent)}局详情**\n"]
            for r in reversed(recent):
                win_icon = "🏆" if r.get("winner") else "❌"
                lines.append(f"{win_icon} **#{r['game_id']}** {r['time'][5:16]}")
                lines.append(f"  下注 {r['total_bet']:,} | 抽水 {r['rake']:,} | 赢家 {r['winner']} 得 {r['winner_return']:,}")
                for p in r.get("players", []):
                    icon = {"win": "🏆", "lose": "❌", "fold": "🏳️"}.get(p["result"], "❓")
                    mark = " ⬅️" if p["name"] == "滴滴答答💋" else ""
                    lines.append(f"  {icon} {p['name']}{mark}")
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
        
        # 排序：按参与次数降序
        sorted_players = sorted(player_stats.items(), key=lambda x: x[1]["total"], reverse=True)
        
        # 计算长条图比例
        max_total = max(s["total"] for s in player_stats.values()) if player_stats else 1
        
        lines = [f"📊 **炸金花统计**　共 {len(records)} 局 | 总抽水 {sum(r.get('rake',0) for r in records):,} 银元\n"]
        
        for name, s in sorted_players:
            win_rate = s["win"] / s["total"] * 100 if s["total"] > 0 else 0
            bar_len = int(s["total"] / max_total * 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            medal = "👑" if name == "滴滴答答💋" else "🎲"
            lines.append(f"{medal} **{name}**")
            lines.append(f"   {bar}  {s['total']}局")
            win_str = "🏆" * min(s["win"], 5) + ("…" if s["win"] > 5 else "")
            lines.append(f"   ✅胜 {s['win']}  ❌负 {s['lose']}  🏳️弃 {s['fold']}  🎯胜率 {win_rate:.1f}%  {win_str}")
            lines.append("")
        
        # 我自己的数据
        me = "滴滴答答💋"
        if me in player_stats:
            s = player_stats[me]
            lines.append(f"👑 **我的战绩**：{s['total']}局 {s['win']}胜 {s['lose']}负 {s['fold']}弃")
            lines.append(f"   胜率 {s['win']/s['total']*100:.1f}%")
        
        # 总数据
        total_bet = sum(r.get("total_bet", 0) for r in records)
        total_rake = sum(r.get("rake", 0) for r in records)
        lines.append(f"\n💰 总下注 {total_bet:,} 银元 | 💸 总抽水 {total_rake:,} 银元")
        lines.append(f"📝 发送 /jhd 查看最近详情")
        
        await message.edit("\n".join(lines))
    
    ctx.log.info("炸金花监控插件已启动")


async def teardown(ctx):
    ctx.log.info("炸金花监控插件已卸载")