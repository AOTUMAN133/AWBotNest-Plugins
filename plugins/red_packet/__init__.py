# =============================================================================
# AWBotNest 插件：抢红包（red_packet）
#
# 监控群红包并自动抢，两类按钮红包合一，按配置开关区分：
#   1. 按钮红包（HDSKY 拼手气红包）：检测「拼手气红包」消息并点击「抢红包」内联按钮。
#   2. 编号按钮红包（癫影积分红包）：逐个点击未抢的数字按钮，抢到一格即停。
#
# 口令红包（影巢测试功能）已拆到独立插件 yingchao_redpacket，本插件不再包含。
#
# 迁移自 AWLottery（button_red_packet / dianyingpai_redpacket / games.red_packet）。
# 不依赖平台 service / DB / state_repo：配置走 ctx.config，运行记录走 ctx.kv。
# MY_TGID→ctx.owner_id，通知→ctx.notify。
#
# 注意：本插件用「用户账号」监听并参与红包（scope=user）。它会以你的账号在群里
# 点击按钮，请仅在可信群启用。
# =============================================================================
from __future__ import annotations

import asyncio
import time as _time

from ._records import Records, parse_groups, to_float
from ._snatch import (
    extract_text, find_snatch_button, find_numbered_buttons,
    is_lucky_packet, is_snatch_success, acct_name,
)

__plugin__ = {
    "name": "抢红包",
    "id": "red_packet",
    "version": "1.1.0",
    "author": "AWdress",
    "scope": "user",
    "default_enabled": False,
    "description": "监控群红包并自动抢：拼手气红包(HDSKY)自动点击「抢红包」按钮、癫影积分红包逐格点击。口令红包请用「影巢口令红包」插件。",
    "config_schema": {
        # ───────── 按钮红包（天空 HDSKY） ─────────
        "button_enabled": {
            "type": "boolean", "default": False, "label": "启用按钮红包（拼手气）",
            "section": "按钮红包(HDSKY)",
            "help": "检测「拼手气红包」消息并自动点击「抢红包」内联按钮。",
        },
        "button_groups": {
            "type": "string", "default": "", "label": "监听群组ID",
            "section": "按钮红包(HDSKY)", "show_if": {"button_enabled": True},
            "help": "逗号分隔的群组ID，留空=所有群。",
        },
        "button_delay": {
            "type": "slider", "default": 0, "label": "点击延迟(秒)",
            "min": 0, "max": 60, "step": 1, "section": "按钮红包(HDSKY)",
            "show_if": {"button_enabled": True},
        },
        "button_pre_send": {
            "type": "boolean", "default": False, "label": "发言占位（/red前）",
            "section": "按钮红包(HDSKY)", "show_if": {"button_enabled": True},
            "help": "检测到 /red 发包命令时先发一条消息占位（随即删除），应对「限最近发言人」。",
        },
        "button_pre_send_text": {
            "type": "string", "default": ".", "label": "占位消息内容",
            "section": "按钮红包(HDSKY)", "show_if": {"button_enabled": True},
        },
        # ───────── 编号按钮红包（癫影积分） ─────────
        "dyp_enabled": {
            "type": "boolean", "default": False, "label": "启用癫影积分红包",
            "section": "癫影积分红包",
            "help": "癫影小助手发的积分红包，逐个点击未抢数字按钮（✅1~✅9 已抢的跳过）。",
        },
        "dyp_delay": {
            "type": "slider", "default": 0, "label": "点击延迟(秒)",
            "min": 0, "max": 60, "step": 1, "section": "癫影积分红包",
            "show_if": {"dyp_enabled": True},
        },
        # ───────── 通用 ─────────
        "notify_owner": {
            "type": "boolean", "default": True, "label": "抢包结果通知我",
            "section": "通用", "help": "抢到/拦截/失败时用机器人通知平台主人。",
        },
    },
}

# 按钮点击去重（进程内，TTL 清理）：key = "acct:chat:msg" → 时间戳
_clicked: dict[str, float] = {}
_CLICKED_TTL = 3600

# 发包机器人 / 癫影群（原项目写死，非可配）
_HDSKY_BOT_ID = 8907007783      # 天空小秘 HDSKY（拼手气红包）
_DYP_BOT_ID = 8704462066        # 癫影小助手（积分红包）
_DYP_GROUP_ID = -1003907877852  # 癫影积分红包固定群


def _prune_clicked() -> None:
    now = _time.time()
    for k in [k for k, ts in _clicked.items() if now - ts > _CLICKED_TTL]:
        _clicked.pop(k, None)


def _click_once(client, message) -> bool:
    """点击去重：返回 True 表示首次（可点击），False 表示已点过。"""
    me = getattr(client, "me", None)
    acct_id = me.id if me else id(client)
    key = f"{acct_id}:{message.chat.id}:{message.id}"
    _prune_clicked()
    if key in _clicked:
        return False
    _clicked[key] = _time.time()
    return True


async def setup(ctx):
    records = Records(ctx.kv, ctx.log)

    # ───────── 按钮红包（HDSKY 拼手气）：/red 占位发言 ─────────
    @ctx.on_message(ctx.filters.group & ctx.filters.regex(r"^/red(@[\w]+)?(\s|$)"), group=-10)
    async def on_red_command(client, message):
        cfg = ctx.config
        if not cfg.get("button_enabled", False) or not cfg.get("button_pre_send", False):
            return
        groups = parse_groups(cfg.get("button_groups", ""))
        if groups and message.chat.id not in groups:
            return
        try:
            pre = cfg.get("button_pre_send_text", ".") or "."
            m = await client.send_message(message.chat.id, pre)
            await m.delete()
            ctx.log.debug("[抢红包] /red 占位发言 chat=%s", message.chat.id)
        except Exception as e:  # noqa: BLE001
            ctx.log.debug("[抢红包] /red 占位失败: %r", e)

    # ───────── 按钮红包（HDSKY 拼手气）：点击抢红包按钮 ─────────
    @ctx.on_message(ctx.filters.group, group=-9)
    async def on_button_packet(client, message):
        cfg = ctx.config
        if not cfg.get("button_enabled", False):
            return
        fu = message.from_user
        bot_id = _HDSKY_BOT_ID  # 原项目写死
        if not (fu and getattr(fu, "is_bot", False) and fu.id == bot_id):
            return
        groups = parse_groups(cfg.get("button_groups", ""))
        if groups and message.chat.id not in groups:
            return
        if not is_lucky_packet(message):
            return
        pos = find_snatch_button(message)
        if not pos:
            return
        if not _click_once(client, message):
            return

        delay = to_float(cfg.get("button_delay", 0))
        if delay > 0:
            await asyncio.sleep(delay)
        row, col = pos
        try:
            result = await message.click(x=col, y=row, timeout=10)
            rtext = getattr(result, "text", None) or getattr(result, "message", None) or str(result)
            ctx.log.info("[抢红包] 已点击拼手气红包 chat=%s msg=%s 结果=%s", message.chat.id, message.id, rtext)
            records.add_history({"type": "按钮红包", "group_id": message.chat.id, "result": str(rtext), "ok": True})
            if cfg.get("notify_owner", True):
                await _notify(ctx, client,
                    f"抢红包-拼手气已抢\n🏠 {getattr(message.chat,'title','')} ({message.chat.id})\n📩 {rtext}\n🔗 {getattr(message,'link','')}",
                    level="success")
        except Exception as e:  # noqa: BLE001
            ctx.log.error("[抢红包] 拼手气点击失败 chat=%s msg=%s: %r", message.chat.id, message.id, e)
            if cfg.get("notify_owner", True):
                await _notify(ctx, client,
                    f"抢红包-拼手气点击失败\n🏠 {getattr(message.chat,'title','')} ({message.chat.id})\n⚠️ {e}",
                    level="error")

    # ───────── 编号按钮红包（癫影积分）：逐格点击 ─────────
    @ctx.on_message(ctx.filters.group, group=-9)
    async def on_dyp_packet(client, message):
        cfg = ctx.config
        if not cfg.get("dyp_enabled", False):
            return
        fu = message.from_user
        bot_id = _DYP_BOT_ID  # 原项目写死
        if not (fu and getattr(fu, "is_bot", False) and fu.id == bot_id):
            return
        if "积分红包" not in extract_text(message):
            return
        if message.chat.id != _DYP_GROUP_ID:
            return
        if not _click_once(client, message):
            return

        delay = to_float(cfg.get("dyp_delay", 0))
        if delay > 0:
            await asyncio.sleep(delay)

        positions = find_numbered_buttons(message)
        if not positions:
            ctx.log.debug("[抢红包] 癫影红包无可点按钮 msg=%s", message.id)
            return
        ctx.log.info("[抢红包] 癫影红包找到 %d 个未抢按钮，逐格尝试", len(positions))

        for idx, (row, col) in enumerate(positions, start=1):
            try:
                result = await message.click(x=col, y=row, timeout=10)
                rtext = getattr(result, "text", None) or getattr(result, "message", None) or ""
                rstr = rtext or str(result)
                ctx.log.info("[抢红包] 癫影第%d格(行%d列%d) 结果=%r", idx, row, col, rstr)
                if is_snatch_success(rstr):
                    records.add_history({"type": "癫影积分红包", "group_id": message.chat.id, "result": rstr, "ok": True})
                    if cfg.get("notify_owner", True):
                        await _notify(ctx, client,
                            f"癫影积分红包-已抢\n🏠 {getattr(message.chat,'title','')} ({message.chat.id})\n📩 {rstr}\n🔗 {getattr(message,'link','')}",
                            level="success")
                    return
                await asyncio.sleep(0.3)
            except Exception as e:  # noqa: BLE001
                ctx.log.warning("[抢红包] 癫影第%d格点击异常: %r", idx, e)
                await asyncio.sleep(0.3)
        # 全部试完未抢到
        if cfg.get("notify_owner", True):
            await _notify(ctx, client,
                f"癫影积分红包-未抢到\n🏠 {getattr(message.chat,'title','')} ({message.chat.id})\n📩 所有格子均已被抢完",
                level="info")

    ctx.log.info("[抢红包] 已加载（拼手气 + 癫影积分）")


async def _notify(ctx, client, text, level="info"):
    try:
        await ctx.notify(text, level=level, category="抢红包", account=client)
    except Exception:  # noqa: BLE001
        pass


async def teardown(ctx):
    _clicked.clear()
