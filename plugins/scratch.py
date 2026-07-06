# =============================================================================
# AWBotNest 插件：天空刮奖（scratch）
#
# 散财童子（@lucifer_hdsky_bot）刮刮乐自动挂机。
# 手动发 /scratch → 检测 Bot 回复你的刮刮乐卡片 → 随机逐格刮开 → 回本就停。
# 赢一把自动在群里发 /scratch 连锁下一张；连续亏损自动停止，关闭插件再开重置。
# =============================================================================

import asyncio
import random
import re
import time

__plugin__ = {
    "name": "🎰天空刮奖",
    "id": "scratch",
    "version": "1.4.0",
    "author": "Yy",
    "description": "散财童子刮刮乐自动挂机。手动发 /scratch 启动，只处理 Bot 回复你的卡片，赢一把自动连锁。",
    "scope": "user",
    "config_schema": {
        "target_group": {
            "type": "string", "default": "-1001326208894",
            "label": "目标群组ID", "section": "基础",
            "help": "Bot 所在群组，发 /scratch 和监听都在此群。",
        },
        "bot_id": {
            "type": "number", "default": 0,
            "label": "Bot 的 Telegram ID", "section": "基础",
            "help": "@lucifer_hdsky_bot 的数字 ID。填 0 = 不按 Bot 过滤（会处理群内所有刮刮乐）。",
            "min": 0, "max": 9999999999,
        },
        "click_delay": {
            "type": "slider", "default": 0.6,
            "label": "点击间隔(秒)", "section": "防封",
            "min": 0.3, "max": 2.0, "step": 0.1,
            "help": "每格点击之间的等待时间，加 ±20% 随机抖动。",
        },
        "card_cooldown": {
            "type": "slider", "default": 5,
            "label": "卡间冷却(秒)", "section": "防封",
            "min": 2, "max": 30, "step": 1,
            "help": "上一张结束后等 N 秒再发 /scratch，随机加 0~3 秒。",
        },
        "max_consecutive_loss": {
            "type": "number", "default": 5,
            "label": "连续亏损自动停止", "section": "策略",
            "help": "连续 N 张净亏损后自动停止刮奖。关闭插件再开即可重置。",
            "min": 1, "max": 20,
        },
    },
}

# ── 模块级状态 ──────────────────────────────────────
_playing: bool = False           # 防止同时玩多张卡
_consecutive_loss: int = 0       # 连续亏损计数
_auto_stopped: bool = False      # 连续亏损后自动停止

# 去重
_seen: dict[str, float] = {}
_SEEN_TTL: float = 300


# ── 工具函数 ────────────────────────────────────────

def _parse_group(raw: str) -> int | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw.split("\n")[0].strip())
    except ValueError:
        return None


def _is_scratch_card(message) -> bool:
    text = message.text or message.caption or ""
    if "刮刮乐" not in text:
        return False
    markup = getattr(message, "reply_markup", None)
    if not markup or not getattr(markup, "inline_keyboard", None):
        return False
    for row in markup.inline_keyboard:
        for btn in row:
            cb = getattr(btn, "callback_data", "") or ""
            if cb.startswith("scratch:"):
                return True
    return False


def _parse_card(message) -> tuple:
    markup = message.reply_markup
    card_id: int | None = None
    cells: dict[int, tuple[int, int]] = {}
    abandon_pos: tuple[int, int] | None = None

    for r, row in enumerate(markup.inline_keyboard):
        for c, btn in enumerate(row):
            cb = getattr(btn, "callback_data", "") or ""
            if not cb.startswith("scratch:"):
                continue
            parts = cb.split(":")
            if len(parts) < 3:
                continue
            if card_id is None:
                try:
                    card_id = int(parts[1])
                except ValueError:
                    pass
            action = parts[2]
            if action == "abandon":
                abandon_pos = (r, c)
            elif action == "all":
                continue
            else:
                try:
                    cn = int(action)
                    if 1 <= cn <= 9:
                        cells[cn] = (r, c)
                except ValueError:
                    pass
    return card_id, cells, abandon_pos


def _parse_payout(text: str) -> int:
    if not text:
        return 0
    m = re.search(r"已派奖：(\d+) 银元", text)
    return int(m.group(1)) if m else 0


def _prune_seen() -> None:
    now = time.time()
    stale = [k for k, ts in _seen.items() if now - ts > _SEEN_TTL]
    for k in stale:
        _seen.pop(k, None)


# ── 刮奖策略 ────────────────────────────────────────

async def _play_card(ctx, client, message, cfg) -> dict | None:
    chat_id = message.chat.id
    msg_id = message.id
    chat_title = getattr(message.chat, "title", "") if message.chat else ""
    msg_link = getattr(message, "link", "")

    card_id, cells, abandon_pos = _parse_card(message)
    if not card_id or not cells:
        ctx.log.warning("无法解析刮刮乐 msg=%s", msg_id)
        return None

    ctx.log.info("刮奖开始 卡#%s msg=%s", card_id, msg_id)

    remaining = list(range(1, 10))
    random.shuffle(remaining)

    cells_revealed = 0
    cum_payout = 0
    click_delay = float(cfg.get("click_delay", 0.6))

    for cell_num in remaining:
        refetched = await client.get_messages(chat_id, msg_id)
        if not refetched:
            ctx.log.warning("get_messages 返回空 chat=%s msg=%s", chat_id, msg_id)
            break

        _, current_cells, _ = _parse_card(refetched)
        if cell_num not in current_cells:
            continue

        row, col = current_cells[cell_num]

        delay = click_delay * random.uniform(0.8, 1.2)
        await asyncio.sleep(delay)

        try:
            await refetched.click(x=col, y=row)
        except Exception as e:
            err_s = str(e).upper()
            if "FLOOD_WAIT" in err_s:
                fm = re.search(r"(\d+)", str(e))
                if fm:
                    s = int(fm.group(1))
                    ctx.log.warning("FloodWait %ss", s)
                    await asyncio.sleep(s)
                    try:
                        await refetched.click(x=col, y=row)
                    except Exception as e2:
                        ctx.log.warning("FloodWait 后重试仍失败: %s", e2)
                        break
                else:
                    break
            elif "BUTTON_DATA_INVALID" in err_s or "MESSAGE_ID_INVALID" in err_s:
                ctx.log.warning("消息已失效 msg=%s", msg_id)
                break
            else:
                ctx.log.warning("点击格子 %s 失败: %s", cell_num, e)
                break

        cells_revealed += 1
        await asyncio.sleep(0.6)

        refetched = await client.get_messages(chat_id, msg_id)
        if refetched:
            cum_payout = _parse_payout(refetched.text or "")

        ctx.log.info(
            "卡#%s 格%s %d/9 累计%d 成本%d",
            card_id, cell_num, cells_revealed, cum_payout, cells_revealed * 100,
        )

        if cum_payout >= cells_revealed * 100:
            ctx.log.info("✅ 回本 卡#%s %d格 累计%d", card_id, cells_revealed, cum_payout)

            refetched = await client.get_messages(chat_id, msg_id)
            if refetched:
                _, _, ab_pos = _parse_card(refetched)
                if ab_pos:
                    try:
                        await refetched.click(x=ab_pos[1], y=ab_pos[0])
                    except Exception as e:
                        ctx.log.warning("点击放弃失败: %s", e)

            net = cum_payout - cells_revealed * 100
            await ctx.notify(
                f"🏠 群组\n   {chat_title}\n   群ID: {chat_id}\n\n"
                f"🎰 刮奖结果\n   卡#{card_id} | 刮{cells_revealed}格\n"
                f"   累计{cum_payout} | 成本{cells_revealed * 100} | 净{net:+d}\n"
                f"   ✅ 回本就停\n\n"
                f"🔗 消息链接\n   {msg_link}",
                level="success", category="回本", account=client,
            )
            return {
                "card_id": card_id,
                "cells": cells_revealed,
                "payout": cum_payout,
                "cost": cells_revealed * 100,
                "net": net,
            }

    cost = cells_revealed * 100
    net = cum_payout - cost
    emoji = "❌" if net < 0 else "⚠️"
    tag = "亏损" if net < 0 else "中断"

    ctx.log.info(
        "卡#%s %s %d格 累计%d 成本%d 净%d",
        card_id, tag, cells_revealed, cum_payout, cost, net,
    )

    await ctx.notify(
        f"🏠 群组\n   {chat_title}\n   群ID: {chat_id}\n\n"
        f"🎰 刮奖结果\n   卡#{card_id} | 刮{cells_revealed}格\n"
        f"   累计{cum_payout} | 成本{cost} | 净{net:+d}\n"
        f"   {emoji} {tag}\n\n"
        f"🔗 消息链接\n   {msg_link}",
        level="success" if net >= 0 else "warning",
        category=tag, account=client,
    )
    return {
        "card_id": card_id,
        "cells": cells_revealed,
        "payout": cum_payout,
        "cost": cost,
        "net": net,
    }


# ── setup / teardown ────────────────────────────────

async def setup(ctx):
    global _playing, _consecutive_loss, _auto_stopped
    _playing = False
    _auto_stopped = False
    _consecutive_loss = 0

    ctx.log.info("天空刮奖插件已启用 owner_id=%s", ctx.owner_id)

    # ── 消息处理器 ──────────────────────────────────
    # filter 层：target_group ∩ bot_id ∩ reply_to_me
    # handler 只管刮刮乐识别 + 策略执行，不重复判断身份/回复
    cfg = ctx.config
    bot_id = int(cfg.get("bot_id", 0))
    owner_id = ctx.owner_id

    msg_filter = ctx.filters.group
    if bot_id:
        msg_filter = msg_filter & ctx.filters.user(bot_id)
        ctx.log.info("Bot 过滤已启用 bot_id=%s", bot_id)
    else:
        ctx.log.warning("bot_id=0，将处理目标群内所有刮刮乐（不按 Bot 过滤）")

    if owner_id:
        def _reply_to_me(_, __, message):
            rt = getattr(message, "reply_to_message", None)
            return bool(rt and getattr(rt, "from_user", None) and rt.from_user.id == owner_id)
        msg_filter = msg_filter & ctx.filters.create(_reply_to_me)
        ctx.log.info("回复过滤已启用 owner_id=%s", owner_id)
    else:
        ctx.log.warning("ctx.owner_id=0，不检查回复")

    @ctx.on_message(msg_filter, group=-9)
    async def on_scratch_card(client, message):
        global _playing, _consecutive_loss, _auto_stopped

        tg = _parse_group(cfg.get("target_group", ""))
        if not tg or message.chat.id != tg:
            return

        if _auto_stopped:
            return

        if not _is_scratch_card(message):
            return

        ctx.log.info("🎰 识别到刮刮乐 msg=%s", message.id)

        # 去重
        _prune_seen()
        key = f"{message.chat.id}:{message.id}"
        if key in _seen:
            return
        _seen[key] = time.time()

        if _playing:
            ctx.log.info("⏳ 正在玩卡中，跳过 msg=%s", message.id)
            return

        _playing = True
        try:
            result = await _play_card(ctx, client, message, cfg)
            if not result:
                return

            if result["net"] >= 0:
                _consecutive_loss = 0
            else:
                _consecutive_loss += 1
                ctx.log.info("📉 连续亏损 %d 张", _consecutive_loss)

            max_loss = int(cfg.get("max_consecutive_loss", 5))
            if _consecutive_loss >= max_loss:
                _auto_stopped = True
                ctx.log.warning("🛑 连续亏损达上限，自动停止")
                chat_title = (
                    getattr(message.chat, "title", "")
                    if message.chat else ""
                )
                await ctx.notify(
                    f"🛑 天空刮奖已自动停止\n\n"
                    f"🏠 群组\n   {chat_title}\n   群ID: {tg}\n\n"
                    f"⚠️ 原因\n   连续 {_consecutive_loss} 张亏损\n\n"
                    f"💡 重新开始\n   在插件管理关闭再开启「🎰天空刮奖」",
                    level="warning", category="自动停止", account=client,
                )
                return  # 不连锁

            # 无论盈亏，只要没停就连锁下一张
            cooldown = int(cfg.get("card_cooldown", 5))
            wait = cooldown + random.uniform(0, 3)
            ctx.log.info("🔄 %.1fs 后群内发送 /scratch（连续亏损=%d）", wait, _consecutive_loss)
            await asyncio.sleep(wait)
            try:
                await ctx.user.send(tg, "/scratch")
                ctx.log.info("📤 已在群内发送 /scratch")
            except Exception as e:
                ctx.log.warning("发送 /scratch 失败: %s", e)
        except Exception:
            ctx.log.exception("刮奖流程异常")
        finally:
            _playing = False


async def teardown(ctx):
    ctx.log.info("天空刮奖插件已停用")
