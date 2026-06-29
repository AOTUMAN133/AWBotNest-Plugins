# =============================================================================
# 红包插件 - 抢包核心逻辑（按钮红包）
#
# 两类按钮红包处理：
#   1. 按钮红包（HDSKY 拼手气红包）：点击「抢红包」内联按钮。
#   2. 编号按钮红包（癫影积分红包）：逐个点击未抢的数字按钮。
#
# 口令红包逻辑已拆到 yingchao_redpacket 插件，本文件不再包含。
# =============================================================================
from __future__ import annotations

import re


# ─── 文本工具 ────────────────────────────────────────────────────────────

def extract_text(message) -> str:
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()


# ─── 按钮查找 ────────────────────────────────────────────────────────────

def find_snatch_button(message):
    """在内联键盘里找「抢红包」按钮，返回 (row, col) 或 None。"""
    markup = getattr(message, "reply_markup", None)
    if not markup or not getattr(markup, "inline_keyboard", None):
        return None
    for r, row in enumerate(markup.inline_keyboard):
        for c, btn in enumerate(row):
            text = (getattr(btn, "text", "") or "")
            if "抢红包" in text or "抢 红 包" in text or text.strip() in ("抢", "领取红包"):
                return (r, c)
    return None


def find_numbered_buttons(message) -> list[tuple[int, int]]:
    """返回所有未抢数字按钮的 (row, col) 列表（癫影积分红包）。"""
    result: list[tuple[int, int]] = []
    markup = getattr(message, "reply_markup", None)
    if not markup or not getattr(markup, "inline_keyboard", None):
        return result
    for r, row in enumerate(markup.inline_keyboard):
        for c, btn in enumerate(row):
            text = (getattr(btn, "text", "") or "").strip()
            if re.search(r"[一-鿿]", text):  # 含中文 → 管理员按钮，跳过
                continue
            if re.match(r"^[✅☑]", text):    # ✅/☑ 已抢，跳过
                continue
            if re.search(r"\d$", text):               # 末尾数字 → 未抢
                result.append((r, c))
    return result


def is_lucky_packet(message) -> bool:
    """判断是否为拼手气（按钮）红包消息。"""
    text = extract_text(message)
    if "拼手气红包" in text:
        return True
    if "红包" in text and ("份数" in text or "总银元" in text or "总金额" in text):
        return True
    return False


def is_snatch_success(result_text: str) -> bool:
    """判断点击结果是否表示抢包成功。"""
    if not result_text or result_text in ("None", ""):
        return False
    return any(k in result_text for k in ("抢到了", "抢到", "恭喜", "你获得", "领取成功", "积分已到账"))


def acct_name(client) -> str:
    me = getattr(client, "me", None)
    if not me:
        return "未知账号"
    if getattr(me, "username", None):
        return f"{me.first_name}(@{me.username})"
    return f"{me.first_name}(ID:{me.id})"
