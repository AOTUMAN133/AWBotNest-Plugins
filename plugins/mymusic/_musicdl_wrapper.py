# musicdl 封装层 - 每次搜索启动独立子进程
import sys
import json
import subprocess
import time
from pathlib import Path

_BASE_DIR = Path(__file__).parent

# 音源配置
SOURCES = {
    "netease": {"name": "网易云音乐", "client": "NeteaseMusicClient", "cmd": "wy"},
    "qq": {"name": "QQ音乐", "client": "QQMusicClient", "cmd": "qq"},
    "kugou": {"name": "酷狗音乐", "client": "KugouMusicClient", "cmd": "kg"},
    "kuwo": {"name": "酷我音乐", "client": "KuwoMusicClient", "cmd": "kw"},
    "migu": {"name": "咪咕音乐", "client": "MiguMusicClient", "cmd": "mg"},
}

_worker_script = str(_BASE_DIR / "_musicdl_worker.py")


def search(keyword: str, sources: list = None) -> dict:
    """搜索音乐，返回 {songs: [{...}]}"""
    srcs = sources or list(SOURCES.keys())
    timeout = 90 if len(srcs) > 2 else 60
    try:
        r = subprocess.run(
            [sys.executable, _worker_script, "search", json.dumps(srcs), keyword],
            capture_output=True, text=True, timeout=timeout
        )
        if r.returncode != 0:
            return {"error": r.stderr[:500] or f"进程退出 (code={r.returncode})"}
        # musicdl 输出进度条到 stdout，JSON 在最后一行
        lines = [l.strip() for l in r.stdout.split("\n") if l.strip()]
        if not lines:
            return {"error": "空响应"}
        # 找到最后一个 JSON 行
        for line in reversed(lines):
            if line.startswith("{"):
                data = json.loads(line)
                # 将 worker 的 {ClientName: [...]} 转为 {songs: [...]}
                if isinstance(data, dict):
                    songs = []
                    for client_name, client_songs in data.items():
                        if isinstance(client_songs, list):
                            songs.extend(client_songs)
                    if songs:
                        return {"songs": songs}
                return data
        return {"error": f"未找到 JSON 输出: {lines[-1][:200]}"}
    except subprocess.TimeoutExpired:
        return {"error": f"搜索超时 ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}


def search_aggregate(keyword: str) -> list:
    """聚合搜索所有音源，返回扁平列表"""
    songs = []
    # 逐个音源搜索，避免慢音源阻塞
    for src_key in SOURCES:
        try:
            result = search(keyword, [src_key])
            if "error" in result:
                continue
            for s in result.get("songs", []):
                s["_source_key"] = src_key
                s["_source_name"] = SOURCES[src_key]["name"]
                songs.append(s)
        except Exception:
            continue
    return songs