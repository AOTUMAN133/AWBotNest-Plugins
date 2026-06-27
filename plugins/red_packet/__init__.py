# =============================================================================
# AWBotNest 插件：抢红包（red_packet）
#
# 监控群红包并自动抢，三类红包合一，按配置开关区分：
#   1. 口令红包：监控指定发包人发的「口令红包」（图片/文档口令）。
#      - OCR 开启且 ddddocr 可用：识别图片口令自动回复。
#      - OCR 关闭/不可用/识别失败：退回「等待复制」——他人口令被红包系统确认后，
#        复制该口令参与（更稳）。三层陷阱防护：命令前缀 / 注入字符 / 关键词库。
#   2. 按钮红包（HDSKY 拼手气红包）：检测「拼手气红包」消息并点击「抢红包」内联按钮。
#   3. 编号按钮红包（癫影积分红包）：逐个点击未抢的数字按钮，抢到一格即停。
#
# 迁移自 AWLottery（red_packet_integration / button_red_packet / dianyingpai_redpacket
# / games.red_packet）。不依赖平台 service / DB / state_repo：配置走 ctx.config，
# 运行记录走 ctx.kv。MY_TGID→ctx.owner_id，通知→ctx.notify。
#
# 注意：本插件用「用户账号」监听并参与红包（scope=user）。它会以你的账号在群里
# 发送口令/点击按钮，请仅监控可信发包人。
# =============================================================================
from __future__ import annotations

import asyncio
import time as _time

from . import _ocr
from ._records import Records, parse_targets, parse_groups, parse_keywords, to_float, to_int
from ._snatch import (
    TokenSnatcher, extract_text, find_snatch_button, find_numbered_buttons,
    is_lucky_packet, is_snatch_success, acct_name,
)

__plugin__ = {
    "name": "抢红包",
    "id": "red_packet",
    "version": "1.0.0",
    "author": "AWdress",
    "scope": "user",
    "default_enabled": False,
    "description": "监控群红包并自动抢：按钮红包自动点击、口令红包自动发口令、图片口令OCR识别，含陷阱防护。",
    "config_schema": {
        # ───────── 口令红包 ─────────
        "token_enabled": {
            "type": "boolean", "default": False, "label": "启用口令红包监控",
            "section": "口令红包",
            "help": "监控指定发包人发的「口令红包」（图片/文档口令），OCR识别或复制他人口令参与。",
        },
        "token_targets": {
            "type": "text", "default": "", "label": "监控发包人",
            "section": "口令红包", "show_if": {"token_enabled": True},
            "help": "一行一个，格式 `用户ID 备注` 或 `用户ID`。只抢这些人发的口令红包。",
        },
        "token_join_delay": {
            "type": "slider", "default": 0, "label": "参与延迟(秒)",
            "min": 0, "max": 60, "step": 1, "section": "口令红包",
            "show_if": {"token_enabled": True},
            "help": "识别/复制到口令后等待多少秒再发送，0=立即。",
        },
        "token_ocr_enabled": {
            "type": "boolean", "default": False, "label": "启用OCR识别图片口令",
            "section": "口令红包", "show_if": {"token_enabled": True},
            "help": "开启则用 ddddocr 识别图片口令自动参与（识别率较低，失败自动退回复制模式）；关闭则只复制他人已确认的口令（更稳）。需安装 ddddocr，未安装时自动降级为复制模式。",
        },
        "token_trap_detection": {
            "type": "boolean", "default": True, "label": "口令陷阱检测",
            "section": "口令红包", "show_if": {"token_enabled": True},
            "help": "发送口令前检查危险/可疑关键词。命令前缀与注入字符始终拦截，不受此开关影响。",
        },
        "token_trap_keywords": {
            "type": "text",
            "default": "脚本,挂,机器人,外挂,bot,自动,作弊,封禁,封号,ban,banned,封,禁,script,auto,cheat,hack,fake,test,block",
            "label": "陷阱关键词", "section": "口令红包",
            "show_if": {"token_enabled": True},
            "help": "逗号或换行分隔。口令命中其中任一关键词则拒绝发送。",
        },
        # ───────── 按钮红包（天空 HDSKY） ─────────
        "button_enabled": {
            "type": "boolean", "default": False, "label": "启用按钮红包（拼手气）",
            "section": "按钮红包(HDSKY)",
            "help": "检测「拼手气红包」消息并自动点击「抢红包」内联按钮。",
        },
        "button_bot_id": {
            "type": "string", "default": "8907007783", "label": "发包机器人ID",
            "section": "按钮红包(HDSKY)", "show_if": {"button_enabled": True},
            "help": "发拼手气红包的机器人用户ID（默认天空小秘 HDSKY）。",
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
        "dyp_bot_id": {
            "type": "string", "default": "8704462066", "label": "癫影机器人ID",
            "section": "癫影积分红包", "show_if": {"dyp_enabled": True},
        },
        "dyp_group_id": {
            "type": "string", "default": "-1003907877852", "label": "癫影监听群ID",
            "section": "癫影积分红包", "show_if": {"dyp_enabled": True},
            "help": "固定监听的群组ID，留空=所有群。",
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

# 口令红包状态机（setup 时创建）
_snatcher: TokenSnatcher | None = None


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
    global _snatcher
    records = Records(ctx.kv, ctx.log)
    _snatcher = TokenSnatcher(ctx, records)

    if not _ocr.ocr_available():
        ctx.log.info("[抢红包] ddddocr 不可用，图片口令OCR将降级为「等待复制」模式")

    # ───────── 口令红包：监控目标发包人的图片/文档红包 ─────────
    @ctx.on_message(ctx.filters.group & (ctx.filters.photo | ctx.filters.document), group=-10)
    async def on_token_packet(client, message):
        cfg = ctx.config
        if not cfg.get("token_enabled", False):
            return
        targets = parse_targets(cfg.get("token_targets", ""))
        fu = message.from_user
        if not fu or fu.id not in targets:
            return
        if "口令红包" not in extract_text(message):
            return
        await _snatcher.handle_new_packet(
            client, message,
            sender_name=targets.get(fu.id, str(fu.id)),
            join_delay=to_float(cfg.get("token_join_delay", 0)),
            ocr_enabled=cfg.get("token_ocr_enabled", False),
            trap_enabled=cfg.get("token_trap_detection", True),
            custom_keywords=parse_keywords(cfg.get("token_trap_keywords", "")),
            notify=cfg.get("notify_owner", True),
        )

    # ───────── 口令红包：监控群内回复（缓存口令 / 失败 / 成功确认）─────────
    @ctx.on_message(ctx.filters.group & ctx.filters.reply, group=-10)
    async def on_token_reply(client, message):
        if not ctx.config.get("token_enabled", False):
            return
        await _snatcher.handle_reply(client, message, notify=ctx.config.get("notify_owner", True))

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
        bot_id = to_int(cfg.get("button_bot_id", "8907007783"))
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
        bot_id = to_int(cfg.get("dyp_bot_id", "8704462066"))
        if not (fu and getattr(fu, "is_bot", False) and fu.id == bot_id):
            return
        if "积分红包" not in extract_text(message):
            return
        group_id = cfg.get("dyp_group_id", "")
        if group_id:
            gid = to_int(group_id)
            if gid and message.chat.id != gid:
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

    ctx.log.info("[抢红包] 已加载（OCR可用=%s）", _ocr.ocr_available())


async def _notify(ctx, client, text, level="info"):
    try:
        await ctx.notify(text, level=level, category="抢红包", account=client)
    except Exception:  # noqa: BLE001
        pass


async def teardown(ctx):
    global _snatcher
    _clicked.clear()
    _snatcher = None
