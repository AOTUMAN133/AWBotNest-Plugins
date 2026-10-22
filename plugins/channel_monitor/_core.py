"""channel_monitor 核心纯逻辑 —— 与平台/客户端解耦，可单测。

这里只放"不依赖 telethon / 不依赖 ctx"的判定逻辑：
  - 规则归一化与匹配
  - 关键词 / 正则过滤
  - 相册缓冲（按 quiet-window 合并）
  - 幂等判定
  - 状态文本
发送、调度、落盘都在 __init__.py / _sender.py 里做。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── 服务消息 ────────────────────────────────────────────────────────────
def is_service_message(msg) -> bool:
    """入群/退群/置顶等系统消息（无正文、不可转发）。

    Pyrogram 用 msg.service，Telethon 用 msg.action（MessageService），两者都认。
    """
    if getattr(msg, "service", None) is not None:
        return True
    return getattr(msg, "action", None) is not None


# ── peer 解析 ───────────────────────────────────────────────────────────
_TME_RE = re.compile(r"^(?:https?://)?t\.me/(?P<kind>c/)?(?P<target>[A-Za-z0-9_+/.-]+)/?$")


def resolve_peer(arg):
    """把 @user / t.me/x / t.me/c/123 / -100xxx / 纯数字 归一化。

    返回 str 或 int；无法识别返回 None。
    """
    arg = (arg or "").strip()
    if not arg:
        return None

    if arg.lstrip("-").isdigit():
        return int(arg)

    m = _TME_RE.match(arg)
    if m:
        # t.me/c/<内部id>/<msg>、t.me/<用户名>/<msg> 都只取会话部分
        target = m.group("target").rstrip("/").split("/")[0]
        # t.me/c/<id> 的 id 是去掉 -100 前缀的频道内部 id
        if m.group("kind"):
            return int(f"-100{target}") if target.isdigit() else None
        return target or None

    if arg.startswith("@"):
        arg = arg[1:]
    return arg or None


# ── 规则 ────────────────────────────────────────────────────────────────
@dataclass
class Rule:
    """一条「源 → 目标」转发规则。

    src_id / dst_id 由调用方解析后回填；解析失败时 error 非空，
    该规则不参与匹配，但不影响其他规则。
    """

    index: int
    source: str
    target: str
    enabled: bool = True
    src_id: int | None = None
    dst_id: int | None = None
    src_title: str = ""
    dst_title: str = ""
    error: str = ""

    @property
    def key(self) -> str:
        """稳定标识：源|目标。不随规则表重排序而漂移。"""
        return f"{self.src_id or self.source}|{self.dst_id or self.target}"

    @property
    def usable(self) -> bool:
        return self.enabled and not self.error and self.src_id is not None \
            and self.dst_id is not None


def normalize_rules(raw) -> tuple[list[Rule], list[str]]:
    """把配置里的 rules 列表转成 Rule 列表。

    返回 (rules, warnings)。配置错误只告警、不抛异常 —— 一行填错
    不该让整个插件起不来。
    """
    rules: list[Rule] = []
    warnings: list[str] = []
    for i, row in enumerate(raw or []):
        if not isinstance(row, dict):
            warnings.append(f"第 {i + 1} 行格式不对，已跳过")
            continue
        src_raw = (row.get("source") or "").strip()
        dst_raw = (row.get("target") or "").strip()
        if not src_raw or not dst_raw:
            warnings.append(f"第 {i + 1} 行源或目标为空，已跳过")
            continue
        enabled = row.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() not in ("", "0", "false", "no", "off")
        rules.append(
            Rule(
                index=i,
                source=src_raw,
                target=dst_raw,
                enabled=bool(enabled),
            )
        )
    return rules, warnings


def match_rules(chat_id, rules) -> list[Rule]:
    """找出 chat_id 命中且可用的规则（同一源可命中多条）。"""
    if chat_id is None:
        return []
    return [r for r in rules if r.usable and r.src_id == chat_id]


# ── 关键词 ──────────────────────────────────────────────────────────────
def compile_keywords(text: str) -> list[str]:
    """每行一个关键词，留空表示不过滤。大小写不敏感。"""
    return [line.strip().lower() for line in (text or "").splitlines() if line.strip()]


def passes_keywords(text: str, file_name: str, keywords) -> bool:
    """任一关键词命中即通过；关键词列表为空则全通过。"""
    if not keywords:
        return True
    blob = f"{text or ''} {file_name or ''}".lower()
    return any(k in blob for k in keywords)


# ── 过滤规则 ────────────────────────────────────────────────────────────
def compile_filters(drop_regex: str = "", replace_regex: str = ""):
    """把配置文本编译成正则。返回 (drops, replaces)。

    drop 行：一条 Python 正则，命中文字或文件名即跳过。
    replace 行：``正则|替换内容``。
    非法正则静默忽略（配置错误不该让监控崩掉）。
    """
    drops: list[re.Pattern] = []
    replaces: list[tuple[re.Pattern, str]] = []

    for line in (drop_regex or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            drops.append(re.compile(line, re.IGNORECASE))
        except re.error:
            continue

    for line in (replace_regex or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pattern, _, replacement = line.partition("|")
        try:
            replaces.append((re.compile(pattern, re.IGNORECASE), replacement))
        except re.error:
            continue

    return drops, replaces


def apply_filters(text: str, file_name: str, drops, replaces):
    """返回 (是否丢弃, 处理后的文字)。"""
    for rx in drops:
        if rx.search(text or "") or (file_name and rx.search(file_name)):
            return True, text
    for rx, replacement in replaces:
        if text:
            text = rx.sub(replacement, text)
    return False, text


# ── 相册缓冲 ────────────────────────────────────────────────────────────
class AlbumBuffer:
    """按 media_group_id 合并相册成员。

    Telethon 把相册成员逐条推送，没有整组事件，只能靠 quiet-window
    攒齐：最后一个成员到达后再等 window 秒没有新成员，就算齐了。
    用"最后到达时间"而不是"首次到达时间"，避免成员间隔大于 window
    时被切两半。

    时间由调用方注入（now），不内部读时钟 —— 保持可单测。
    """

    def __init__(self, window: float = 0.8):
        self.window = max(0.05, float(window))
        self._groups: dict = {}

    def add(self, msg, now: float) -> None:
        """把一条消息放进缓冲。没有 media_group_id 的不要调这里。"""
        gid = getattr(msg, "media_group_id", None)
        if not gid:
            return
        slot = self._groups.get(gid)
        if slot is None:
            slot = {"items": [], "last": now}
            self._groups[gid] = slot
        slot["items"].append(msg)
        slot["last"] = now

    def pop_ready(self, now: float) -> list[list]:
        """取出所有已安静的相册组（旧→新顺序保持）。"""
        ready = []
        for gid, slot in list(self._groups.items()):
            if now - slot["last"] >= self.window:
                ready.append(slot["items"])
                del self._groups[gid]
        ready.sort(key=lambda items: items[0].id)
        return ready

    def flush_all(self) -> list[list]:
        """停用/收尾时强制取出所有残余组。"""
        ready = [slot["items"] for slot in self._groups.values()]
        self._groups.clear()
        ready.sort(key=lambda items: items[0].id)
        return ready

    def pending_count(self) -> int:
        return sum(len(s["items"]) for s in self._groups.values())


# ── 幂等 ────────────────────────────────────────────────────────────────
def should_skip(msg_id, last_id) -> bool:
    """已处理过的消息（断线重连会重推）直接丢弃。"""
    if not msg_id or not last_id:
        return False
    return int(msg_id) <= int(last_id)


def truthy(value, default: bool = False) -> bool:
    """配置里的布尔值可能是 True / "true" / "0" / "" 等形态。

    平台存表单值时可能落成字符串，bool("false") 是 True，必须显式判定。
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    return text not in ("0", "false", "no", "off", "none", "null")


# ── 链接 ────────────────────────────────────────────────────────────────
def build_link(src_id, msg_id) -> str:
    """构造源消息链接。

    私有频道用 t.me/c/<内部id>/<msg>，成员可点开；拿不到 id 就返回空。
    """
    try:
        sid = int(src_id)
        mid = int(msg_id)
    except (TypeError, ValueError):
        return ""
    if mid <= 0:
        return ""
    s = str(abs(sid))
    if s.startswith("100") and len(s) > 3:
        s = s[3:]
    return f"https://t.me/c/{s}/{mid}"


# ── 状态文本 ────────────────────────────────────────────────────────────
def render_status(rows) -> str:
    """rows: [dict(name, target, last_id, sent, skipped, failed, state)]"""
    if not rows:
        return "还没有配置转发规则"
    lines = ["📡 频道监控转发"]
    for i, r in enumerate(rows, 1):
        lines.append("")
        lines.append(f"{i}. {r.get('name') or '?'} → {r.get('target') or '?'}")
        if r.get("error"):
            lines.append(f"   ⚠️ {r['error']}")
            continue
        lines.append(
            f"   最近ID {r.get('last_id') or '-'} · 成功 {r.get('sent', 0)}"
            f" · 跳过 {r.get('skipped', 0)} · 失败 {r.get('failed', 0)}"
        )
        lines.append(f"   状态：{r.get('state') or '运行中 ▶'}")
    return "\n".join(lines)
