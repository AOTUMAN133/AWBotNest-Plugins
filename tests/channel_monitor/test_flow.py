"""channel_monitor 全流程测试 —— 用假客户端，不碰 Telegram。"""
import asyncio
import importlib
import sys
import time
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "plugins"))
cm = importlib.import_module("channel_monitor")


# ── 假对象 ──────────────────────────────────────────────────────────────
class Channel:
    """名字必须叫 Channel —— _marked_id 靠类型名判断 -100 前缀。"""

    def __init__(self, cid, title):
        self.id = cid
        self.title = title


class FakeClient:
    def __init__(self, messages, src, dst):
        self.messages = sorted(messages, key=lambda m: m.id)
        self.src = src
        self.dst = dst
        self.forwarded = []   # dict(dst, ids, src, as_album)
        self.sent_texts = []

    async def get_entity(self, peer):
        if peer in (-100111, 111, "src"):
            return self.src
        return self.dst

    async def iter_messages(self, peer, limit=None, **kw):
        # telethon 语义：最新在前
        picked = list(reversed(self.messages))
        if limit:
            picked = picked[:limit]
        for m in picked:
            yield m

    async def forward_messages(self, dst, ids, from_peer=None,
                               drop_author=None, as_album=None, **kw):
        ids = list(ids)
        self.forwarded.append({
            "dst": dst, "ids": ids, "src": from_peer,
            "as_album": bool(as_album), "drop_author": drop_author,
        })

        async def _edit(text):
            return None

        return [SimpleNamespace(text="", message="", edit=_edit)]

    async def send_message(self, dst, text, **kw):
        self.sent_texts.append((dst, text))
        return SimpleNamespace(text=text, edit=lambda t: None)


class Msg:
    def __init__(self, mid, text="", mgid=None, media=None, service=None):
        self.id = mid
        self.text = text
        self.media_group_id = mgid
        self.media = media
        self.service = service


class FakeEvent(Msg):
    def __init__(self, mid, chat_id, text="", mgid=None, media=None, service=None):
        super().__init__(mid, text, mgid, media, service)
        self.chat_id = chat_id
        self.replies = []

    async def reply(self, text):
        self.replies.append(text)


class FakeCtx:
    def __init__(self, cfg, client):
        self.config = cfg
        self.users = [client]
        self.client = client
        self._store = {}
        self.handlers = {}
        self.notifications = []
        self.tasks = []
        self.log = SimpleNamespace(
            info=lambda *a, **k: None,
            warning=lambda *a, **k: None,
            error=lambda *a, **k: None,
            exception=lambda *a, **k: None,
        )

    # 存储
    class _Storage:
        def __init__(self, outer):
            self.outer = outer

        async def get(self, key, default=None):
            return self.outer._store.get(key, default)

        async def set(self, key, value):
            self.outer._store[key] = value

        async def delete(self, key):
            self.outer._store.pop(key, None)

    @property
    def storage(self):
        return FakeCtx._Storage(self)

    # 注册器
    def on_message(self, **kw):
        def deco(fn):
            key = "incoming" if kw.get("incoming") and not kw.get("outgoing") else "outgoing"
            self.handlers[key] = fn
            return fn
        return deco

    def create_task(self, coro, name=None, **kw):
        task = asyncio.ensure_future(coro)
        self.tasks.append(task)
        return task

    async def notify(self, text, **kw):
        self.notifications.append(text)


BASE_CFG = {
    "rules": [{"source": "-100111", "target": "-100222", "enabled": True}],
    "backfill_enable": False,
    "backfill_count": 0,
    "copy_media": True,
    "keep_albums": True,
    "attach_source": False,
    "skip_service": True,
    "keywords": "",
    "drop_regex": "",
    "replace_regex": "",
    "album_window": 0.25,
    "flood_wait_max": 300,
    "command": "/chmon",
}


def make_ctx(client, **over):
    cfg = dict(BASE_CFG)
    cfg.update(over)
    return FakeCtx(cfg, client)


async def wait_until(pred, timeout=4.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        await asyncio.sleep(0.02)
    return False


async def fire(ctx, *events):
    handler = ctx.handlers["incoming"]
    for ev in events:
        await handler(ev)


# ── 用例 ────────────────────────────────────────────────────────────────
async def test_live_single_and_album():
    src, dst = Channel(111, "源频道"), Channel(222, "目标群")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client)
    await cm.setup(ctx)
    rt = cm._RT
    try:
        await fire(
            ctx,
            FakeEvent(10, -100111, "消息10"),
            FakeEvent(11, -100111, "消息11"),
            FakeEvent(12, -100111, "消息12"),
            # 一个三图相册
            FakeEvent(20, -100111, "", mgid="g1", media=object()),
            FakeEvent(21, -100111, "", mgid="g1", media=object()),
            FakeEvent(22, -100111, "", mgid="g1", media=object()),
        )

        slot = rt.slots[rt.rules[0].key]
        ok = await wait_until(lambda: slot.state["sent"] >= 4)
        assert ok, f"只发出 {slot.state['sent']} 次"

        singles = [f for f in client.forwarded if not f["as_album"]]
        albums = [f for f in client.forwarded if f["as_album"]]
        assert [f["ids"] for f in singles] == [[10], [11], [12]], singles
        assert len(albums) == 1, f"相册应该整组发一次，实际 {len(albums)} 次"
        assert albums[0]["ids"] == [20, 21, 22], albums[0]["ids"]
        assert all(f["drop_author"] is True for f in client.forwarded)
    finally:
        await cm.teardown(ctx)


async def test_dedupe_on_replay():
    src, dst = Channel(111, "源"), Channel(222, "目")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client)
    await cm.setup(ctx)
    rt = cm._RT
    try:
        await fire(ctx, FakeEvent(10, -100111, "第一次"))
        slot = rt.slots[rt.rules[0].key]
        assert await wait_until(lambda: slot.state["sent"] == 1)

        # 断线重连后 Telegram 重推同一条
        await fire(ctx, FakeEvent(10, -100111, "第一次"))
        await asyncio.sleep(0.2)
        assert len(client.forwarded) == 1, "重复消息不该再转一次"
    finally:
        await cm.teardown(ctx)


async def test_backfill_then_live():
    src, dst = Channel(111, "源"), Channel(222, "目")
    msgs = [Msg(i, f"历史{i}") for i in range(1, 11)]
    client = FakeClient(msgs, src, dst)
    ctx = make_ctx(client, backfill_enable=True, backfill_count=5)
    await cm.setup(ctx)
    rt = cm._RT
    try:
        rule = rt.rules[0]
        slot = rt.slots[rule.key]
        ok = await wait_until(lambda: slot.state["sent"] == 5)
        assert ok, f"补历史只发了 {slot.state['sent']} 条"

        order = [f["ids"][0] for f in client.forwarded]
        assert order == [6, 7, 8, 9, 10], f"应该从旧到新补最后 5 条，实际 {order}"
        assert slot.state["last_id"] == 10

        # 补完之后的新消息继续转
        await fire(ctx, FakeEvent(11, -100111, "新消息"))
        assert await wait_until(lambda: slot.state["sent"] == 6)
        assert client.forwarded[-1]["ids"] == [11]
    finally:
        await cm.teardown(ctx)


async def test_backfill_zero_sets_last_id_only():
    src, dst = Channel(111, "源"), Channel(222, "目")
    msgs = [Msg(i, f"历史{i}") for i in range(1, 11)]
    client = FakeClient(msgs, src, dst)
    ctx = make_ctx(client, backfill_enable=True, backfill_count=0)
    await cm.setup(ctx)
    rt = cm._RT
    try:
        rule = rt.rules[0]
        slot = rt.slots[rule.key]
        assert await wait_until(lambda: slot.ready)
        assert client.forwarded == [], "count=0 不该补任何历史"
        assert slot.state["last_id"] == 10, "但要把 last_id 设到最新，避免旧消息被当成新消息"

        await fire(ctx, FakeEvent(11, -100111, "新消息"))
        assert await wait_until(lambda: slot.state["sent"] == 1)
    finally:
        await cm.teardown(ctx)


async def test_keyword_filter():
    src, dst = Channel(111, "源"), Channel(222, "目")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client, keywords="115\n夸克")
    await cm.setup(ctx)
    rt = cm._RT
    try:
        await fire(
            ctx,
            FakeEvent(10, -100111, "今天天气不错"),
            FakeEvent(11, -100111, "115 分享来了"),
        )
        slot = rt.slots[rt.rules[0].key]
        assert await wait_until(lambda: slot.state["sent"] == 1)
        assert client.forwarded[0]["ids"] == [11]
        assert slot.state["skipped"] == 1
    finally:
        await cm.teardown(ctx)


async def test_service_message_skipped():
    src, dst = Channel(111, "源"), Channel(222, "目")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client)
    await cm.setup(ctx)
    rt = cm._RT
    try:
        await fire(ctx, FakeEvent(10, -100111, "入群", service=object()))
        await asyncio.sleep(0.15)
        slot = rt.slots[rt.rules[0].key]
        assert client.forwarded == []
        assert slot.state["skipped"] == 1
    finally:
        await cm.teardown(ctx)


async def test_status_command():
    src, dst = Channel(111, "源频道"), Channel(222, "目标群")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client)
    await cm.setup(ctx)
    try:
        ev = FakeEvent(999, -100111, ".chmon")
        await ctx.handlers["outgoing"](ev)
        assert ev.replies and "频道监控转发" in ev.replies[0]
        assert "源频道" in ev.replies[0]
    finally:
        await cm.teardown(ctx)


async def test_teardown_clears_runtime():
    src, dst = Channel(111, "源"), Channel(222, "目")
    client = FakeClient([], src, dst)
    ctx = make_ctx(client)
    await cm.setup(ctx)
    assert cm._RT is not None
    await cm.teardown(ctx)
    assert cm._RT is None
    await asyncio.sleep(0.05)
    alive = [t for t in ctx.tasks if not t.cancelled() and not t.done()]
    assert alive == [], f"停用后仍有 {len(alive)} 个任务存活"
