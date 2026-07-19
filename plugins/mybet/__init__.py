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
    "version": "0.5.0",
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
        "step1_bet": {
            "type": "number", "default": 20000, "label": "第1次错",
            "section": "下注", "min": 100, "max": 100000000, "help": "连错第1局下这个数", "order": 4
        },
        "step2_bet": {
            "type": "number", "default": 50000, "label": "第2次错",
            "section": "下注", "min": 100, "max": 100000000, "help": "连错第2局下这个数", "order": 5
        },
        "loss_streak": {
            "type": "number", "default": 3, "label": "连错几次进反击",
            "section": "下注", "min": 1, "max": 50, "help": "连错达到N局后进入反击模式(大注倍投)", "order": 6
        },
        "big_bet": {
            "type": "number", "default": 5000, "label": "反击大注起始",
            "section": "下注", "min": 100, "max": 100000000, "help": "反击模式第一次下这个数", "order": 7
        },
        "big_bet_mult": {
            "type": "number", "default": 2, "label": "反击大注倍率",
            "section": "下注", "min": 1, "max": 10, "help": "反击模式还输就乘这个倍数继续", "order": 8
        },
        "max_bet": {
            "type": "number", "default": 50000000, "label": "单局封顶",
            "section": "下注", "min": 100, "max": 50000000, "help": "下注封顶，平台上限5000万", "order": 9
        },
        "take_profit": {
            "type": "number", "default": 100000, "label": "止盈线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计盈利达此值自动停", "order": 8
        },
        "stop_loss": {
            "type": "number", "default": 50000, "label": "止损线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计亏损达此值自动停", "order": 9
        },
        "max_loss_streak": {
            "type": "number", "default": 10, "label": "最大连错数",
            "section": "风控", "min": 1, "max": 100, "help": "连错达到此数强制锁仓停赌，手动重置才能恢复", "order": 10
        },
        "_stats": {
            "type": "info", "label": "战绩",
            "section": "战绩"
        },
        "reset_bet": {
            "type": "action", "label": "🔄 重置下注状态",
            "section": "战绩", "action": "reset_bet", "danger": True
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

    # 重置下注状态动作
    @ctx.action("reset_bet")
    async def _reset_bet(req):
        keys = ["mybet_last_matrix", "mybet_last_target", "mybet_last_amount", "mybet_betted",
                "mybet_wins", "mybet_losses", "mybet_profit", "mybet_lose_streak",
                "mybet_fibo_step", "mybet_paroli_step", "mybet_total_bet", "mybet_locked",
                "mybet_records"]
        for k in keys:
            ctx.kv.delete(k)
        ctx.update_config({"_stats": "已重置"})
        return {"ok": True, "message": "下注状态已重置"}

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
    fee = int(amount * 0.01)  # 1%手续费
    net = amount - fee if is_win else -amount

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

    # 最大连错保护
    max_streak = int(cfg.get("max_loss_streak", 10) or 10)
    if not is_win and max_streak > 0 and lose_streak >= max_streak:
        ctx.kv.set("mybet_locked", True)
        ctx.log.info("[下注] 🛑 连错达%s局，强制锁仓停赌！", lose_streak)

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

    # 顺势策略
    target, mode_name, streak, _ = analyze_trend(
        matrix_str,
        dragon_start=int(cfg.get("dragon_start", 5) or 5),
        dragon_kill=int(cfg.get("dragon_kill", 8) or 8),
        enable_anti_alt=cfg.get("enable_anti_alt", False),
        enable_anti_double=cfg.get("enable_anti_double", False),
    )
    if target == "挂起":
        return

    # 判断注码：阶梯式递增 → 反击模式
    lose_streak = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
    loss_threshold = int(cfg.get("loss_streak", 3) or 3)
    step1_bet = int(cfg.get("step1_bet", 20000) or 20000)
    step2_bet = int(cfg.get("step2_bet", 50000) or 50000)
    big_bet = int(cfg.get("big_bet", 5000) or 5000)

    if lose_streak == 0:
        current_bet = base_bet
        mode_label = "平常"
    elif lose_streak == 1:
        current_bet = step1_bet
        mode_label = "第1次错"
    elif lose_streak < loss_threshold:
        current_bet = step2_bet
        mode_label = f"第{lose_streak}次错"
    else:
        # 反击模式：大注倍投
        big_bet_mult = float(cfg.get("big_bet_mult", 2) or 2)
        extra = lose_streak - loss_threshold + 1
        current_bet = int(big_bet * (big_bet_mult ** (extra - 1)))
        mode_label = f"反击(×{big_bet_mult}^{extra-1})"

    ctx.log.info("[下注] 策略: %s → %s, 连错%s, 注码%s(%s)",
                  mode_name, target, lose_streak,
                  _fmt(current_bet), mode_label)

    # 用筹码组合下注（按钮面额固定）
    chips = [50000000, 5000000, 1000000, 250000, 50000, 20000, 2000, 500]
    remaining = current_bet
    success = False
    has_click = hasattr(message, "click")
    for chip in chips:
        while remaining >= chip:
            btn_text = f"押{target} {chip:,}"
            clicked = False
            if has_click:
                try:
                    await message.click(btn_text)
                    ctx.log.info("[下注] ✅ 点击: %s", btn_text)
                    clicked = True
                except ValueError:
                    ctx.log.warning("[下注] 按钮不存在 %s", btn_text)
                    break
                except Exception as e:
                    ctx.log.warning("[下注] 点击异常 %s: %r", btn_text, e)
                    break
            else:
                # 没有 click 方法，用用户账号发文本
                try:
                    apps = list(ctx.user_apps or [])
                    if apps:
                        await apps[0].send_message(message.chat.id, btn_text)
                        ctx.log.info("[下注] ✅ 发送: %s", btn_text)
                        clicked = True
                except Exception as e2:
                    ctx.log.warning("[下注] 发送失败: %r", e2)
                    break
            if clicked:
                remaining -= chip
                success = True
                await asyncio.sleep(0.3)
    if remaining > 0:
        ctx.log.warning("[下注] ⚠️ 剩余 %s 无法下注", _fmt(remaining))

    if success:
        ctx.kv.set("mybet_last_target", target)
        ctx.kv.set("mybet_last_amount", current_bet)
        ctx.kv.set("mybet_betted", True)
    else:
        ctx.log.warning("[下注] ❌ 下注失败")


async def teardown(ctx):
    pass