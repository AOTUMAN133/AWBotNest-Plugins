# =============================================================================
# AWBotNest 插件：天空红包（hdsky）
#
# 由 tgbot-n/plugins/user/red_packet/hdsky.py 迁移适配。
# 天空小秘（bot ID 8907007783）在群组发拼手气红包，
# 消息含「拼手气红包」关键字，内联键盘有「抢红包」按钮，
# 点击按钮抢红包。
#
# 策略：
# 1. 检测到拼手气红包 → 立即点击「抢红包」按钮
# 2. 如果返回"前 10 秒仅限最近 20 位发言人领取"，等够 10s 后重试一次
# =============================================================================

import asyncio
import time

__plugin__ = {
    "name": "🧧天空红包",
    "id": "hdsky",
    "version": "2.0.0",
    "author": "Yy",
    "description": "天空小秘（bot 8907007783）拼手气红包自动抢：检测「抢红包」按钮即时点击，遇10秒限制自动等够重试。",
    "scope": "user",
    "config_schema": {
        "enabled_groups": {
            "type": "string", "default": "-1001326208894",
            "label": "监听群组（一行一个ID）",
            "section": "群组",
            "help": "要监听的群组ID，每行一个。空 = 所有群。",
        },
    },
}

BOT_ID = 8907007783
_CLICKED_TTL = 3600

# 去重缓存（内存级，插件重载时重置）
_clicked: dict[str, float] = {}


def _parse_groups(raw: str) -> list[int]:
    """解析多行群组 ID 字符串为列表。"""
    groups = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                groups.append(int(line))
            except ValueError:
                pass
    return groups


def _prune_clicked() -> None:
    """清理过期的去重记录。"""
    now = time.time()
    stale = [k for k, ts in _clicked.items() if now - ts > _CLICKED_TTL]
    for k in stale:
        _clicked.pop(k, None)


def _find_snatch_button(message) -> tuple[int, int] | None:
    """在消息内联键盘里找「抢红包」按钮，返回 (row, col) 或 None。"""
    markup = getattr(message, "reply_markup", None)
    if not markup or not getattr(markup, "inline_keyboard", None):
        return None
    for r, row in enumerate(markup.inline_keyboard):
        for c, btn in enumerate(row):
            text = getattr(btn, "text", "") or ""
            if "抢红包" in text or "抢 红 包" in text or text.strip() in ("抢", "领取红包"):
                return (r, c)
    return None


def _is_lucky_packet(message) -> bool:
    """判断是否为拼手气红包消息。"""
    text = message.text or message.caption or ""
    if "拼手气红包" in text:
        return True
    if "红包" in text and ("份数" in text or "总银元" in text or "总金额" in text):
        return True
    return False


async def setup(ctx):
    cfg = ctx.config
    ctx.log.info("天空红包插件已启用")

    # ─── 抢红包 Handler ────────────────────────────────
    @ctx.on_message(
        ctx.filters.group
        & ctx.filters.user(BOT_ID),
        group=-9,
    )
    async def snatch_red_packet(client, message):
        """检测拼手气红包消息并点击「抢红包」按钮。"""
        chat_id = message.chat.id
        groups = _parse_groups(cfg.get("enabled_groups", ""))
        if groups and chat_id not in groups:
            return

        if not _is_lucky_packet(message):
            return

        btn_pos = _find_snatch_button(message)
        if not btn_pos:
            ctx.log.debug("拼手气红包消息无「抢红包」按钮，跳过 msg=%s", message.id)
            return

        # 去重（按 owner 隔离，多账号安全）
        owner_id = getattr(client, "_owner_id", 0)
        key = f"{owner_id}:{chat_id}:{message.id}"
        _prune_clicked()
        if key in _clicked:
            return
        _clicked[key] = time.time()

        # ── 直接点击 ──
        row, col = btn_pos
        chat_title = getattr(message.chat, "title", "") if message.chat else ""
        msg_link = getattr(message, "link", "")

        try:
            result = await message.click(x=col, y=row, timeout=10)
            result_text = getattr(result, "message", None) or str(result)

            # 如果触发 10 秒限制（前 10 秒仅限最近 20 位发言人），等够 10 秒后重试
            if "前 10 秒仅限最近 20 位发言人" in result_text and message.date:
                red_packet_ts = message.date.timestamp()
                now = time.time()
                wait = max(0, red_packet_ts + 10 - now)
                if wait > 0:
                    ctx.log.info(
                        "天空红包 10秒限制，等待 %.1fs 后重试 chat=%s msg=%s",
                        wait, chat_id, message.id,
                    )
                    await asyncio.sleep(wait)
                    result = await message.click(x=col, y=row, timeout=10)
                    result_text = getattr(result, "message", None) or str(result)

            ctx.log.info("已点击抢红包 chat=%s msg=%s 结果=%s", chat_id, message.id, result_text)
            await ctx.notify(
                f"🏠 所在群组\n   {chat_title}\n   群ID: {chat_id}\n\n"
                f"📩 抢包结果\n   {result_text}\n\n"
                f"🔗 消息链接\n   {msg_link}",
                level="success",
                category="已抢",
                account=client,
            )
        except Exception as e:
            ctx.log.warning("点击抢红包失败 chat=%s msg=%s: %s", chat_id, message.id, e)
            await ctx.notify(
                f"🏠 所在群组\n   {chat_title}\n   群ID: {chat_id}\n\n"
                f"⚠️ 错误信息\n   {e}\n\n"
                f"🔗 消息链接\n   {msg_link}",
                level="error",
                category="失败",
                account=client,
            )


async def teardown(ctx):
    ctx.log.info("天空红包插件已停用")
