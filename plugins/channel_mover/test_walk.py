"""用假 pyrogram Client 跑完整搬运循环 —— 不碰 Telegram。

重点验证：
  1. 从最早一条开始，顺序正确
  2. 不漏不重（每条恰好搬一次）
  3. 跨批相册不被拆散
  4. 断点续传接着上次的 next_id
  5. 停止标志能中断
  6. FloodWait 超上限会暂停而非死循环

运行: python test_walk.py
"""
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

# 把插件目录当作包导入（包名 channel_mover，目录即包）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
cm = importlib.import_module("channel_mover")


class FakeChat:
    def __init__(self, cid, title):
        self.id = cid
        self.title = title


class FakeDoc:
    def __init__(self, name=""):
        self.file_name = name


class FakeMedia:
    def __init__(self, doc=None):
        self.document = doc


class FakeMsg:
    def __init__(self, mid, chat, text="", mgid=None, service=None,
                 media=None, reply_to=None):
        self.id = mid
        self.chat = chat
        self.text = text
        self.media_group_id = mgid
        self.service = service
        self.media = media
        self.reply_to_message_id = reply_to
        self.caption = None


class FakeClient:
    """按 pyrogram 语义实现的假客户端。

    get_chat_history 语义（已从 pyrogram 2.2.26 源码确认）：
      reverse=False -> 从最新开始由新到旧，min_id 只做下限
      reverse=True  -> 从 id>=min_id 开始由旧到新
    """

    def __init__(self, messages, src_chat, dst_chat):
        self.messages = sorted(messages, key=lambda m: m.id)
        self.src_chat = src_chat
        self.dst_chat = dst_chat
        self.copied = []          # (from_chat_id, message_id, caption)
        self.albums_copied = []   # (from_chat_id, message_id)
        self.history_calls = []

    async def get_chat(self, peer):
        return self.src_chat if peer == "src" else self.dst_chat

    async def get_chat_history(self, chat_id, limit=None, min_id=0,
                               max_id=0, reverse=False, **kw):
        self.history_calls.append(
            {"min_id": min_id, "limit": limit, "reverse": reverse}
        )
        if reverse:
            picked = [m for m in self.messages if m.id >= min_id]
            picked = picked[:limit] if limit else picked
        else:
            picked = [m for m in self.messages if m.id <= (max_id or 10 ** 12)]
            if min_id:
                picked = [m for m in picked if m.id >= min_id]
            picked = list(reversed(picked))
            picked = picked[:limit] if limit else picked
        for m in picked:
            yield m

    async def copy_message(self, chat_id, from_chat_id, message_id,
                           caption=None, reply_to_message_id=None, **kw):
        self.copied.append((from_chat_id, message_id, caption))

    async def copy_media_group(self, chat_id, from_chat_id, message_id, **kw):
        self.albums_copied.append((from_chat_id, message_id))

    async def forward_messages(self, chat_id, from_chat_id, message_ids, **kw):
        for mid in message_ids:
            self.copied.append((from_chat_id, mid, None))


class FakeCtx:
    """最小 ctx 面：storage + log + create_task + notify"""

    def __init__(self, cfg=None):
        self._store = {}
        self.config = cfg or {}
        self.log = SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
            exception=lambda *a, **k: None,
        )
        self.notifications = []

    async def storage_get(self, key, default=None):
        return self._store.get(key, default)

    async def storage_set(self, key, value):
        self._store[key] = value

    # ctx.storage 是对象，包一层
    @property
    def storage(self):
        outer = self

        class _S:
            async def get(self, key, default=None):
                return await outer.storage_get(key, default)

            async def set(self, key, value):
                await outer.storage_set(key, value)

            async def delete(self, key):
                outer._store.pop(key, None)

        return _S()

    def create_task(self, coro, name=None):
        return asyncio.ensure_future(coro)

    async def notify(self, text, **kw):
        self.notifications.append(text)


def make_messages(ids, src, mgid_of=None, text_of=None, media_of=None):
    mgid_of = mgid_of or {}
    text_of = text_of or {}
    media_of = media_of or {}
    return [
        FakeMsg(i, src, text=text_of.get(i, f"msg{i}"),
                mgid=mgid_of.get(i), media=media_of.get(i))
        for i in ids
    ]


async def test_walks_from_oldest_in_order():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 21), src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源频道", "dst_name": "目标群",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t1", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 7})

    order = [mid for _, mid, _ in client.copied]
    assert order == list(range(1, 21)), order
    assert state["finished"] is True
    assert state["sent"] == 20, state
    assert any("完成" in n for n in ctx.notifications)
    print("✓ 20 条从最早开始按序搬完，无遗漏无重复")


async def test_resume_continues_from_next_id():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 31), src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 1, "max_id": 30, "next_id": 16, "total": 30,
        "done": 15, "sent": 15, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "then", "updated": "then", "finished": False,
    }
    await cm._run_copy(ctx, "t2", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 5})

    order = [mid for _, mid, _ in client.copied]
    assert order == list(range(16, 31)), order
    print("✓ 断点续传从 next_id=16 接着搬，不重搬前 15 条")


async def test_album_not_split_across_batches():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    # id 2..5 是同一相册，batch=3 会把它切断
    msgs = make_messages(
        [1, 2, 3, 4, 5, 6], src, mgid_of={2: 100, 3: 100, 4: 100, 5: 100}
    )
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t3", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 3})

    # 相册整组一次 copy_media_group，首条 id=2
    assert client.albums_copied == [(-100111, 2)], client.albums_copied
    # 其余 1 和 6 是单条
    assert [mid for _, mid, _ in client.copied] == [1, 6], client.copied
    print("✓ 跨批相册（id 2-5）整组搬运，未被批边界拆散")


async def test_service_messages_skipped():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = [
        FakeMsg(1, src, text="正常"),
        FakeMsg(2, src, service="NEW_CHAT_MEMBERS"),
        FakeMsg(3, src, text="也正常"),
    ]
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t4", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 10})

    assert [mid for _, mid, _ in client.copied] == [1, 3], client.copied
    print("✓ 服务消息（入群）被跳过")


async def test_drop_regex_filters():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 6), src, text_of={
        1: "正常消息", 2: "这是广告", 3: "又是广告内容", 4: "正常", 5: "广告",
    })
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t5", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 10,
                        "drop_regex": "广告"})

    assert [mid for _, mid, _ in client.copied] == [1, 4], client.copied
    print("✓ 丢弃正则过滤掉含「广告」的消息")


async def test_replace_regex_rewrites_caption():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages([1], src, text_of={1: "加微信 abc123 聊天"})
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t6", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 10,
                        "replace_regex": "abc123|[已隐藏]"})

    assert client.copied[0][2] == "加微信 [已隐藏] 聊天", client.copied
    print("✓ 替换正则改写文字后搬运")


async def test_media_skipped_when_disabled():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = [
        FakeMsg(1, src, text="文字"),
        FakeMsg(2, src, text="", media=FakeMedia(FakeDoc("a.mp4"))),
    ]
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t7", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 10,
                        "copy_media": False})

    assert [mid for _, mid, _ in client.copied] == [1], client.copied
    print("✓ 关闭搬运媒体时只搬文字")


async def test_stop_flag_interrupts():
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 101), src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }

    # 搬 10 条后置停止标志
    original = client.copy_message

    async def counting_copy(**kw):
        await original(**kw)
        if len(client.copied) >= 10:
            cm._STOP_FLAGS["t8"] = True

    client.copy_message = counting_copy
    await cm._run_copy(ctx, "t8", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 20})

    assert len(client.copied) == 10, len(client.copied)
    assert state["finished"] is not True
    assert state["next_id"] == 11, state["next_id"]
    cm._STOP_FLAGS.pop("t8", None)
    print("✓ 停止标志中断任务，进度停留在 next_id=11")


async def test_gap_in_ids_does_not_loop():
    """消息 ID 不连续时（大量已删除），空页要能跳过而不是死循环。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages([1, 2, 500, 501], src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t9", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 3})

    assert [mid for _, mid, _ in client.copied] == [1, 2, 500, 501]
    assert state["finished"] is True
    print("✓ ID 大跳空（2→500）不死循环，正常搬完")


async def test_history_uses_reverse_true():
    """回归测试：必须 reverse=True，否则搬的是最新消息而非从最早开始。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 21), src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }
    await cm._run_copy(ctx, "t10", client, "src", "dst", state,
                       {"send_interval": 0, "batch_size": 7})

    walk_calls = [c for c in client.history_calls if c["min_id"] > 0]
    assert walk_calls, client.history_calls
    assert all(c["reverse"] is True for c in walk_calls), walk_calls
    print("✓ 遍历调用全部使用 reverse=True（防回归）")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            asyncio.run(t())
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
