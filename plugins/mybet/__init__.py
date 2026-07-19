# -*- coding: utf-8 -*-
# AWBotNest 插件：自动下注引擎 (mybet) v0.3.0
# 简化版：平常500，连错N次后下大注

import asyncio
import re
from datetime import datetime, timezone, timedelta

from ._strategy import analyze_trend

__plugin__ = {
    "name": "自动下注",
    "id": "mybet",
    "version": "0.3.3",
    "author": "凹凸曼",
    "description": "监听彩票开奖结果，顺势下注。平常500，连错N次后下大注反击。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "enable_bet": {
            "type": "boolean", "default": False, "label": "启用自动下注",
            "section": "功能开关", "cols": 4, "order": 1
        },
        "target_chat": {
            "type": "number", "default": 0, "label": "目标群/频道ID",
            "section": "监听", "help": "监听哪个群的彩票开奖消息", "order": 2
        },
        "base_bet": {
            "type": "number", "default": 500, "label": "平常注码",
            "section": "下注", "min": 100, "max": 10000000, "order": 3
        },
        "big_bet": {
            "type": "number", "default": 5000, "label": "大注起始",
            "section": "下注", "min": 100, "max": 100000000, "help": "连错达到阈值后第一次下这个数", "order": 4
        },
        "big_bet_mult": {
            "type": "number", "default": 2, "label": "大注倍率",
            "section": "下注", "min": 1, "max": 10, "help": "大注还输就乘这个倍数继续下，直到赢为止", "order": 5
        },
        "loss_streak": {
            "type": "number", "default": 5, "label": "连错几次下大注",
            "section": "下注", "min": 1, "max": 50, "help": "连续输N局后下一把开始下大注", "order": 6
        },
        "take_profit": {
            "type": "number", "default": 100000, "label": "止盈线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计盈利达此值自动停", "order": 6
        },
        "stop_loss": {
            "type": "number", "default": 50000, "label": "止损线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计亏损达此值自动停", "order": 7
        },
        "_stats": {
            "type": "info", "label": "战绩",
            "section": "战绩"
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
    # 初始化战绩面板
    ctx.update_config({"_stats": "启动中…"})

    @ctx.on_message(ctx.filters.text & ~ctx.filters.outgoing, group=5)
    async def monitor_bet(client, message):
        cfg = ctx.config
        if not cfg.get("enable_bet", False):
            return
        target_chat = int(cfg.get("target_chat", 0) or 0)
        if not target_chat or message.chat.id != target_chat:
            return

        text = message.text or ""
        if not text:
            return

        if ctx.kv.get("mybet_locked", False):
            return

        # 解析走势矩阵
        if "[近 40 次结果]" in text:
            lines = text.split("\n")
            matrix_str = ""
            for line in lines:
                if "[" in line and "]" in line and "近 40 次结果" not in line and "由近及远" not in line:
                    digits = re.sub(r"[^\d]", "", line)
                    if len(digits) >= 5:
                        matrix_str += digits
            if matrix_str:
                await _handle_matrix(ctx, client, message, matrix_str)

    # 定时更新战绩
    async def stats_pusher():
        wins = int(ctx.kv.get("mybet_wins", 0) or 0)
        losses = int(ctx.kv.get("mybet_losses", 0) or 0)
        profit = int(ctx.kv.get("mybet_profit", 0) or 0)
        streak = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
        total = wins + losses
        rate = f"{wins / total * 100:.1f}%" if total > 0 else "-"
        records = ctx.kv.get("mybet_records", []) or []
        rec_text = ""
        if records:
            recent = records[-10:]
            lines = []
            for r in recent:
                lines.append(f"{r['t']} {r['r']} {r['a']} (累计{r['p']})")
            rec_text = "\n" + "\n".join(lines)
        ctx.update_config({"_stats": f"连错{streak} 总盈亏{_fmt(profit)} 赢{wins} 输{losses} 胜率{rate}\n━━━━━━━━━━━━━━\n{rec_text}"})

    ctx.schedule(stats_pusher, "interval", seconds=30, id="mybet_stats")


async def _handle_matrix(ctx, client, message, matrix_str):
    last = ctx.kv.get("mybet_last_matrix", "")
    if matrix_str == last:
        return
    ctx.kv.set("mybet_last_matrix", matrix_str)

    # 先结算上一局
    had_bet = ctx.kv.get("mybet_betted", False)
    if had_bet:
        await _settle(ctx, matrix_str)

    # 再决定下一把
    await _run_strategy(ctx, client, message, matrix_str)


async def _settle(ctx, matrix_str):
    """结算上一局"""
    cfg = ctx.config
    latest = matrix_str[0]
    target = ctx.kv.get("mybet_last_target", "")
    amount = int(ctx.kv.get("mybet_last_amount", 0) or 0)

    if not target or not amount:
        return

    is_win = (target == "大" and latest == "1") or (target == "小" and latest == "0")
    net = -amount if not is_win else amount

    # 更新统计
    wins = int(ctx.kv.get("mybet_wins", 0) or 0)
    losses = int(ctx.kv.get("mybet_losses", 0) or 0)
    profit = int(ctx.kv.get("mybet_profit", 0) or 0)
    lose_streak = int(ctx.kv.get("mybet_lose_streak", 0) or 0)

    if is_win:
        wins += 1
        profit += net
        lose_streak = 0  # 赢了清零连错
    else:
        losses += 1
        profit += net
        lose_streak += 1  # 输了连错+1

    ctx.kv.set("mybet_wins", wins)
    ctx.kv.set("mybet_losses", losses)
    ctx.kv.set("mybet_profit", profit)
    ctx.kv.set("mybet_lose_streak", lose_streak)
    ctx.kv.set("mybet_betted", False)

    # 存储最近记录（保留最近20条）
    records = ctx.kv.get("mybet_records", []) or []
    from datetime import datetime as _dt
    records.append({
        "t": _dt.now().strftime("%H:%M"),
        "r": "✅" if is_win else "❌",
        "a": _fmt(amount),
        "p": _fmt(abs(profit)),
    })
    if len(records) > 20:
        records = records[-20:]
    ctx.kv.set("mybet_records", records)

    symbol = "✅" if is_win else "❌"
    ctx.log.info("[下注] %s 结算: 押%s %s → %s, 连错%s, 累计%s",
                  symbol, target, _fmt(amount),
                  "赢" if is_win else "输",
                  lose_streak, _fmt(profit))

    # 止盈止损
    take_profit = int(cfg.get("take_profit", 100000) or 0)
    stop_loss = int(cfg.get("stop_loss", 50000) or 0)
    if take_profit > 0 and profit >= take_profit:
        ctx.kv.set("mybet_locked", True)
        ctx.log.info("[下注] 🏆 达止盈线 %s，停", _fmt(take_profit))
    elif stop_loss > 0 and profit <= -stop_loss:
        ctx.kv.set("mybet_locked", True)
        ctx.log.info("[下注] 🛑 达止损线 %s，停", _fmt(stop_loss))


async def _run_strategy(ctx, client, message, matrix_str):
    """决定下注金额并执行"""
    cfg = ctx.config
    base_bet = int(cfg.get("base_bet", 500) or 500)
    big_bet = int(cfg.get("big_bet", 5000) or 5000)
    loss_threshold = int(cfg.get("loss_streak", 5) or 5)

    # 顺势策略
    target, mode_name, streak, _ = analyze_trend(matrix_str, 99, 99)
    if target == "挂起":
        return

    # 判断是否下大注
    lose_streak = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
    use_big = lose_streak >= loss_threshold
    if use_big:
        big_bet_mult = float(cfg.get("big_bet_mult", 2) or 2)
        extra = lose_streak - loss_threshold + 1
        current_bet = int(big_bet * (big_bet_mult ** (extra - 1)))
    else:
        current_bet = base_bet

    ctx.log.info("[下注] 策略: %s → %s, 连错%s, 注码%s(%s)",
                  mode_name, target, lose_streak,
                  _fmt(current_bet), "大注" if use_big else "平常")

    btn_text = f"押{target} {current_bet:,}"
    success = False
    try:
        await message.click(btn_text)
        ctx.log.info("[下注] ✅ 点击: %s", btn_text)
        success = True
    except AttributeError:
        try:
            apps = list(ctx.user_apps or [])
            if apps:
                await apps[0].send_message(message.chat.id, btn_text)
                ctx.log.info("[下注] ✅ 发送: %s", btn_text)
                success = True
        except Exception as e2:
            ctx.log.warning("[下注] 文本下注失败: %r", e2)
    except Exception as e:
        ctx.log.warning("[下注] 点击失败: %r", e)

    if success:
        ctx.kv.set("mybet_last_target", target)
        ctx.kv.set("mybet_last_amount", current_bet)
        ctx.kv.set("mybet_betted", True)
    else:
        ctx.log.warning("[下注] ❌ 下注失败")


async def teardown(ctx):
    pass