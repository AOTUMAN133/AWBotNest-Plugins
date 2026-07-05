# =============================================================================
# 学习插件：社交图谱（记录我跟谁聊过天）
# =============================================================================
import time
from typing import Optional

# 内存缓存：chat_id -> {user_id -> {name, count, last_ts}}
_cache: dict[int, dict[int, dict]] = {}
_SAVE_KEY_TPL = "social:{}"  # social:<chat_id> → list


def _ensure(chat_id: int):
    if chat_id not in _cache:
        _cache[chat_id] = {}


def record(chat_id: int, user_id: int, name: str, kv):
    """记录一次与 user 的互动。"""
    _ensure(chat_id)
    entry = _cache[chat_id].get(user_id)
    if entry:
        entry["count"] = entry.get("count", 0) + 1
        entry["last_ts"] = time.time()
        entry["name"] = name
    else:
        _cache[chat_id][user_id] = {
            "user_id": user_id,
            "name": name,
            "count": 1,
            "last_ts": time.time(),
        }
    # 持久化
    _persist(chat_id, kv)


def get_frequent(chat_id: int, kv, min_count: int = 3) -> list[dict]:
    """获取聊天超过 min_count 次的活跃联系人。"""
    raw = _load(chat_id, kv)
    return [u for u in raw if u.get("count", 0) >= min_count]


def get_all(chat_id: int, kv) -> list[dict]:
    """获取该群的所有社交记录。"""
    return _load(chat_id, kv)


def cross_group_frequent(kv, chat_ids: list[int], min_count: int = 3) -> dict[int, dict]:
    """跨群汇总：返回 {user_id: {total_count, groups, name}}。"""
    summary: dict[int, dict] = {}
    for cid in chat_ids:
        for u in _load(cid, kv):
            uid = u["user_id"]
            if uid not in summary:
                summary[uid] = {"total_count": 0, "groups": set(), "name": u.get("name", "")}
            summary[uid]["total_count"] += u.get("count", 0)
            summary[uid]["groups"].add(cid)
    # 过滤低频
    return {uid: info for uid, info in summary.items()
            if info["total_count"] >= min_count}


def _load(chat_id: int, kv) -> list[dict]:
    """从 kv 加载社交数据到缓存（如已缓存则跳过）。"""
    if chat_id not in _cache:
        raw = kv.get(_SAVE_KEY_TPL.format(chat_id), [])
        _cache[chat_id] = {u["user_id"]: u for u in raw}
    return list(_cache[chat_id].values())


def _persist(chat_id: int, kv):
    """将缓存刷回 kv。"""
    raw = list(_cache.get(chat_id, {}).values())
    kv.set(_SAVE_KEY_TPL.format(chat_id), raw)


def clear():
    _cache.clear()
