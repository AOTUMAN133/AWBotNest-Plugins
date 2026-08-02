#!/usr/bin/env python3
# musicdl worker - 子进程执行搜索/获取URL
# 注意：musicdl 的日志输出会污染 stdout，必须重定向到 stderr

import sys, json, os

# 将 stdout 临时重定向到 stderr，让 musicdl 的日志不污染 JSON 输出
_old_stdout = sys.stdout
sys.stdout = sys.stderr

from musicdl.musicdl import MusicClient

# 恢复 stdout 用于 JSON 输出
sys.stdout = _old_stdout

def main():
    action = sys.argv[1]
    sources = json.loads(sys.argv[2])
    keyword = sys.argv[3] if len(sys.argv) > 3 else ""
    song_index = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    SHORT_TO_CLIENT = {
        "netease": "NeteaseMusicClient",
        "qq": "QQMusicClient",
        "kugou": "KugouMusicClient",
        "kuwo": "KuwoMusicClient",
        "migu": "MiguMusicClient",
    }
    client_names = [SHORT_TO_CLIENT.get(s, s) for s in sources]

    client = MusicClient(music_sources=client_names, init_music_clients_cfg={cn: {"disable_print": True} for cn in client_names})

    if action == "search":
        result = client.search(keyword)
        output = {}
        for src, songs in result.items():
            output[src] = []
            for s in songs:
                singers = [str(sg) for sg in (s.singers or [])]
                output[src].append({
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
        print(json.dumps(output, ensure_ascii=False))
    elif action == "url":
        result = client.search(keyword)
        songs = []
        for src in client_names:
            songs.extend(result.get(src, []))
        if song_index < len(songs):
            s = songs[song_index]
            print(json.dumps({
                "download_url": s.download_url or "",
                "ext": s.ext or "",
                "file_size": s.file_size or "",
                "song_name": s.song_name,
                "singers": [str(sg) for sg in (s.singers or [])],
            }, ensure_ascii=False))
        else:
            print(json.dumps({"error": "未找到歌曲"}))

if __name__ == "__main__":
    main()