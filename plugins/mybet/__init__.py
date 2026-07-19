# -*- coding: utf-8 -*-
# AWBotNest 插件：自动下注引擎 (mybet) v0.6.0

import asyncio
import re
from datetime import datetime, timezone, timedelta

from ._strategy import analyze_trend

__plugin__ = {
    "name": "自动下注",
    "id": "mybet",
    "version": "0.6.1",
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
            "section": "风控", "min": 0, "max": 100000000, "help": "累计盈利达此值自动停", "order": 10
        },
        "stop_loss": {
            "type": "number", "default": 50000, "label": "止损线",
            "section": "风控", "min": 0, "max": 100000000, "help": "累计亏损达此值自动停", "order": 11
        },
        "max_loss_streak": {
            "type": "number", "default": 10, "label": "最大连错数",
            "section": "风控", "min": 1, "max": 100, "help": "连错达到此数强制锁仓", "order": 12
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
FIBO_SEQ = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]


def _fmt(n):
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return "0"


async def setup(ctx):
    ctx.update_config({"_stats": "启动中…"})

    # ── 重置动作 ──
    @ctx.action("reset_bet")
    async def _reset_bet(req=None):
        ctx.kv.set("mybet_locked", False)
        ctx.kv.set("mybet_betted", False)
        ctx.kv.set("mybet_lose_streak", 0)
        ctx.kv.set("mybet_wins", 0)
        ctx.kv.set("mybet_losses", 0)
        ctx.kv.set("mybet_profit", 0)
        ctx.kv.set("mybet_last_matrix", "")
        ctx.kv.set("mybet_last_target", "")
        ctx.kv.set("mybet_last_amount", 0)
        ctx.kv.set("mybet_fibo_step", 0)
        ctx.kv.set("mybet_paroli_step", 0)
        ctx.kv.set("mybet_total_bet", 0)
        ctx.kv.set("mybet_records", [])
        ctx.update_config({"_stats": "已重置"})
        return {"ok": True, "message": "下注状态已重置"}

    # ── 内部函数 ──
    async def _settle(matrix_str):
        cfg = ctx.config
        latest = matrix_str[0]
        target = ctx.kv.get("mybet_last_target", "")
        amount = int(ctx.kv.get("mybet_last_amount", 0) or 0)
        if not target or not amount:
            return
        is_win = (target == "大" and latest == "1") or (target == "小" and latest == "0")
        fee = int(amount * 0.01)
        net = amount - fee if is_win else -amount
        wins = int(ctx.kv.get("mybet_wins", 0) or 0)
        losses = int(ctx.kv.get("mybet_losses", 0) or 0)
        profit = int(ctx.kv.get("mybet_profit", 0) or 0)
        lose_streak = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
        if is_win:
            wins += 1; profit += net; lose_streak = 0
        else:
            losses += 1; profit += net; lose_streak += 1
        ctx.kv.set("mybet_wins", wins)
        ctx.kv.set("mybet_losses", losses)
        ctx.kv.set("mybet_profit", profit)
        ctx.kv.set("mybet_lose_streak", lose_streak)
        ctx.kv.set("mybet_betted", False)
        # 最大连错保护
        max_streak = int(cfg.get("max_loss_streak", 10) or 10)
        if not is_win and max_streak > 0 and lose_streak >= max_streak:
            ctx.kv.set("mybet_locked", True)
        # 记录
        records = list(ctx.kv.get("mybet_records", []) or [])
        records.append({"t": datetime.now().strftime("%H:%M"), "r": "✅" if is_win else "❌", "a": _fmt(amount), "p": _fmt(abs(profit))})
        if len(records) > 20:
            records = records[-20:]
        ctx.kv.set("mybet_records", records)
        ctx.log.info("[下注] %s 结算: 押%s %s → %s, 连错%s, 累计%s",
                      "✅" if is_win else "❌", target, _fmt(amount),
                      "赢" if is_win else "输", lose_streak, _fmt(profit))
        # 止盈止损
        tp = int(cfg.get("take_profit", 100000) or 0)
        sl = int(cfg.get("stop_loss", 50000) or 0)
        if tp > 0 and profit >= tp:
            ctx.kv.set("mybet_locked", True)
        elif sl > 0 and profit <= -sl:
            ctx.kv.set("mybet_locked", True)

    async def _run_strategy(client, message, matrix_str):
        cfg = ctx.config
        bb = int(cfg.get("base_bet", 500) or 500)
        s1 = int(cfg.get("step1_bet", 20000) or 20000)
        s2 = int(cfg.get("step2_bet", 50000) or 50000)
        lt = int(cfg.get("loss_streak", 3) or 3)
        bg = int(cfg.get("big_bet", 5000) or 5000)
        bm = float(cfg.get("big_bet_mult", 2) or 2)
        mx = int(cfg.get("max_bet", 50000000) or 50000000)

        target, mode_name, streak, _ = analyze_trend(
            matrix_str,
            dragon_start=int(cfg.get("dragon_start", 5) or 5),
            dragon_kill=int(cfg.get("dragon_kill", 8) or 8),
            enable_anti_alt=cfg.get("enable_anti_alt", False),
            enable_anti_double=cfg.get("enable_anti_double", False),
        )
        if target == "挂起":
            return

        ls = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
        if ls == 0:
            cb, ml = bb, "平常"
        elif ls == 1:
            cb, ml = s1, "第1次错"
        elif ls < lt:
            cb, ml = s2, f"第{ls}次错"
        else:
            extra = ls - lt + 1
            cb = int(bg * (bm ** (extra - 1)))
            ml = f"反击(×{bm}^{extra-1})"
        if cb > mx:
            cb = mx

        ctx.log.info("[下注] 策略: %s → %s, 连错%s, 注码%s(%s)", mode_name, target, ls, _fmt(cb), ml)

        chips = [50000000, 5000000, 1000000, 250000, 50000, 20000, 2000, 500]
        remaining = cb
        success = False
        for chip in chips:
            while remaining >= chip:
                btn = f"押{target} {chip:,}"
                ok = False
                try:
                    await message.click(btn)
                    ok = True
                except ValueError:
                    break
                except Exception as e:
                    ctx.log.warning("[下注] 点击异常: %r", e)
                    break
                if ok:
                    remaining -= chip
                    success = True
                    await asyncio.sleep(0.3)
        if remaining > 0:
            ctx.log.warning("[下注] ⚠️ 剩余%s无法下注", _fmt(remaining))
        if success:
            ctx.kv.set("mybet_last_target", target)
            ctx.kv.set("mybet_last_amount", cb)
            ctx.kv.set("mybet_betted", True)
        else:
            ctx.log.warning("[下注] ❌ 下注失败")

    async def _handle_matrix(client, message, matrix_str):
        last = ctx.kv.get("mybet_last_matrix", "")
        if matrix_str == last:
            ctx.log.info("[下注] 矩阵未变化，跳过")
            return
        ctx.kv.set("mybet_last_matrix", matrix_str)
        ctx.log.info("[下注] 处理新矩阵: %s...", matrix_str[:20])
        had_bet = ctx.kv.get("mybet_betted", False)
        if had_bet:
            await _settle(matrix_str)
        await _run_strategy(client, message, matrix_str)

    # ── 消息监听 ──
    @ctx.on_message(ctx.filters.text | ctx.filters.caption, group=7)
    async def monitor_bet(client, message):
        try:
            cfg = ctx.config
            if not cfg.get("enable_bet", False):
                return
            tc = int(cfg.get("target_chat", 0) or 0)
            if not tc:
                ctx.log.info("[下注] 未设置目标群")
                return
            if message.chat.id != tc:
                return
            if ctx.kv.get("mybet_locked", False):
                ctx.log.info("[下注] 已锁仓，跳过")
                return
            text = (message.text or message.caption or "").strip()
            if not text:
                ctx.log.info("[下注] 消息为空")
                return
            ctx.log.info("[下注] 收到消息: %s...", text[:50])
            if "[近 40 次结果]" not in text:
                return
            ctx.log.info("[下注] 收到矩阵消息，开始解析")
            lines = text.split("\n")
            ms = ""
            for line in lines:
                if "[" in line and "]" in line and "近 40 次结果" not in line and "由近及远" not in line:
                    d = re.sub(r"[^\d]", "", line)
                    if len(d) >= 5:
                        ms += d
            if not ms:
                ctx.log.info("[下注] 矩阵解析为空")
                return
            await _handle_matrix(client, message, ms)
        except Exception as e:
            ctx.log.error("[下注] 处理异常: %r", e)

    # ── 战绩推送 ──
    async def stats_pusher():
        w = int(ctx.kv.get("mybet_wins", 0) or 0)
        l = int(ctx.kv.get("mybet_losses", 0) or 0)
        p = int(ctx.kv.get("mybet_profit", 0) or 0)
        s = int(ctx.kv.get("mybet_lose_streak", 0) or 0)
        t = w + l
        r = f"{w / t * 100:.1f}%" if t > 0 else "-"
        recs = ctx.kv.get("mybet_records", []) or []
        rt = ""
        if recs:
            lines = []
            for r2 in recs[-10:]:
                lines.append(f"{r2['t']} {r2['r']} {r2['a']} (累计{r2['p']})")
            rt = "\n" + "\n".join(lines)
        ctx.update_config({"_stats": f"连错{s} 总盈亏{_fmt(p)} 赢{w} 输{l} 胜率{r}\n━━━━━━━━━━━━━━\n{rt}"})

    ctx.schedule(stats_pusher, "interval", seconds=30, id="mybet_stats")


async def teardown(ctx):
    pass