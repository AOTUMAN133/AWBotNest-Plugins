# =============================================================================
# 多站点转账 - 站点配置解析 + 消息解析 + 金额提取
#
# 这里只放无副作用的纯工具：站点列表解析、转账方向判定、金额提取、对手方解析。
# 不 import pyrogram / core / config —— 运行期 Message 对象由调用方（__init__.py）传入，
# 我们只读它的属性（pyrogram Message 的标准字段）。
#
# 各站点的共性（已确认）：群里的「转账 bot」发一条确认消息，消息处在一条回复链上：
#   GET（别人转给我）：bot确认 → 回复 → 对方的「+金额」消息 → 回复 → 我的原始消息
#       → message.reply_to_message.reply_to_message.from_user.is_self 为真
#       → 对手方（转入方）= message.reply_to_message.from_user
#   PAY（我转给别人）：bot确认 → 回复 → 我的「+金额」消息 → 回复 → 对方的原始消息
#       → message.reply_to_message.from_user.is_self 为真
#       → 对手方（收款方）= message.reply_to_message.reply_to_message.from_user
# 金额来源两种：① 对 bot 文本跑正则（默认）；② 取回复链里的「+金额」消息（parser=plus）。
# hdsky 形态特殊，由 __init__.py 里的专用解析处理，本模块只负责识别它的 parser 标记。
# =============================================================================

import re
from typing import Optional, NamedTuple

# 金额默认正则：抓文本里第一个数字（含小数）
_DEFAULT_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)")
# 「+金额」格式
_PLUS_RE = re.compile(r"^\s*\+?\s*(\d+(?:\.\d+)?)\s*$")


class SiteConfig(NamedTuple):
    """单个站点的配置。"""
    chat_id: int          # 群组 ID
    site_name: str        # 站点标识（聚合排行榜按此分组）
    bot_id: int           # 该群转账 bot 的数字 ID（0 = 不校验发送者）
    bonus_name: str       # 货币单位（爆米花/魔力值/茉莉…）
    amount_re: re.Pattern # 金额正则（parser=reply 时用）
    parser: str           # "reply"（默认，正则抓 bot 文本，抓不到回退 +金额）
                          # | "plus"（强制取回复链里的 +金额 消息）
                          # | "hdsky"（实体解析，专用分支）


def parse_sites(raw: str) -> dict[int, list[SiteConfig]]:
    """解析多行站点配置文本，返回 {chat_id: [SiteConfig, ...]}。

    每行格式（| 分隔，两端空白自动去除）：
        群ID | 站点名 | botID | 奖励名 [ | 金额正则 ] [ | parser ]

    - 金额正则可留空（用默认）；parser 可留空（默认 reply）。
    - 同一群可能配多个站点（少见），故 value 用 list。
    - `#` 开头或空行忽略。
    """
    result: dict[int, list[SiteConfig]] = {}
    for line in str(raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        try:
            chat_id = int(parts[0])
            bot_id = int(parts[2]) if parts[2] else 0
        except ValueError:
            continue
        site_name = parts[1]
        bonus_name = parts[3]
        amount_pat = parts[4] if len(parts) >= 5 and parts[4] else ""
        parser = parts[5].lower() if len(parts) >= 6 and parts[5] else "reply"
        try:
            amount_re = re.compile(amount_pat) if amount_pat else _DEFAULT_AMOUNT_RE
        except re.error:
            amount_re = _DEFAULT_AMOUNT_RE
        cfg = SiteConfig(chat_id, site_name, bot_id, bonus_name, amount_re, parser)
        result.setdefault(chat_id, []).append(cfg)
    return result


def _from_user_is_self(msg) -> bool:
    return bool(msg and msg.from_user and getattr(msg.from_user, "is_self", False))


def detect_direction(message) -> Optional[str]:
    """根据回复链判定方向：'in'（转入）/ 'out'（转出）/ None（不是转账确认）。

    GET/in : message.reply_to_message.reply_to_message.from_user.is_self
    PAY/out: message.reply_to_message.from_user.is_self
    注意：先判 in（更深一层），避免 out 误判。
    """
    rtm = getattr(message, "reply_to_message", None)
    if not rtm:
        return None
    rtm2 = getattr(rtm, "reply_to_message", None)
    if _from_user_is_self(rtm2):
        return "in"
    if _from_user_is_self(rtm):
        return "out"
    return None


def counterparty_message(message, direction: str):
    """返回承载对手方信息的那条消息（其 from_user 即转入方/收款方）。"""
    rtm = getattr(message, "reply_to_message", None)
    if not rtm:
        return None
    if direction == "in":
        return rtm                                   # 对方的 +金额 消息
    return getattr(rtm, "reply_to_message", None)    # 对方的原始消息


def plus_amount_message(message, direction: str):
    """parser=plus 时，承载「+金额」文本的那条消息。

    GET：别人回复我发的 +金额 → message.reply_to_message
    PAY：我回复别人发的 +金额 → message.reply_to_message
    两种方向「+金额」都在 message.reply_to_message。
    """
    return getattr(message, "reply_to_message", None)


def extract_amount_from_text(text: Optional[str], pattern: re.Pattern) -> Optional[str]:
    """用站点正则从文本里抓金额；抓不到返回 None。"""
    if not text:
        return None
    m = pattern.search(text)
    if not m:
        return None
    # 优先取第一个捕获组，没有分组就取整体匹配
    return m.group(1) if m.groups() else m.group(0)


def extract_plus_amount(text: Optional[str]) -> Optional[str]:
    """从「+888 / 888」这类文本里抓金额。"""
    if not text:
        return None
    m = _PLUS_RE.match(text.strip())
    return m.group(1) if m else None


def user_identity(msg) -> tuple[int, str]:
    """从一条消息的 from_user 解析 (user_id, user_name)。

    user_id 取不到时为 0；user_name 优先 first+last，回退 username/用户ID。
    """
    fu = getattr(msg, "from_user", None) if msg else None
    if not fu:
        return 0, "未知用户"
    user_id = getattr(fu, "id", 0) or 0
    parts = []
    if getattr(fu, "first_name", None):
        parts.append(fu.first_name)
    if getattr(fu, "last_name", None):
        parts.append(fu.last_name)
    name = " ".join(parts).strip()
    if not name or name.lower() in ("untitled", "none", "null"):
        uname = getattr(fu, "username", None)
        name = f"@{uname}" if uname else f"用户{user_id}"
    return user_id, name[:48]
