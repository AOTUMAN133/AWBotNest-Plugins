#!/usr/bin/env python3
# musicdl daemon - 持久化进程，按需初始化音源客户端
import sys, json, os

_real_stdout = sys.stdout
sys.stdout = sys.stderr

from musicdl.musicdl import MusicClient

SHORT_TO_CLIENT = {
    "netease": "NeteaseMusicClient",
    "qq": "QQMusicClient",
    "kugou": "KugouMusicClient",
    "kuwo": "KuwoMusicClient",
    "migu": "MiguMusicClient",
}

# 缓存已初始化的客户端
_client = None
_current_sources = []

def _ensure_client(sources):
    global _client, _current_sources
    client_names = [SHORT_TO_CLIENT.get(s, s) for s in sources]
    if _client is None or set(client_names) != set(_current_sources):
        _client = MusicClient(
            music_sources=client_names,
            init_music_clients_cfg={cn: {"disable_print": True, "search_size_per_source": 5} for cn in client_names}
        )
        _current_sources = client_names
    return _client

# 通知就绪
_real_stdout.write("READY\n")
_real_stdout.flush()

# 命令循环
while True:
    line = sys.stdin.readline()
    if not line:
        break
    line = line.strip()
    if not line:
        continue
    if line == "EXIT":
        break
    
    try:
        cmd = json.loads(line)
        action = cmd.get("action", "search")
        sources = cmd.get("sources", ["netease"])
        keyword = cmd.get("keyword", "")
        
        if action == "search":
            client = _ensure_client(sources)
            target_clients = [SHORT_TO_CLIENT.get(s, s) for s in sources]
            
            result = client.search(keyword)
            output = {"songs": []}
            for src, songs in result.items():
                if src in target_clients:
                    for s in songs:
                        singers = [str(sg) for sg in (s.singers or [])]
                        output["songs"].append({
                            "song_name": s.song_name,
                            "singers": singers,
                            "album": s.album or "",
                            "duration_s": s.duration_s or 0,
                            "download_url": s.download_url or "",
                            "ext": s.ext or "",
                            "file_size": s.file_size or "",
                            "source": s.source or src,
                            "cover_url": s.cover_url or "",
                        })
            _real_stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
            _real_stdout.flush()
        else:
            _real_stdout.write(json.dumps({"error": f"Unknown action: {action}"}) + "\n")
            _real_stdout.flush()
    except Exception as e:
        import traceback
        _real_stdout.write(json.dumps({"error": str(e)}) + "\n")
        _real_stdout.flush()