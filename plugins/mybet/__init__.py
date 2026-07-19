# -*- coding: utf-8 -*-
# AWBotNest 插件：自动下注引擎 (mybet)

import asyncio
import re
import random
from datetime import datetime, timezone, timedelta

from ._strategy import analyze_trend

__plugin__ = {
    "name": "自动下注",
    "id": "mybet",
    "version": "0.1.1",
    "author": "凹凸曼",
    "description": "监听彩票开奖结果，按追龙/斩龙/斐波那契等策略自动押大押小。",
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
        "dragon_start": {
            "type": "number", "default": 5, "label": "追龙起步",
            "section": "策略", "min": 2, "max": 20, "help": "连开N局后开始追龙", "order": 5
        },
        "dragon_kill": {
            "type": "number", "default": 8, "label": "斩龙死线",
            "section": "策略", "min": 3, "max": 30, "help": "连开N局后逆势反买", "order": 6
        },
        "fibo_max_step": {
            "type": "number", "default": 4, "label": "斐波那契最大阶",
            "section": "策略", "min": 1, "max": 10, "help": "连输倍投到第N阶后强制复位", "order": 7
        },
        "enable_anti_alt": {
            "type": "boolean", "default": False, "label": "破单跳",
            "section": "策略", "order": 8
        },
        "enable_anti_double": {
            "type": "boolean", "default": False, "label": "破双跳",
            "section": "策略", "order": 9
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
                last = ctx.kv.get("mybet_last_matrix", "")
                if matrix_str != last:
                    ctx.kv.set("mybet_last_matrix", matrix_str)
                    ctx.log.info("[下注] 更新走势矩阵: %s...", matrix_str[:20])
                    await _run_strategy(ctx, client, message, matrix_str)

    # ── 定时心跳 ──
    async def heartbeat():
        cfg = ctx.config
        if not cfg.get("enable_bet", False):
            return
        last_sync = ctx.kv.get("mybet_last_sync_ts", 0) or 0
        now = time.time()
        if now - last_sync > 1800:
            ctx.kv.set("mybet_last_sync_ts", now)
            apps = list(ctx.user_apps or [])
            if apps:
                try:
                    await apps[0].send_message("@ZHUQUE_helper_bot", "/info")
                    ctx.log.info("[下注] 心跳 /info")
                except Exception as e:
                    ctx.log.warning("[下注] 心跳失败: %r", e)

    ctx.schedule(heartbeat, "interval", minutes=30, id="mybet_heartbeat")


async def _run_strategy(ctx, client, message, matrix_str):
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

    # 斐波那契/帕罗利
    fibo_step = int(ctx.kv.get("mybet_fibo_step", 0) or 0)
    paroli_step = int(ctx.kv.get("mybet_paroli_step", 0) or 0)
    current_bet = base_bet

    if fibo_step > 0:
        fibo_seq = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55]
        multiplier = fibo_seq[min(fibo_step, len(fibo_seq) - 1)]
        current_bet = base_bet * multiplier
    elif paroli_step > 0:
        current_bet = base_bet * (2 ** paroli_step)

    if current_bet > max_bet:
        current_bet = max_bet

    ctx.log.info("[下注] 注码: %s (底注%s, fibo%s, paroli%s)",
                  _fmt(current_bet), _fmt(base_bet), fibo_step, paroli_step)

    # 尝试下注
    if target in ("大", "小"):
        btn_text = f"押{target} {current_bet:,}"
        success = False
        try:
            # 方式1: 直接点击按钮 (Pyrogram: click(text) 传位置参数)
            await message.click(btn_text)
            ctx.log.info("[下注] ✅ 点击按钮: %s", btn_text)
            success = True
        except AttributeError:
            # 方式2: 用用户账号发消息
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