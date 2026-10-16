"""channel_mover 核心逻辑测试 —— 用假消息对象，不碰 Telegram。

运行: python tests/channel_mover/test_core.py
"""
import asyncio
import importlib
import sys
from pathlib import Path

# 测试在 tests/ 下，被测模块在 plugins/channel_mover/ 下，按包导入
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins"))

_core = importlib.import_module("channel_mover._core")
apply_filters = _core.apply_filters
build_progress_text = _core.build_progress_text
compile_filters = _core.compile_filters
group_albums = _core.group_albums
is_finished = _core.is_finished
is_service_message = _core.is_service_message
next_id_after = _core.next_id_after
resolve_peer = _core.resolve_peer
trailing_open_album = _core.trailing_open_album


class FakeMsg:
    """模拟 pyrogram Message 的最小面"""

    def __init__(self, mid, mgid=None, service=None, text=""):
        self.id = mid
        self.media_group_id = mgid
        self.service = service
        self.text = text


def test_group_albums_basic():
    msgs = [FakeMsg(1), FakeMsg(2, mgid=100), FakeMsg(3, mgid=100), FakeMsg(4)]
    groups = group_albums(msgs)
    assert groups == [[msgs[0]], [msgs[1], msgs[2]], [msgs[3]]], groups
    print("✓ 相册分组：单条/相册/单条")


def test_group_albums_adjacent_same_gid():
    """两个不同相册的成员 id 不相邻，但分组逻辑只看 media_group_id。"""
    msgs = [FakeMsg(1, mgid=100), FakeMsg(2, mgid=100), FakeMsg(3, mgid=200), FakeMsg(4, mgid=200)]
    groups = group_albums(msgs)
    assert groups == [[msgs[0], msgs[1]], [msgs[2], msgs[3]]], groups
    print("✓ 相册分组：两个相邻相册正确切开")


def test_group_albums_no_keep():
    msgs = [FakeMsg(1), FakeMsg(2, mgid=100), FakeMsg(3, mgid=100)]
    groups = group_albums(msgs, keep_albums=False)
    assert groups == [[msgs[0]], [msgs[1]], [msgs[2]]], groups
    print("✓ 关闭相册保持时全部拆散")


def test_trailing_open_album():
    """跨批未完结相册必须能被识别，否则相册会被拆成两次发送。"""
    msgs = [FakeMsg(1), FakeMsg(2, mgid=100), FakeMsg(3, mgid=100)]
    groups = group_albums(msgs)
    assert trailing_open_album(groups) == [msgs[1], msgs[2]]
    print("✓ 跨批未完结相册被识别")

    closed = [FakeMsg(1, mgid=100), FakeMsg(2, mgid=100), FakeMsg(3)]
    assert trailing_open_album(group_albums(closed)) is None
    print("✓ 已完结的末尾组不会被误判")


def test_next_id_after_uses_id_not_count():
    """消息 ID 不连续，next_id 必须是最后一条 id+1，不能累加条数。"""
    group = [FakeMsg(10), FakeMsg(15), FakeMsg(23)]
    assert next_id_after(group) == 24, next_id_after(group)
    print("✓ next_id = 最后一条 id+1（非累加条数）")


def test_is_finished():
    assert is_finished(101, 100) is True
    assert is_finished(100, 100) is False
    assert is_finished(99, 100) is False
    print("✓ 完成判定：next_id > max_id")


def test_is_service_message():
    assert is_service_message(FakeMsg(1, service="NEW_CHAT_MEMBERS")) is True
    assert is_service_message(FakeMsg(2)) is False
    print("✓ 服务消息判定")


def test_resolve_peer():
    assert resolve_peer("@somechannel") == "somechannel"
    assert resolve_peer("somechannel") == "somechannel"
    assert resolve_peer("t.me/somechannel") == "somechannel"
    assert resolve_peer("https://t.me/somechannel") == "somechannel"
    assert resolve_peer("-1001234567890") == -1001234567890
    assert resolve_peer("1234567890") == 1234567890
    # t.me/c/<id> 的 id 是频道内部 id，需补 -100 前缀
    assert resolve_peer("t.me/c/1234567890") == -1001234567890
    assert resolve_peer("") is None
    assert resolve_peer("   ") is None
    print("✓ peer 解析（@user / t.me / t.me/c / -100xxx）")


def test_compile_and_apply_filters_drop():
    drops, replaces = compile_filters(drop_regex="广告|垃圾")
    assert len(drops) == 1 and replaces == []
    dropped, text = apply_filters("这是广告内容", "", drops, replaces)
    assert dropped is True
    dropped, _ = apply_filters("正常消息", "", drops, replaces)
    assert dropped is False
    print("✓ 丢弃正则命中/未命中")


def test_filters_match_filename():
    drops, _ = compile_filters(drop_regex=r"\.exe$")
    dropped, _ = apply_filters("看看这个", "virus.exe", drops, [])
    assert dropped is True
    dropped, _ = apply_filters("看看这个", "movie.mp4", drops, [])
    assert dropped is False
    print("✓ 丢弃正则匹配文件名")


def test_filters_replace():
    drops, replaces = compile_filters(replace_regex="AAA|X\nBBB|Z\n手机号|[REDACTED]")
    assert len(replaces) == 3
    _, text = apply_filters("AAA 和 BBB", "", drops, replaces)
    assert text == "X 和 Z", text
    _, text = apply_filters("我的手机号是13800000000", "", drops, replaces)
    assert "手机号" not in text and "13800000000" in text, text
    print("✓ 替换正则多行生效")


def test_filters_invalid_regex_ignored():
    """非法正则应被忽略而不是让搬运崩掉。"""
    drops, replaces = compile_filters(
        drop_regex="(未闭合\n[a-", replace_regex="*bad|x\n好正则|替换"
    )
    assert drops == [], drops
    assert len(replaces) == 1, replaces
    print("✓ 非法正则静默忽略")


def test_filters_empty_text_no_replace():
    """纯媒体消息无文字时不该被替换逻辑碰。"""
    drops, replaces = compile_filters(replace_regex="x|y")
    dropped, text = apply_filters("", "file.mp4", drops, replaces)
    assert dropped is False and text == ""
    print("✓ 空文字不触发替换")


def test_build_progress_text():
    state = {
        "src_name": "源频道", "dst_name": "目标群",
        "total": 1000, "done": 250, "sent": 200, "skipped": 40, "failed": 10,
        "next_id": 260, "started": "10-16 20:00:00", "updated": "10-16 20:05:00",
    }
    text = build_progress_text(state)
    assert "250/1000" in text and "25%" in text
    assert "运行中" in text
    print("✓ 进度文本（百分比 + 运行中）")

    state["finished"] = True
    assert "已完成" in build_progress_text(state)
    state["finished"] = False
    state["paused_reason"] = "FloodWait 900s"
    assert "已暂停" in build_progress_text(state)
    assert build_progress_text(None) == "还没有搬运任务"
    print("✓ 进度文本（已完成/已暂停/空）")


def test_progress_text_zero_total():
    """total=0 时不能除零。"""
    text = build_progress_text({"total": 0, "done": 0})
    assert "-" in text
    print("✓ total=0 不除零")


async def _fake_agen(items):
    for it in items:
        yield it


async def test_pagination_walk():
    """模拟分页遍历：跨批相册必须靠 pending 拼回完整，不能拆散。"""

    all_msgs = [
        FakeMsg(1), FakeMsg(2, mgid=100), FakeMsg(3, mgid=100),
        FakeMsg(4, mgid=100), FakeMsg(5), FakeMsg(6),
    ]
    batch_size = 3
    pages = [all_msgs[0:3], all_msgs[3:6]]

    collected = []
    pending = []
    for page in pages:
        merged = pending + page
        groups = group_albums(merged)
        open_album = trailing_open_album(groups)
        if open_album:
            groups = groups[:-1]
            pending = open_album
        else:
            pending = []
        collected.extend(groups)
    if pending:
        collected.append(pending)

    # 关键断言：id 2,3,4 是同一相册，必须在一组里，不能被批边界切开
    assert len(collected) == 4, [[m.id for m in g] for g in collected]
    assert [m.id for m in collected[0]] == [1]
    assert [m.id for m in collected[1]] == [2, 3, 4], [m.id for m in collected[1]]
    assert [m.id for m in collected[2]] == [5]
    assert [m.id for m in collected[3]] == [6]
    print("✓ 分页遍历：跨批相册完整不拆散")


async def test_no_duplicate_no_gap():
    """分页推进必须既不重复也不漏：每条消息恰好出现一次。"""

    all_msgs = [FakeMsg(i) for i in range(1, 51)]
    batch_size = 7
    cursor = 0
    seen = []
    idx = 0
    pending = []
    while idx < len(all_msgs):
        page = all_msgs[idx: idx + batch_size]
        idx += batch_size
        merged = pending + page
        groups = group_albums(merged)
        open_album = trailing_open_album(groups)
        if open_album:
            groups = groups[:-1]
            pending = open_album
        else:
            pending = []
        for g in groups:
            seen.append(g[0].id)
            cursor = next_id_after(g)
    if pending:
        seen.append(pending[0].id)
    assert seen == list(range(1, 51)), seen
    assert cursor == 51
    print("✓ 50 条分 7 批：无重复无遗漏（50 条全到）")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            if asyncio.iscoroutinefunction(t):
                asyncio.run(t())
            else:
                t()
        except AssertionError as e:
            failed += 1
            print(f"✗ {t.__name__} 失败: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"✗ {t.__name__} 异常: {e!r}")
    print()
    print(f"共 {len(tests)} 项，失败 {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
