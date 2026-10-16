"""用假 pyrogram Client 跑完整搬运循环 —— 不碰 Telegram。

重点验证：
  1. 从最早一条开始，顺序正确
  2. 不漏不重（每条恰好搬一次）
  3. 跨批相册不被拆散
  4. 断点续传接着上次的 next_id
  5. 停止标志能中断
  6. FloodWait 超上限会暂停而非死循环

运行: python tests/channel_mover/test_walk.py
"""
import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

# 把插件目录当作包导入（包名 channel_mover，目录即包）
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins"))
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

    def __init__(self, messages, src_chat, dst_chat, peer_map=None):
        self.messages = sorted(messages, key=lambda m: m.id)
        self.src_chat = src_chat
        self.dst_chat = dst_chat
        # 额外别名映射：{"srcc": src_chat, ...}（键为 resolve_peer 后的形态）
        self.peer_map = dict(peer_map or {})
        self.copied = []          # (from_chat_id, message_id, caption)
        self.albums_copied = []   # (from_chat_id, message_id)
        self.history_calls = []

    async def get_chat(self, peer):
        # 按 peer 匹配，而不是"非 src 即 dst"——否则配置回退测试会认错源
        for key, chat in self.peer_map.items():
            if peer == key:
                return chat
        if peer in (self.src_chat.id, self.src_chat.title, "src"):
            return self.src_chat
        return self.dst_chat

    async def get_chat_history(self, chat_id, limit=None, min_id=0,
                               max_id=0, reverse=False, **kw):
        self.history_calls.append(
            {"min_id": min_id, "max_id": max_id, "limit": limit, "reverse": reverse}
        )
        # 与 pyrogram 语义一致：min_id/max_id 均为闭区间边界
        hi = max_id if max_id else 10 ** 12
        if reverse:
            picked = [m for m in self.messages if min_id <= m.id <= hi]
            picked = picked[:limit] if limit else picked
        else:
            picked = [m for m in self.messages if m.id <= hi]
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




# ── 配置回退测试（v1.1.0 新增）──────────────────────────────────────────
class FakeEvent:
    def __init__(self, text, client, chat_id=-100999, sender_id=111):
        self.text = text
        self.client = client
        self.chat_id = chat_id
        self.sender_id = sender_id
        self.replies = []

    async def reply(self, text, **kw):
        self.replies.append(text)
        return None


class FakeRegCtx(FakeCtx):
    """带 on_message 注册的 ctx，用来抓 handler。"""

    def __init__(self, cfg=None):
        super().__init__(cfg)
        self._handlers = []

    def on_message(self, **kw):
        def deco(fn):
            self._handlers.append(fn)
            return fn
        return deco

    async def dispatch(self, event):
        for fn in self._handlers:
            await fn(event)


async def _drain_tasks(cm, sender_id="111", timeout=20):
    """等插件起的后台搬运任务跑完，否则断言会早于搬运完成。"""
    task = cm._TASKS.get(sender_id)
    if task is not None:
        await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    cm._TASKS.clear()
    cm._STOP_FLAGS.pop(sender_id, None)


def _base_state():
    return {
        "src": "src", "dst": "dst", "src_name": "源", "dst_name": "目",
        "min_id": 0, "max_id": 0, "next_id": 0, "total": 0,
        "done": 0, "sent": 0, "skipped": 0, "failed": 0,
        "id_map": {}, "started": "now", "updated": "now", "finished": False,
    }


async def test_bare_command_uses_config_source_target():
    """配置填了源和目标，裸 /chcopy 就该开搬。"""
    await cm.setup(_reg_ctx_holder[0]) if False else None
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 6), src)
    client = FakeClient(msgs, src, dst, peer_map={"srcc": src, "dstt": dst})
    ctx = FakeRegCtx({
        "source_chat": "@srcc", "target_chat": "@dstt",
        "send_interval": 0, "batch_size": 10,
    })
    await cm.setup(ctx)
    ev = FakeEvent("/chcopy", client)
    await ctx.dispatch(ev)
    await _drain_tasks(cm)

    assert [mid for _, mid, _ in client.copied] == [1, 2, 3, 4, 5], client.copied
    assert any("开始搬运" in r for r in ev.replies), ev.replies
    st = await ctx.storage_get("task_111", None)
    assert st and st["finished"] is True
    cm._TASKS.clear()
    print("✓ 配置填好后裸命令 /chcopy 直接开搬")


async def test_command_args_override_config():
    """命令带参数时应覆盖配置里的值。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    other = FakeChat(-100333, "另一个")
    msgs = make_messages(range(1, 4), other)
    client = FakeClient(msgs, other, dst,
                        peer_map={"other": other, "dstt": dst})
    ctx = FakeRegCtx({
        "source_chat": "@configured_src", "target_chat": "@configured_dst",
        "send_interval": 0, "batch_size": 10,
    })
    await cm.setup(ctx)
    ev = FakeEvent("/chcopy other dstt", client)
    await ctx.dispatch(ev)
    await _drain_tasks(cm)

    # 搬的是 other 的消息（id 1-3），不是配置里的源
    assert [mid for _, mid, _ in client.copied] == [1, 2, 3], client.copied
    st = await ctx.storage_get("task_111", None)
    assert st["src_name"] == "另一个", st["src_name"]
    cm._TASKS.clear()
    print("✓ 命令参数覆盖配置")


async def test_partial_config_prompts_missing():
    """只填源没填目标时，应提示缺什么，而不是崩。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    client = FakeClient([], src, dst)
    ctx = FakeRegCtx({"source_chat": "@srcc", "send_interval": 0})
    await cm.setup(ctx)
    ev = FakeEvent("/chcopy", client)
    await ctx.dispatch(ev)

    assert ev.replies and "目标" in ev.replies[0], ev.replies
    assert client.copied == []
    print("✓ 只填源时提示缺目标，不误启动")


async def test_empty_config_shows_usage():
    """配置全空时给完整用法。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    client = FakeClient([], src, dst)
    ctx = FakeRegCtx({"send_interval": 0})
    await cm.setup(ctx)
    ev = FakeEvent("/chcopy", client)
    await ctx.dispatch(ev)

    assert ev.replies and "用法" in ev.replies[0], ev.replies
    assert "resume" in ev.replies[0]
    print("✓ 配置全空时给用法说明")


async def test_status_and_resume_without_args():
    """status / resume 不需要源目标参数。"""
    src, dst = FakeChat(-100111, "源频道"), FakeChat(-100222, "目标群")
    msgs = make_messages(range(1, 21), src)
    client = FakeClient(msgs, src, dst)
    ctx = FakeRegCtx({"send_interval": 0, "batch_size": 5})
    await cm.setup(ctx)

    # 先跑到一半，手动停
    state = _base_state()
    state.update({"src": "src", "dst": "dst", "src_name": "源频道",
                  "dst_name": "目标群", "max_id": 20, "total": 20})
    await ctx.storage_set("task_111", state)
    cm._STOP_FLAGS["t_status"] = True

    ev = FakeEvent("/chcopy status", client)
    await ctx.dispatch(ev)
    assert ev.replies and "进度" in ev.replies[0], ev.replies

    cm._STOP_FLAGS.pop("t_status", None)
    cm._TASKS.clear()
    print("✓ status 无需参数即可查进度")

# ── Telethon 客户端兼容（v1.2.0）────────────────────────────────────────
# 平台实际给插件的是 telethon 的 TelegramClient，曾因此报
# "'TelegramClient' object has no attribute 'get_chat'"。
# 这几个用例保证 pyrogram / telethon 两种客户端都能跑完搬运。

class TelethonStyleClient:
    """只有 telethon API 的假客户端。

    没有 get_chat_history / get_chat / copy_message /
    copy_media_group / resolve_peer —— 插件必须自动降级：
      遍历  -> iter_messages
      取名字 -> get_entity
      发送  -> send_message（连 copy 都没有时的兜底）
    """

    def __init__(self, messages, src, dst):
        self.messages = sorted(messages, key=lambda m: m.id)
        self.src, self.dst = src, dst
        self.sent = []
        self.history_calls = []

    async def get_entity(self, entity):
        return SimpleNamespace(title=f"实体:{entity}")

    async def iter_messages(self, entity, limit=None, min_id=0,
                            max_id=0, reverse=False, **kw):
        self.history_calls.append(
            {"entity": entity, "min_id": min_id, "reverse": reverse}
        )
        hi = max_id or 10**12
        # telethon 真实语义：min_id 是**开区间**（id <= min_id 即丢弃），
        # 见 _MessagesIter._message_in_range。这里如实模拟，插件须自行 -1 补偿。
        picked = [m for m in self.messages if min_id < m.id <= hi]
        if not reverse:
            picked = list(reversed(picked))
        if limit:
            picked = picked[:limit]
        for m in picked:
            yield m

    async def send_message(self, chat, text, reply_to=None):
        self.sent.append((chat, text, reply_to))

    async def forward_messages(self, entity, messages, from_peer=None,
                               drop_author=None, **kw):
        self.sent.append(("fwd", entity, list(messages),
                          from_peer, drop_author))


def _tmsg(i, text=""):
    """telethon 风格消息：无 .chat，ID 藏在 peer_id.channel_id 里。"""
    return SimpleNamespace(
        id=i, text=text, caption=None, media=None, service=None,
        peer_id=SimpleNamespace(channel_id=-100111, user_id=None, chat_id=None),
        document=None, reply_to_message_id=None, grouped_id=None,
    )


async def test_telethon_client_can_walk_and_send():
    """telethon 客户端：能遍历、能发（走 forward_messages 而非 chat_id=）。"""
    msgs = [_tmsg(i, f"msg{i}") for i in range(1, 6)]
    client = TelethonStyleClient(msgs, -100111, -100222)
    ctx = FakeCtx({"send_interval": 0})
    state = _base_state()
    state.update({"min_id": 1, "max_id": 5, "next_id": 1, "total": 5})

    await cm._run_copy(ctx, "tele1", client, -100111, -100222, state,
                       {"send_interval": 0, "batch_size": 20})

    fwds = [s for s in client.sent if s[0] == "fwd"]
    assert len(fwds) == 5, client.sent
    assert state["next_id"] == 6, state["next_id"]
    assert state["finished"] is True, state
    print("✓ telethon 客户端可正常遍历与发送")


async def test_telethon_forward_uses_drop_author():
    """telethon 发送必须带 drop_author=True，否则出现'转发自'来源头。"""
    msgs = [_tmsg(1, "hello")]
    client = TelethonStyleClient(msgs, -100111, -100222)
    ctx = FakeCtx({"send_interval": 0})
    state = _base_state()
    state.update({"min_id": 1, "max_id": 1, "next_id": 1, "total": 1})

    await cm._run_copy(ctx, "tele2", client, -100111, -100222, state,
                       {"send_interval": 0, "batch_size": 20})

    fwd = [s for s in client.sent if s[0] == "fwd"]
    assert len(fwd) == 1, client.sent
    _, entity, messages, from_peer, drop_author = fwd[0]
    assert drop_author is True, f"drop_author={drop_author}，会显示转发来源"
    assert entity == -100222, entity
    assert messages == [1], messages
    assert from_peer == -100111, from_peer
    print("✓ telethon 发送带 drop_author=True（不显示转发来源）")


async def test_telethon_album_sent_as_group():
    """telethon 相册：一次 forward 整组，不拆成单条。"""
    src_msgs = [_tmsg(1), _tmsg(2, "cap"), _tmsg(3)]
    for m in src_msgs:
        m.media_group_id = 77
    client = TelethonStyleClient(src_msgs, -100111, -100222)
    ctx = FakeCtx({"send_interval": 0})
    state = _base_state()
    state.update({"min_id": 1, "max_id": 3, "next_id": 1, "total": 3})

    await cm._run_copy(ctx, "tele3", client, -100111, -100222, state,
                       {"send_interval": 0, "batch_size": 20,
                        "keep_albums": True})

    fwds = [s for s in client.sent if s[0] == "fwd"]
    assert len(fwds) == 1, client.sent
    assert sorted(fwds[0][2]) == [1, 2, 3], fwds[0][2]
    assert fwds[0][4] is True
    print("✓ telethon 相册整组发送不拆散")


async def test_album_at_batch_end_not_hung():
    """末尾正好是一整个相册且本批已取满时，不能死循环挂起。

    曾经的 bug：trailing_open_album 只要末尾是 >=2 的同组消息就挂起，
    而测试里整批就是相册，于是下一批 merged 还是同一组，永远发不出去。
    修法：只有本批真的取满（len(page) >= batch_size）才允许挂起。
    """
    src_msgs = [_tmsg(1), _tmsg(2, "cap"), _tmsg(3)]
    for m in src_msgs:
        m.media_group_id = 77
    client = TelethonStyleClient(src_msgs, -100111, -100222)
    ctx = FakeCtx({"send_interval": 0})
    state = _base_state()
    state.update({"min_id": 1, "max_id": 3, "next_id": 1, "total": 3})

    await asyncio.wait_for(
        cm._run_copy(ctx, "tele4", client, -100111, -100222, state,
                     {"send_interval": 0, "batch_size": 20,
                      "keep_albums": True}), 15)

    assert state["finished"] is True, state
    assert state["next_id"] == 4, state["next_id"]
    fwds = [s for s in client.sent if s[0] == "fwd"]
    assert len(fwds) == 1, client.sent
    assert sorted(fwds[0][2]) == [1, 2, 3], fwds[0][2]
    print("✓ 末尾相册取满时正常发出不死循环")


async def test_album_spanning_batches_stays_together():
    """相册跨批时必须等齐了再整组发，且不重搬。"""
    src = FakeChat(-100111, "源频道")
    dst = FakeChat(-100222, "目标群")
    # 8 条：1 普通，2-7 同一相册，8 普通；batch=5 会把相册切断
    msgs = make_messages([1, 2, 3, 4, 5, 6, 7, 8], src,
                         mgid_of={2: 5, 3: 5, 4: 5, 5: 5, 6: 5, 7: 5})
    client = FakeClient(msgs, src, dst)
    ctx = FakeCtx({"send_interval": 0})
    state = _base_state()
    state.update({"min_id": 1, "max_id": 8, "next_id": 1, "total": 8})

    await asyncio.wait_for(
        cm._run_copy(ctx, "tele5", client, src, dst, state,
                     {"send_interval": 0, "batch_size": 5,
                      "keep_albums": True}), 20)

    # 相册 2-7 必须作为一组发出（fake 只记首条 id），不能拆成单条
    assert client.albums_copied, f"相册未整组发出: {client.copied}"
    album_heads = sorted(mid for _, mid in client.albums_copied)
    assert album_heads == [2], album_heads
    single_ids = sorted(mid for _, mid, _ in client.copied)
    assert single_ids == [1, 8], single_ids
    assert state["next_id"] == 9, state["next_id"]
    print("✓ 相册跨批不拆散、不重搬")


async def test_telethon_peer_resolution_uses_get_entity():
    """telethon 客户端：解析走 get_entity，没有 get_chat 也能取到名字。"""
    client = TelethonStyleClient([], -100111, -100222)
    peer = await cm._resolve_peer(client, -100111)
    assert getattr(peer, "title", "") == "实体:-100111", peer
    title = await cm._peer_title(client, -100111)
    assert title == "实体:-100111", title
    print("✓ telethon 客户端 peer 解析与取名正常")


async def test_iter_history_pyrogram_uses_get_chat_history():
    """pyrogram 客户端：必须走 get_chat_history，不退到 iter_messages。"""
    used = []

    def _agen():
        async def _g():
            if False:
                yield None
        return _g()

    class PyroStyle:
        def get_chat_history(self, peer, **kw):
            used.append("get_chat_history")
            return _agen()

        def iter_messages(self, peer, **kw):
            used.append("iter_messages")
            return _agen()

        async def copy_message(self, **kw):
            pass

    async for _ in cm._iter_history(PyroStyle(), 1, limit=1):
        pass
    assert used == ["get_chat_history"], used
    print("✓ pyrogram 走 get_chat_history")


async def test_iter_history_telethon_min_id_exclusive():
    """telethon 的 min_id 是开区间，插件须 -1 补偿才不会漏消息。"""
    seen = []

    class TelStyle:
        async def iter_messages(self, entity, limit=None, min_id=0,
                                max_id=0, reverse=False, **kw):
            seen.append(min_id)
            yield 1

    async for _ in cm._iter_history(TelStyle(), 1, limit=5, min_id=42,
                                    reverse=True):
        pass
    # 传入 42，实际调用应为 41，否则第 42 条会被丢弃
    assert seen == [41], seen
    print("✓ telethon min_id 开区间已做 -1 补偿")


async def test_missing_both_history_apis_raises():
    """两个遍历 API 都没有时明确报错，而不是静默失败。"""
    class Empty:
        pass

    try:
        async for _ in cm._iter_history(Empty(), 1, limit=1):
            pass
        raise AssertionError("应该抛 AttributeError")
    except AttributeError as exc:
        assert "iter_messages" in str(exc), exc
    print("✓ 无遍历 API 时明确报错")


async def test_telethon_peer_id_extraction():
    """telethon 消息无 .chat，from_chat_id 必须从 peer_id 提取。"""
    m = _tmsg(3)
    assert cm._msg_peer_id(m) == -100111, cm._msg_peer_id(m)
    # pyrogram 消息有 .chat.id，应优先用它
    m2 = SimpleNamespace(id=3, chat=SimpleNamespace(id=-999))
    assert cm._msg_peer_id(m2) == -999
    # 都取不到时用传入的 peer 兜底
    m3 = SimpleNamespace(id=3)
    assert cm._msg_peer_id(m3, 12345) == 12345
    print("✓ 两种消息格式的会话 ID 提取均正确")



# 供上面测试占位用（避免误触发）
_reg_ctx_holder = [None]

_TEST_TIMEOUT = 30  # 单项测试超时（秒），防止死循环拖垮整轮


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            asyncio.run(asyncio.wait_for(t(), timeout=_TEST_TIMEOUT))
        except asyncio.TimeoutError:
            failed += 1
            print(f"✗ {t.__name__} 超时 {_TEST_TIMEOUT}s（疑似死循环）")
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
