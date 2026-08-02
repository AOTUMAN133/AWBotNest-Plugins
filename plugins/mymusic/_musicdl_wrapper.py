# musicdl 封装层 - 聚合搜索+下载，支持多音源
import sys
import json
import subprocess
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

ALL_CLIENTS = [s["client"] for s in SOURCES.values()]


def _run_musicdl(action: str, sources: list, keyword: str = "", song_index: int = 0):
    """通过子进程调用 musicdl 封装脚本"""
    script = str(_BASE_DIR / "_musicdl_worker.py")
    args = [sys.executable, script, action, json.dumps(sources)]
    if keyword:
        args.append(keyword)
    if song_index:
        args.append(str(song_index))
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return {"error": r.stderr[:300]}
        # musicdl 会输出进度条到 stdout，JSON 在最后一行
        output = r.stdout.strip().split("\n")[-1]
        return json.loads(output) if output else {"error": "空响应"}
    except subprocess.TimeoutExpired:
        return {"error": "搜索超时"}
    except Exception as e:
        return {"error": str(e)}


def search(keyword: str, sources: list = None) -> dict:
    """搜索音乐，返回 {source: [songs]}"""
    srcs = sources or list(SOURCES.keys())
    return _run_musicdl("search", srcs, keyword)


def get_url(source: str, song_index: int = 0, keyword: str = "") -> dict:
    """获取指定歌曲的下载URL"""
    return _run_musicdl("url", [source], keyword, song_index)


def search_aggregate(keyword: str) -> list:
    """聚合搜索所有音源，返回扁平列表（每个音源单独搜索，避免慢音源阻塞）"""
    songs = []
    for src_key, src_info in SOURCES.items():
        try:
            result = search(keyword, [src_key])
            if "error" in result:
                continue
            src_songs = result.get(src_info["client"], [])
            for s in src_songs:
                s["_source_key"] = src_key
                s["_source_name"] = src_info["name"]
                songs.append(s)
        except Exception:
            continue
    return songs