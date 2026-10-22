"""channel_monitor 纯逻辑单测 —— 不碰 Telegram、不碰平台。"""
import importlib
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins"))
cm_core = importlib.import_module("channel_monitor._core")

from channel_monitor._core import (  # noqa: E402
    AlbumBuffer,
    build_link,
    compile_filters,
    compile_keywords,
    is_service_message,
    match_rules,
    normalize_rules,
    passes_keywords,
    resolve_peer,
    should_skip,
    render_status,
)


# ── peer 解析 ───────────────────────────────────────────────────────────
def test_resolve_peer_variants():
    assert resolve_peer("-1001234567890") == -1001234567890
    assert resolve_peer("@somechannel") == "somechannel"
    assert resolve_peer("t.me/somechannel") == "somechannel"
    assert resolve_peer("https://t.me/somechannel/") == "somechannel"
    assert resolve_peer("t.me/c/1234567890/77") == -1001234567890
    assert resolve_peer("") is None
    assert resolve_peer("   ") is None


# ── 规则 ────────────────────────────────────────────────────────────────
def test_normalize_rules_skips_bad_rows():
    rules, warnings = normalize_rules([
        {"source": "-100111", "target": "-100222", "enabled": True},
        {"source": "", "target": "-100222"},          # 源为空
        "不是字典",                                     # 类型错
        {"source": "@a", "target": "@b"},              # 缺 enabled 默认开
    ])
    assert len(rules) == 2
    assert len(warnings) == 2
    assert rules[0].enabled is True
    assert rules[1].enabled is True


def test_normalize_rules_enabled_string():
    rules, _ = normalize_rules([
        {"source": "-1", "target": "-2", "enabled": "false"},
        {"source": "-3", "target": "-4", "enabled": "1"},
    ])
    assert rules[0].enabled is False
    assert rules[1].enabled is True


def test_match_rules_by_chat_id():
    rules, _ = normalize_rules([
        {"source": "-100111", "target": "-100222"},
        {"source": "-100111", "target": "-100333"},
        {"source": "-100999", "target": "-100222"},
    ])
    for r, sid, did in zip(rules, (-100111, -100111, -100999), (-100222, -100333, -100222)):
        r.src_id, r.dst_id = sid, did

    hits = match_rules(-100111, rules)
    assert len(hits) == 2, "同一个源可以命中多条规则"
    assert match_rules(-100555, rules) == []


def test_rule_key_is_stable_across_reorder():
    rules, _ = normalize_rules([
        {"source": "-100111", "target": "-100222"},
        {"source": "-100333", "target": "-100444"},
    ])
    for r, sid, did in zip(rules, (-100111, -100333), (-100222, -100444)):
        r.src_id, r.dst_id = sid, did
    keys = [r.key for r in rules]
    assert keys[0] != keys[1]
    # 重排后 key 不变（状态不会串到别的规则上）
    rules.reverse()
    assert [r.key for r in rules] == list(reversed(keys))


def test_disabled_rule_not_matched():
    rules, _ = normalize_rules([{"source": "-100111", "target": "-100222", "enabled": False}])
    rules[0].src_id, rules[0].dst_id = -100111, -100222
    assert match_rules(-100111, rules) == []


# ── 关键词 ──────────────────────────────────────────────────────────────
def test_keywords():
    kws = compile_keywords("115\n  夸克  \n\n")
    assert kws == ["115", "夸克"]
    assert passes_keywords("这是115分享", "", kws) is True
    assert passes_keywords("夸克网盘", "", kws) is True
    assert passes_keywords("百度网盘", "", kws) is False
    assert passes_keywords("", "", []) is True, "空关键词列表 = 全通过"


def test_keywords_match_filename():
    kws = compile_keywords("4k")
    assert passes_keywords("", "movie.4K.mkv", kws) is True


# ── 正则过滤 ────────────────────────────────────────────────────────────
def test_drop_and_replace():
    drops, replaces = compile_filters("广告|spam", "微信|QQ")
    dropped, _ = cm_core.apply_filters("这里全是广告", "", drops, replaces)
    assert dropped is True
    dropped, _ = cm_core.apply_filters("正常内容", "spam.txt", drops, replaces)
    assert dropped is True, "文件名命中也要丢"
    dropped, text = cm_core.apply_filters("加微信领资源", "", drops, replaces)
    assert dropped is False
    assert text == "加QQ领资源"


def test_invalid_regex_ignored():
    drops, replaces = compile_filters("(未闭合", "([bad|xx")
    assert drops == [] and replaces == []


# ── 服务消息 ────────────────────────────────────────────────────────────
def test_service_message():
    class M:
        service = None
        action = None
    assert is_service_message(M()) is False
    M.service = object()
    assert is_service_message(M()) is True
    M.service = None
    M.action = object()
    assert is_service_message(M()) is True, "Telethon 的 MessageService 用 action"


# ── 相册缓冲 ────────────────────────────────────────────────────────────
class Ref:
    def __init__(self, i, gid):
        self.id = i
        self.media_group_id = gid


def test_album_quiet_window():
    buf = AlbumBuffer(window=0.8)
    buf.add(Ref(1, "g"), now=0.0)
    buf.add(Ref(2, "g"), now=0.3)
    buf.add(Ref(3, "g"), now=0.6)

    assert buf.pop_ready(1.0) == [], "最后一个成员才到 0.4 秒，还没安静够"
    ready = buf.pop_ready(1.5)
    assert len(ready) == 1
    assert [m.id for m in ready[0]] == [1, 2, 3]


def test_album_members_spanning_window_stay_together():
    """成员间隔大于窗口也要整组：用"最后到达时间"而不是首次。"""
    buf = AlbumBuffer(window=0.5)
    buf.add(Ref(1, "g"), now=0.0)
    buf.add(Ref(2, "g"), now=0.9)
    assert buf.pop_ready(1.0) == []
    ready = buf.pop_ready(1.5)
    assert [m.id for m in ready[0]] == [1, 2]


def test_album_groups_independent():
    buf = AlbumBuffer(window=0.5)
    buf.add(Ref(1, "a"), now=0.0)
    buf.add(Ref(2, "b"), now=0.0)
    buf.add(Ref(3, "a"), now=0.1)
    ready = buf.pop_ready(1.0)
    assert sorted([m.id for m in ready[0]]) == [1, 3]
    assert [m.id for m in ready[1]] == [2]


def test_flush_all():
    buf = AlbumBuffer(window=10)
    buf.add(Ref(1, "g"), now=0.0)
    assert buf.pending_count() == 1
    ready = buf.flush_all()
    assert [m.id for m in ready[0]] == [1]
    assert buf.pending_count() == 0


# ── 幂等 ────────────────────────────────────────────────────────────────
def test_should_skip():
    assert should_skip(10, 10) is True
    assert should_skip(9, 10) is True
    assert should_skip(11, 10) is False
    assert should_skip(0, 10) is False, "没有 id 不该被当成重复"
    assert should_skip(10, 0) is False, "首次运行 last_id=0"


# ── 链接与状态 ──────────────────────────────────────────────────────────
def test_build_link():
    assert build_link(-1001234567890, 77) == "https://t.me/c/1234567890/77"
    assert build_link(-1001, 5) == "https://t.me/c/1/5"
    assert build_link(None, 5) == ""
    assert build_link(-100123, 0) == ""


def test_render_status():
    text = render_status([
        {"name": "源A", "target": "群A", "last_id": 100, "sent": 8,
         "skipped": 2, "failed": 0, "state": "运行中 ▶"},
        {"name": "源B", "target": "群B", "error": "解析失败：找不到频道"},
    ])
    assert "源A" in text and "群A" in text and "成功 8" in text
    assert "解析失败" in text
    assert render_status([]) == "还没有配置转发规则"
