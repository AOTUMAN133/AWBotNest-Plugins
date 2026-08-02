"""
AWBotNest 插件测试框架
模拟 PlatformContext，让插件在本地加载运行，无需真实 Telegram 账号。
"""
import os, sys, json, asyncio, time, inspect, importlib
from pathlib import Path
from typing import Any, Callable, Optional

# ── 模拟插件上下文 ──

class _MockKV:
    """模拟 KV 存储（内存字典）"""
    def __init__(self):
        self._data = {}
    def get(self, key, default=None):
        return self._data.get(key, default)
    def set(self, key, value):
        self._data[key] = value
    def delete(self, key):
        self._data.pop(key, None)

class _MockLogger:
    def __init__(self, plugin_id):
        self._pid = plugin_id
    def _log(self, level, msg, *a, **k):
        if a:
            try: text = str(msg) % a
            except: text = " ".join([str(msg), *[str(x) for x in a]])
        else:
            text = str(msg)
        print(f"  [{level.upper()}] [{self._pid}] {text}")
    def debug(self, msg, *a, **k): self._log("debug", msg, *a, **k)
    def info(self, msg, *a, **k): self._log("info", msg, *a, **k)
    def warning(self, msg, *a, **k): self._log("warning", msg, *a, **k)
    def error(self, msg, *a, **k): self._log("error", msg, *a, **k)

class _MockMessage:
    """模拟消息对象"""
    def __init__(self, text, chat_id=12345, from_user_id=67890, msg_id=1):
        self.text = text
        self.chat = type('obj', (), {'id': chat_id})()
        self.from_user = type('obj', (), {'id': from_user_id})()
        self.id = msg_id
        self.reply_to = None
    async def reply(self, text, **kw):
        print(f"  [发消息] {text[:100]}")
        return _MockReplyMessage(text)
    async def edit(self, **kw):
        text = kw.get('text', '')
        print(f"  [编辑消息] {text[:100]}")
    async def delete(self):
        print(f"  [删除消息]")

class _MockReplyMessage:
    def __init__(self, text):
        self.text = text
        self.id = 999
    async def edit(self, text, **kw):
        print(f"  [编辑消息] {text[:100]}")
    async def edit_text(self, text, **kw):
        print(f"  [编辑消息] {text[:100]}")
    async def delete(self):
        print(f"  [删除消息]")

class _MockClient:
    """模拟 Telegram 客户端"""
    def __init__(self):
        self.handlers = []
    async def send_audio(self, chat_id, file, **kw):
        print(f"  [发送音频] chat={chat_id} title={kw.get('title','')}")
    async def send_video(self, chat_id, file, **kw):
        print(f"  [发送视频] chat={chat_id} caption={kw.get('caption','')}")
    async def delete_messages(self, chat_id, msg_ids):
        print(f"  [删除多条消息] chat={chat_id} ids={msg_ids}")

class _MockFilterObj:
    def __init__(self, name=None):
        self._name = name
    def __call__(self, *a, **k):
        return True
    def __rand__(self, other):
        return self
    def __and__(self, other):
        return self

class _MockFilters:
    def __init__(self):
        self.text = _MockFilterObj("text")
        self.outgoing = _MockFilterObj("outgoing")

class PlatformContext:
    """模拟平台上下文，插件通过此对象访问平台能力"""
    def __init__(self, plugin_id: str, data_dir: str = None):
        self.plugin_id = plugin_id
        self.data_dir = Path(data_dir or f"/tmp/awbotnest_test/{plugin_id}")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.kv = _MockKV()
        self.log = _MockLogger(plugin_id)
        self.filters = _MockFilters()
        self._handlers = []
        self._schedules = []
        self._actions = []
        self._config = {"keep_local": True}

    def config(self, key: str, default=None):
        return self._config.get(key, default)

    @property
    def config(self):
        return self._config

    def on_message(self, *filters, group=0):
        """模拟装饰器，记录 handler 但不实际注册"""
        def decorator(func):
            self._handlers.append((func, filters, group))
            return func
        return decorator

    def schedule(self, callback, mode, **kw):
        self._schedules.append((callback, mode, kw))
        print(f"  [定时任务] 注册: {callback.__name__} mode={mode}")

    def action(self, name: str):
        def decorator(func):
            self._actions.append((name, func))
            return func
        return decorator

    def notify(self, msg, level="info", **kw):
        print(f"  [通知] [{level}] {msg[:100]}")


# ── 插件加载器 ──

class PluginTester:
    """加载插件并提供测试入口"""
    def __init__(self, plugin_path: str):
        self.plugin_path = Path(plugin_path).resolve()
        self.plugin_dir = self.plugin_path.parent
        self.module = None
        self.ctx = None
        self.client = _MockClient()

    def load(self):
        """加载插件，调用 setup(ctx)"""
        sys.path.insert(0, str(self.plugin_dir))
        spec = importlib.util.spec_from_file_location(
            self.plugin_path.stem, str(self.plugin_path)
        )
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

        # 创建上下文
        plugin_id = self.module.__plugin__.get("id", self.plugin_path.stem)
        self.ctx = PlatformContext(plugin_id)

        # 调用 setup
        print(f"\n{'='*60}")
        print(f"  加载插件: {self.module.__plugin__.get('name', plugin_id)} v{self.module.__plugin__.get('version', '?')}")
        print(f"  插件 ID: {plugin_id}")
        print(f"{'='*60}\n")
        asyncio.get_event_loop().run_until_complete(self.module.setup(self.ctx))
        print(f"\n  ✅ 加载完成 | handlers={len(self.ctx._handlers)} schedules={len(self.ctx._schedules)} actions={len(self.ctx._actions)}\n")
        return self.ctx

    def find_handler(self, cmd_text: str):
        """查找能处理指定命令的 handler"""
        msg = _MockMessage(cmd_text)
        for func, filters, group in self.ctx._handlers:
            # 执行 handler
            asyncio.get_event_loop().run_until_complete(func(self.client, msg))
        return msg

    def test_search(self, keyword: str, source: str = "youtube"):
        """测试搜索功能"""
        print(f"\n  ▶ 测试搜索: source={source} keyword={keyword}")
        # 模拟消息
        if source == "netease":
            text = f".yy wy {keyword}"
        else:
            text = f".yy {keyword}"
        msg = _MockMessage(text)
        for func, filters, group in self.ctx._handlers:
            asyncio.get_event_loop().run_until_complete(func(self.client, msg))
        return msg

    def test_download(self, song_id: str, title: str, artist: str, source: str = "netease"):
        """测试下载功能（通过子进程调用，与插件实际路径一致）"""
        print(f"\n  ▶ 测试下载: source={source} id={song_id} title={title}")
        import subprocess
        api_path = str(Path(__file__).parent / "_netease_api.py")
        r = subprocess.run(
            [sys.executable, api_path, "url", str(song_id)],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).parent),
        )
        print(f"  子进程返回码: {r.returncode}")
        if r.returncode != 0:
            print(f"  子进程错误: {r.stderr[:200]}")
            return None
        result = json.loads(r.stdout.strip())
        if isinstance(result, dict) and "error" in result:
            print(f"  API错误: {result['error']}")
            return None
        print(f"  URL结果: 有效 ({result.get('size', 0)} bytes)")
        return result

    def test_direct(self, func_name: str, *args, **kwargs):
        """直接调用插件内的函数"""
        if hasattr(self.module, func_name):
            func = getattr(self.module, func_name)
            if asyncio.iscoroutinefunction(func):
                return asyncio.get_event_loop().run_until_complete(func(*args, **kwargs))
            else:
                return func(*args, **kwargs)
        # 也可能是 setup 内的闭包 - 通过 handlers 测试
        raise AttributeError(f"函数 {func_name} 未找到")


# ── 主入口 ──

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AWBotNest 插件测试框架")
    parser.add_argument("plugin", help="插件路径 (__init__.py)")
    parser.add_argument("--cmd", default=".yysm", help="要测试的命令")
    parser.add_argument("--search", help="搜索关键词")
    parser.add_argument("--source", default="youtube", choices=["youtube", "netease"])
    args = parser.parse_args()

    tester = PluginTester(args.plugin)
    ctx = tester.load()

    if args.search:
        tester.test_search(args.search, args.source)
    elif args.cmd:
        print(f"\n  ▶ 测试命令: {args.cmd}")
        tester.find_handler(args.cmd)