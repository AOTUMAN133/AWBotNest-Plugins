# -*- coding: utf-8 -*-
# musicdl 引擎封装层 — 直接导入各源模块，绕过 sources/__init__.py（避免 pywidevine 依赖）
import sys
import json
import hashlib
import io
from pathlib import Path

_BASE_DIR = Path(__file__).parent

# ── 直接导入各源模块（绕过 sources/__init__.py，避免触发 apple/soundcloud 的 pywidevine 依赖）──
HAS_MUSICDL = False
_import_error = ""

_CLIENTS = {}
_CLIENT_MAP = {
    "netease": "NeteaseMusicClient", "qq": "QQMusicClient",
    "kugou": "KugouMusicClient", "kuwo": "KuwoMusicClient", "migu": "MiguMusicClient",
}
_NAME_MAP = {"netease": "网易云音乐", "qq": "QQ音乐", "kugou": "酷狗音乐", "kuwo": "酷我音乐", "migu": "咪咕音乐"}

try:
    from musicdl.modules.sources.netease import NeteaseMusicClient
    from musicdl.modules.sources.qq import QQMusicClient
    from musicdl.modules.sources.kugou import KugouMusicClient
    from musicdl.modules.sources.kuwo import KuwoMusicClient
    from musicdl.modules.sources.migu import MiguMusicClient
    _CLIENTS = {
        "NeteaseMusicClient": NeteaseMusicClient,
        "QQMusicClient": QQMusicClient,
        "KugouMusicClient": KugouMusicClient,
        "KuwoMusicClient": KuwoMusicClient,
        "MiguMusicClient": MiguMusicClient,
    }
    HAS_MUSICDL = True
except Exception as e:
    _import_error = str(e)[:200]


def _build_client(client_class):
    """构建单个音乐客户端"""
    return client_class(
        search_size_per_source=5, auto_set_proxies=False,
        random_update_ua=False, max_retries=3, maintain_session=False,
        disable_print=True, work_dir=str(_BASE_DIR / "musicdl_outputs"),
        default_search_cookies={}, default_download_cookies={},
        default_parse_cookies={},
        search_size_per_page=10, strict_limit_search_size_per_page=True,
        quark_parser_config={}, freeproxy_settings=None,
        enable_download_curl_cffi=False, enable_parse_curl_cffi=False,
        enable_search_curl_cffi=False,
    )


def search_via_musicdl(keyword: str, sources: list = None) -> list:
    """使用 musicdl 搜索（仅导入中国音源，不依赖 pywidevine）"""
    src_list = sources or list(_CLIENT_MAP.keys())
    songs = []
    
    _old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        for src in src_list:
            client_name = _CLIENT_MAP.get(src)
            if not client_name or client_name not in _CLIENTS:
                continue
            client_class = _CLIENTS[client_name]
            client = _build_client(client_class)
            result = client.search(keyword, 5)
            if not result:
                continue
            for s in result:
                songs.append({
                    "song_name": s.song_name,
                    "singers": [str(sg) for sg in (s.singers or [])],
                    "album": s.album or "",
                    "duration_s": s.duration_s or 0,
                    "download_url": s.download_url or "",
                    "ext": s.ext or "",
                    "file_size": s.file_size or "",
                    "source": s.source or client_name,
                    "_source_key": src,
                    "_source_name": _NAME_MAP.get(src, src),
                })
    finally:
        sys.stdout = _old_stdout
    
    return songs


# ── 网易云 EAPI 降级方案 ──
EAPI_KEY = b'e82ckenh8dichen8'

def _eapi_encrypt(url_path, body):
    from Crypto.Cipher import AES
    body_str = json.dumps(body, separators=(',', ':'))
    text = url_path + '-36cd479b6b5-' + body_str + '-36cd479b6b5-' + \
        hashlib.md5(('nobody' + url_path + 'use' + body_str + 'md5forencrypt').encode()).hexdigest()
    pad = 16 - len(text) % 16
    text += chr(pad) * pad
    cipher = AES.new(EAPI_KEY, AES.MODE_ECB)
    return cipher.encrypt(text.encode()).hex().upper()


def search_netease(keyword: str, limit: int = 10) -> list:
    """网易云音乐搜索（EAPI 直连）"""
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
    """搜索音乐 — 优先用 musicdl，失败降级为网易云 EAPI"""
    if HAS_MUSICDL and sources:
        # 单音源搜索（musicdl）
        return search_via_musicdl(keyword, sources)
    elif HAS_MUSICDL and not sources:
        # 聚合搜索（musicdl）
        return search_via_musicdl(keyword)
    elif sources and sources[0] == "netease":
        # 降级：网易云 EAPI
        return _netease_to_songs(search_netease(keyword))
    else:
        return []


def get_url(song_data: dict) -> str:
    """获取下载 URL"""
    url = song_data.get("download_url", "")
    if url:
        return url
    url_id = song_data.get("url_id", "")
    if url_id:
        return get_netease_url(url_id)
    return ""


def _netease_to_songs(eapi_result):
    """将 EAPI 结果转为标准格式"""
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
    if songs:
        try:
            url = get_netease_url(eapi_result[0]["id"])
            if url:
                songs[0]["download_url"] = url
        except:
            pass
    return songs


def get_import_error() -> str:
    return _import_error