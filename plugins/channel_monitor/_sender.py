"""channel_monitor 发送层 —— 只跟 Telethon 客户端打交道。

与 channel_mover 的差异：
  - 不设置 silent（原实现里 silent=True 会让转发出去的消息被静音）
  - FloodWait 超限抛 Paused，由编排层决定暂停并通知
  - 单条/相册统一入口，相册用 as_album=True 整组发
"""
from __future__ import annotations

import asyncio

# Telethon 抛 FloodWaitError，Pyrogram 抛 FloodWait —— 都按名字判断，
# 避免为了一个异常类型去 import 框架。
_FLOOD_NAMES = {"FloodWaitError", "FloodWait", "SlowModeWaitError", "SlowModeWait"}


class Paused(Exception):
    """FloodWait 超过配置上限，本规则应当暂停。"""

    def __init__(self, seconds: int):
        super().__init__(f"FloodWait {seconds}s")
        self.seconds = int(seconds)


def flood_seconds(exc) -> int:
    """从限流异常里取等待秒数。取不到返回 0。"""
    for attr in ("seconds", "value", "x"):
        v = getattr(exc, attr, None)
        if not v:
            continue
        try:
            return int(v)
        except (TypeError, ValueError):
            continue
    return 0


async def with_flood_retry(factory, max_wait: int, log=None):
    """执行 factory()，遇 FloodWait 退避重试；超限抛 Paused。

    CancelledError 继承自 BaseException，不会被这里的 except Exception 吞掉。
    """
    while True:
        try:
            return await factory()
        except Exception as exc:  # noqa: BLE001 - 按类型名分流
            if type(exc).__name__ not in _FLOOD_NAMES:
                raise
            secs = flood_seconds(exc)
            if secs <= 0:
                raise
            if secs > max_wait:
                raise Paused(secs) from exc
            if log is not None:
                log.warning("[监控] FloodWait %ss，等待后重试", secs)
            await asyncio.sleep(secs + 1)


async def forward_one(client, dst, msg_id: int, src_peer):
    """服务端转发单条消息（drop_author=True 即不带转发来源头）。"""
    return await client.forward_messages(
        dst, [msg_id], from_peer=src_peer, drop_author=True,
    )


async def forward_album(client, dst, msg_ids, src_peer):
    """整组转发相册。as_album=True 让 Telegram 重新合并成一条相册。"""
    return await client.forward_messages(
        dst, list(msg_ids), from_peer=src_peer,
        drop_author=True, as_album=True,
    )


def _last_message(sent):
    """forward_messages 单条返回 Message，多条返回 list。统一取"最后一条"。"""
    if sent is None:
        return None
    if isinstance(sent, (list, tuple)):
        return sent[-1] if sent else None
    # Telethon 的 TotalList 也是 list 子类，上面已覆盖
    return sent


async def append_link(sent, link: str):
    """在刚转发出去的消息末尾追加一行来源链接。

    转发是服务端复制，没法在发送时改文本，只能在事后 edit。
    失败不抛 —— 链接只是附加信息，不该把成功的一次转发算成失败。
    """
    if not link:
        return
    msg = _last_message(sent)
    if msg is None:
        return
    try:
        body = getattr(msg, "text", "") or getattr(msg, "message", "") or ""
        await msg.edit(f"{body}\n{link}" if body else link)
    except Exception:  # noqa: BLE001 - 附加信息，失败忽略
        return
