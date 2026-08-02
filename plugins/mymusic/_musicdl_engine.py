# -*- coding: utf-8 -*-
# musicdl 引擎封装层
# 借鉴聚合解析插件的 _videodl_engine.py 模式：try/except 包裹，失败则有 HAS_MUSICDL=False
# 这样即使 musicdl 依赖（pywidevine 等）有问题，插件仍可降级使用网易云 EAPI

import sys
import json
import hashlib
from pathlib import Path

_BASE_DIR = Path(__file__).parent

HAS_MUSICDL = False
_import_error = ""

# ── 尝试导入 musicdl ──
try:
    from musicdl.musicdl import MusicClient
    HAS_MUSICDL = True
except Exception as e:
    _import_error = str(e)[:200]

# ── 网易云 EAPI 降级方案（纯 requests+pycryptodome，平台已有） ──
EAPI_KEY = b'e82ckenh8dichen8'

def _eapi_encrypt(url_path, body):
    """EAPI 加密"""
    from Crypto.Cipher import AES
    body_str = json.dumps(body, separators=(',', ':'))
    text = url_path + '-36cd479b6b5-' + body_str + '-36cd479b6b5-' + \
        hashlib.md5(('nobody' + url_path + 'use' + body_str + 'md5forencrypt').encode()).hexdigest()
    pad = 16 - len(text) % 16
    text += chr(pad) * pad
    cipher = AES.new(EAPI_KEY, AES.MODE_ECB)
    return cipher.encrypt(text.encode()).hex().upper()


def search_netease(keyword: str, limit: int = 10) -> list:
    """网易云音乐搜索（EAPI 直连，不依赖 musicdl）"""
    import requests
    api_path = '/api/cloudsearch/pc'
    body = {'s': keyword, 'type': 1, 'limit': limit, 'offset': 0, 'total': 'true'}
    params = _eapi_encrypt(api_path, body)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; M2007J3SC) AppleWebKit/537.36',
        'Referer': 'https://music.163.com/',
        'Cookie': 'os=pc; appver=2.7.1.198277;',
    }
    r = requests.post('http://music.163.com/eapi/cloudsearch/pc',
        data={'params': params}, headers=headers, timeout=15)
    data = r.json()
    songs = []
    for s in (data.get('result', {}).get('songs', []) if isinstance(data, dict) else []):
        songs.append({
            'id': str(s.get('id', '')),
            'name': s.get('name', '未知'),
            'artist': ', '.join(a.get('name', '') for a in (s.get('ar') or []) if isinstance(a, dict)),
            'album': (s.get('al') or {}).get('name', '') if isinstance(s.get('al'), dict) else '',
            'duration': s.get('dt', 0) // 1000,
        })
    return songs


def get_netease_url(song_id: str) -> str:
    """网易云音乐下载 URL（EAPI 直连）"""
    import requests
    api_path = '/api/song/enhance/player/url'
    body = {'ids': [song_id], 'br': 128000}
    params = _eapi_encrypt(api_path, body)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; M2007J3SC) AppleWebKit/537.36',
        'Referer': 'https://music.163.com/',
        'Cookie': 'os=pc; appver=2.7.1.198277;',
    }
    r = requests.post('http://music.163.com/eapi/song/enhance/player/url',
        data={'params': params}, headers=headers, timeout=15)
    data = r.json()
    urls = data.get('data', []) if isinstance(data, dict) else []
    if urls and isinstance(urls, list) and len(urls) > 0:
        return urls[0].get('url', '')
    return ''


def search(keyword: str, sources: list = None) -> list:
    """搜索音乐
    如果 musicdl 可用，使用 musicdl 搜索全部音源；
    否则降级为网易云 EAPI。
    """
    CLIENT_MAP = {
        "netease": "NeteaseMusicClient", "qq": "QQMusicClient",
        "kugou": "KugouMusicClient", "kuwo": "KuwoMusicClient", "migu": "MiguMusicClient"
    }
    NAME_MAP = {"netease": "网易云音乐", "qq": "QQ音乐", "kugou": "酷狗音乐", "kuwo": "酷我音乐", "migu": "咪咕音乐"}
    
    src_list = sources or list(CLIENT_MAP.keys())
    
    if HAS_MUSICDL and not sources:
        # 聚合搜索全部音源
        import io
        _old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            client_names = [CLIENT_MAP.get(s, s) for s in src_list]
            client = MusicClient(
                music_sources=client_names,
                init_music_clients_cfg={cn: {"disable_print": True, "search_size_per_source": 5} for cn in client_names}
            )
            result = client.search(keyword)
            songs = []
            for src, src_songs in result.items():
                if src in client_names:
                    for s in src_songs:
                        songs.append({
                            "song_name": s.song_name,
                            "singers": [str(sg) for sg in (s.singers or [])],
                            "album": s.album or "",
                            "duration_s": s.duration_s or 0,
                            "download_url": s.download_url or "",
                            "ext": s.ext or "",
                            "file_size": s.file_size or "",
                            "source": s.source or src,
                            "_source_key": next((k for k, v in CLIENT_MAP.items() if v == src), src),
                            "_source_name": NAME_MAP.get(next((k for k, v in CLIENT_MAP.items() if v == src), src), src),
                        })
        finally:
            sys.stdout = _old_stdout
        return songs
    
    elif sources:
        # 单音源搜索
        src = sources[0]
        if src == "netease":
            eapi_result = search_netease(keyword)
            songs = []
            for s in eapi_result:
                songs.append({
                    "song_name": s["name"],
                    "singers": [s["artist"]],
                    "album": s["album"],
                    "duration_s": s["duration"],
                    "download_url": "",
                    "ext": "mp3",
                    "file_size": "",
                    "source": "NeteaseMusicClient",
                    "url_id": s["id"],
                    "_source_key": "netease",
                    "_source_name": "网易云音乐",
                })
            # 预获取第一个的 URL
            if songs and not songs[0].get("download_url"):
                try:
                    url = get_netease_url(eapi_result[0]["id"])
                    if url:
                        songs[0]["download_url"] = url
                except:
                    pass
            return songs
        elif HAS_MUSICDL:
            # 非网易云但有 musicdl
            import io
            _old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                client_names = [CLIENT_MAP.get(s, s) for s in src_list]
                client = MusicClient(
                    music_sources=client_names,
                    init_music_clients_cfg={cn: {"disable_print": True, "search_size_per_source": 5} for cn in client_names}
                )
                result = client.search(keyword)
                songs = []
                for s in result.get(client_names[0], []):
                    songs.append({
                        "song_name": s.song_name,
                        "singers": [str(sg) for sg in (s.singers or [])],
                        "album": s.album or "",
                        "duration_s": s.duration_s or 0,
                        "download_url": s.download_url or "",
                        "ext": s.ext or "",
                        "file_size": s.file_size or "",
                        "source": s.source or client_names[0],
                        "_source_key": src,
                        "_source_name": NAME_MAP.get(src, src),
                    })
            finally:
                sys.stdout = _old_stdout
            return songs
        else:
            return []
    else:
        # 默认降级到网易云
        return search_netease(keyword)


def get_import_error() -> str:
    return _import_error