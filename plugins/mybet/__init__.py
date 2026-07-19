# -*- coding: utf-8 -*-
# AWBotNest 插件：自动下注引擎 (mybet) v0.2.0

import asyncio
import re
from datetime import datetime, timezone, timedelta

from ._strategy import analyze_trend

__plugin__ = {
    "name": "自动下注",
    "id": "mybet",
    "version": "0.2.0",
    "author": "凹凸曼",
    "description": "监听彩票开奖结果，按追龙/斩龙/斐波那契等策略自动押大押小。含结算记录、止盈止损。",
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
            "type": "number", "default": 500, "label": "底注",
            "section": "下注", "min": 100, "max": 1000000, "order": 3
        },
        "max_bet": {
            "type": "number", "default": 5000, "label": "单局上限",
            "section": "下注", "min": 100, "max": 100000000, "order": 4
        },
        "take_profit": {
            "type": "number", "default": 100000, "label": "止盈线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计盈利达此值自动停", "order": 5
        },
        "stop_loss": {
            "type": "number", "default": 50000, "label": "止损线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计亏损达此值自动停", "order": 6
        },
        "dragon_start": {
            "type": "number", "default": 5, "label": "追龙起步",
            "section": "策略", "min": 2, "max": 20, "help": "连开N局后开始追龙", "order": 7
        },
        "dragon_kill": {
            "type": "number", "default": 8, "label": "斩龙死线",
            "section": "策略", "min": 3, "max": 30, "help": "连开N局后逆势反买", "order": 8
        },
        "fibo_max_step": {
            "type": "number", "default": 4, "label": "斐波那契最大阶",
            "section": "策略", "min": 1, "max": 10, "help": "连输倍投到第N阶后强制复位", "order": 9
        },
        "enable_anti_alt": {
            "type": "boolean", "default": False, "label": "破单跳",
            "section": "策略", "order": 10
        },
        "enable_anti_double": {
            "type": "boolean", "default": False, "label": "破双跳",
            "section": "策略", "order": 11
        },
        "_stats": {
            "type": "info", "label": "战绩",
            "section": "战绩"
        },
    },
}

TZ_SH = timezone(timedelta(hours=8))
FIBO_SEQ = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]


def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


async def setup(ctx):
    # ── 监听开奖消息 ──
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

        # 检查是否止盈止损锁仓
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

    # ── 定时更新战绩到配置面板 ──
    async def stats_pusher():
        wins = int(ctx.kv.get("mybet_wins", 0) or 0)
        losses = int(ctx.kv.get("mybet_losses", 0) or 0)
        profit = int(ctx.kv.get("mybet_profit", 0) or 0)
        total = wins + losses
        rate = f"{wins / total * 100:.1f}%" if total > 0 else "-"
        ctx.update_config({"_stats": {
            "type": "info",
            "text": f"赢{wins} 输{losses} 胜率{rate} 总盈亏{_fmt(profit)}"
        }})

    ctx.schedule(stats_pusher, "interval", seconds=30, id="mybet_stats")


async def _handle_matrix(ctx, client, message, matrix_str):
    """处理新的走势矩阵"""
    last = ctx.kv.get("mybet_last_matrix", "")
    if matrix_str == last:
        return
    ctx.kv.set("mybet_last_matrix", matrix_str)

    # 结算上一局
    had_bet = ctx.kv.get("mybet_betted", False)
    if had_bet:
        await _settle(ctx, matrix_str)

    # 运行策略
    await _run_strategy(ctx, client, message, matrix_str)


async def _settle(ctx, matrix_str):
    """结算上一局的下注结果"""
    cfg = ctx.config
    latest = matrix_str[0]  # 最新一期结果
    target = ctx.kv.get("mybet_last_target", "")
    amount = int(ctx.kv.get("mybet_last_amount", 0) or 0)
    mode = ctx.kv.get("mybet_last_mode", "")

    if not target or not amount:
        return

    is_win = (target == "大" and latest == "1") or (target == "小" and latest == "0")
    tax = int(amount * 0.01) if is_win else 0
    net = amount - tax if is_win else -amount

    # 更新统计
    wins = int(ctx.kv.get("mybet_wins", 0) or 0)
    losses = int(ctx.kv.get("mybet_losses", 0) or 0)
    profit = int(ctx.kv.get("mybet_profit", 0) or 0)
    total_bet = int(ctx.kv.get("mybet_total_bet", 0) or 0)

    if is_win:
        wins += 1
        profit += net
    else:
        losses += 1
        profit += net
    total_bet += amount

    ctx.kv.set("mybet_wins", wins)
    ctx.kv.set("mybet_losses", losses)
    ctx.kv.set("mybet_profit", profit)
    ctx.kv.set("mybet_total_bet", total_bet)

    # 更新策略步进
    fibo_step = int(ctx.kv.get("mybet_fibo_step", 0) or 0)
    paroli_step = int(ctx.kv.get("mybet_paroli_step", 0) or 0)
    fibo_max = int(cfg.get("fibo_max_step", 4) or 4)

    if is_win:
        if fibo_step > 0:
            fibo_step = max(0, fibo_step - 2)
            paroli_step = 0
        else:
            paroli_step += 1
            if paroli_step >= 3:
                paroli_step = 0
    else:
        paroli_step = 0
        fibo_step += 1
        if fibo_step >= fibo_max:
            fibo_step = 0
            ctx.log.info("[下注] ⚠️ 斐波那契达死线，强制复位")

    ctx.kv.set("mybet_fibo_step", fibo_step)
    ctx.kv.set("mybet_paroli_step", paroli_step)
    ctx.kv.set("mybet_betted", False)

    symbol = "✅" if is_win else "❌"
    ctx.log.info("[下注] %s 结算: 押%s %s → %s, 净利%s, 累计%s",
                  symbol, target, _fmt(amount),
                  "赢" if is_win else "输",
                  _fmt(net), _fmt(profit))

    # 检查止盈止损
    take_profit = int(cfg.get("take_profit", 100000) or 0)
    stop_loss = int(cfg.get("stop_loss", 50000) or 0)
    if take_profit > 0 and profit >= take_profit:
        ctx.kv.set("mybet_locked", True)
        ctx.log.info("[下注] 🏆 达到止盈线 %s，自动停", _fmt(take_profit))
    elif stop_loss > 0 and profit <= -stop_loss:
        ctx.kv.set("mybet_locked", True)
        ctx.log.info("[下注] 🛑 达到止损线 %s，自动停", _fmt(stop_loss))


async def _run_strategy(ctx, client, message, matrix_str):
    """执行策略并下注"""
    cfg = ctx.config
    base_bet = int(cfg.get("base_bet", 500) or 500)
    max_bet = int(cfg.get("max_bet", 5000) or 5000)
    dragon_start = int(cfg.get("dragon_start", 5) or 5)
    dragon_kill = int(cfg.get("dragon_kill", 8) or 8)
    anti_alt = cfg.get("enable_anti_alt", False)
    anti_double = cfg.get("enable_anti_double", False)

    target, mode_name, streak, _ = analyze_trend(
        matrix_str, dragon_start, dragon_kill, anti_alt, anti_double
    )
    ctx.log.info("[下注] 策略: %s → %s", mode_name, target)

    if target == "挂起":
        return

    # 斐波那契/帕罗利计算
    fibo_step = int(ctx.kv.get("mybet_fibo_step", 0) or 0)
    paroli_step = int(ctx.kv.get("mybet_paroli_step", 0) or 0)
    current_bet = base_bet

    if fibo_step > 0:
        multiplier = FIBO_SEQ[min(fibo_step, len(FIBO_SEQ) - 1)]
        current_bet = base_bet * multiplier
    elif paroli_step > 0:
        current_bet = base_bet * (2 ** paroli_step)

    if current_bet > max_bet:
        current_bet = max_bet

    ctx.log.info("[下注] 注码: %s (底注%s, fibo%s, paroli%s)",
                  _fmt(current_bet), _fmt(base_bet), fibo_step, paroli_step)

    # 下注
    if target in ("大", "小"):
        btn_text = f"押{target} {current_bet:,}"
        success = False
        try:
            await message.click(btn_text)
            ctx.log.info("[下注] ✅ 点击按钮: %s", btn_text)
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
            ctx.log.warning("[下注] 按钮点击失败: %r", e)

        if success:
            ctx.kv.set("mybet_last_target", target)
            ctx.kv.set("mybet_last_amount", current_bet)
            ctx.kv.set("mybet_last_mode", mode_name)
            ctx.kv.set("mybet_betted", True)
        else:
            ctx.log.warning("[下注] ❌ 下注失败")


async def teardown(ctx):
    pass