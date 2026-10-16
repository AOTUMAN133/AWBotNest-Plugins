"""channel_mover 核心纯逻辑 —— 与平台/客户端解耦，可单测。

这里只放"不依赖 pyrogram / 不依赖 ctx"的判定与推进逻辑：
  - 相册分组
  - 过滤规则编译与应用
  - peer 参数解析
  - 服务消息判定
  - 分页推进（next_id 计算）
发送、下载、存储都在 __init__.py 里做。
"""
from __future__ import annotations

import re

def is_service_message(msg) -> bool:
    """入群/退群/置顶等系统消息（无正文、不可搬运）。

    kurigram/pyrogram 的 Message.service 是 MessageServiceType 枚举，非 None 即服务消息。
    """
    return getattr(msg, "service", None) is not None


# ── 相册分组 ─────────────────────────────────────────────────────────────
def group_albums(messages, keep_albums: bool = True):
    """把连续同一 media_group_id 的消息归为一组，保持原顺序。

    跨批边界时，调用方需自行把上一批末尾的未完结相册接到下一批开头，
    见 iter_pages() 的用法说明。
    """
    if not keep_albums:
        return [[m] for m in messages]

    groups: list[list] = []
    current: list = []
    for msg in messages:
        gid = getattr(msg, "media_group_id", None)
        if gid:
            if not current or getattr(current[0], "media_group_id", None) == gid:
                current.append(msg)
            else:
                groups.append(current)
                current = [msg]
        else:
            if current:
                groups.append(current)
                current = []
            groups.append([msg])
    if current:
        groups.append(current)
    return groups


def trailing_open_album(groups):
    """返回跨批未完结的相册组（最后一组且仍在累加中），没有则返回 None。

    判定：最后一组长度 >=2 且首尾 media_group_id 相同 —— 说明下一批可能还有同组成员。
    """
    if not groups:
        return None
    last = groups[-1]
    if len(last) < 2:
        return None
    gid = getattr(last[0], "media_group_id", None)
    if not gid:
        return None
    return last if getattr(last[-1], "media_group_id", None) == gid else None


# ── 过滤规则 ─────────────────────────────────────────────────────────────
def compile_filters(drop_regex: str = "", replace_regex: str = ""):
    """把配置文本编译成正则。返回 (drops, replaces)。

    drop 行：一条 Python 正则，命中文字或文件名即跳过。
    replace 行：``正则|替换内容``。
    非法正则静默忽略（配置错误不该让搬运崩掉）。
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
        if rx.search(text) or (file_name and rx.search(file_name)):
            return True, text
    for rx, replacement in replaces:
        if text:
            text = rx.sub(replacement, text)
    return False, text


# ── peer 解析 ────────────────────────────────────────────────────────────
_TME_RE = re.compile(r"^(?:https?://)?t\.me/(?P<kind>c/)?(?P<target>[A-Za-z0-9_+/.-]+)/?$")


def resolve_peer(arg: str):
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
        target = m.group("target")
        # t.me/c/<id> 的 id 是去掉 -100 前缀的频道内部 id
        if m.group("kind"):
            return int(f"-100{target}") if target.isdigit() else None
        return target

    if arg.startswith("@"):
        arg = arg[1:]
    return arg or None


# ── 分页推进 ─────────────────────────────────────────────────────────────
def next_id_after(group) -> int:
    """一组消息处理完后，下一批的起点。

    消息 ID 在频道里不连续（服务消息、已删除消息都占号），
    所以必须用"本组最后一条的 id + 1"，不能用组内条数累加。
    """
    return group[-1].id + 1


def is_finished(next_id: int, max_id: int) -> bool:
    """next_id 超过启动时记录的最新消息 ID，即搬运完成。"""
    return next_id > max_id


def build_progress_text(state: dict) -> str:
    """给用户看的进度文本。"""
    if not state:
        return "还没有搬运任务"
    total = state.get("total", 0) or 0
    done = state.get("done", 0) or 0
    pct = f"{done * 100 // total}%" if total else "-"
    lines = [
        f"源：{state.get('src_name', '?')}",
        f"目标：{state.get('dst_name', '?')}",
        f"进度：{done}/{total}（{pct}）",
        f"已搬 {state.get('sent', 0)} · 跳过 {state.get('skipped', 0)} · 失败 {state.get('failed', 0)}",
        f"下一消息 ID：{state.get('next_id', '-')}",
        f"开始于 {state.get('started', '-')} · 更新于 {state.get('updated', '-')}",
    ]
    if state.get("finished"):
        lines.append("状态：已完成 ✅")
    elif state.get("paused_reason"):
        lines.append(f"状态：已暂停（{state['paused_reason']}）")
    else:
        lines.append("状态：运行中 ▶")
    return "\n".join(lines)
