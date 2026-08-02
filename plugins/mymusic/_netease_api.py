# NetEase Cloud Music API wrapper (pure Python, EAPI protocol)
# Dependencies: requests, pycryptodome (both already in platform)
import json, requests, hashlib

EAPI_KEY = b'e82ckenh8dichen8'

def _eapi_encrypt(url_path, body):
    """EAPI encryption (used by @meting/core)"""
    from Crypto.Cipher import AES
    body_str = json.dumps(body, separators=(',', ':'))
    text = url_path + '-36cd479b6b5-' + body_str + '-36cd479b6b5-' + hashlib.md5(('nobody' + url_path + 'use' + body_str + 'md5forencrypt').encode()).hexdigest()
    # AES-128-ECB
    pad = 16 - len(text) % 16
    text += chr(pad) * pad
    cipher = AES.new(EAPI_KEY, AES.MODE_ECB)
    encrypted = cipher.encrypt(text.encode())
    return encrypted.hex().upper()


def search(keyword: str, limit: int = 5) -> list:
    """搜索网易云音乐"""
    api_path = '/api/cloudsearch/pc'  # 加密用 /api/，请求时替换为 /eapi/
    body = {'s': keyword, 'type': 1, 'limit': limit, 'offset': 0, 'total': 'true'}
    params = _eapi_encrypt(api_path, body)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; M2007J3SC) AppleWebKit/537.36',
        'Referer': 'https://music.163.com/',
        'Cookie': 'os=pc; appver=2.7.1.198277;',
    }
    r = requests.post('http://music.163.com/eapi/cloudsearch/pc',  # 请求用 /eapi/
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


def get_song_url(song_id: str, br: int = 128000) -> str:
    """获取歌曲下载 URL"""
    api_path = '/api/song/enhance/player/url'  # 加密用 /api/
    body = {'ids': [song_id], 'br': br}
    params = _eapi_encrypt(api_path, body)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11; M2007J3SC) AppleWebKit/537.36',
        'Referer': 'https://music.163.com/',
        'Cookie': 'os=pc; appver=2.7.1.198277;',
    }
    r = requests.post('http://music.163.com/eapi/song/enhance/player/url',  # 请求用 /eapi/
        data={'params': params}, headers=headers, timeout=15)
    data = r.json()
    
    urls = data.get('data', []) if isinstance(data, dict) else []
    if urls and isinstance(urls, list) and len(urls) > 0:
        return urls[0].get('url', '')
    return ''


if __name__ == '__main__':
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else 'search'
    if action == 'search':
        keyword = sys.argv[2] if len(sys.argv) > 2 else '晴天'
        result = search(keyword)
        print(json.dumps(result, ensure_ascii=False))
    elif action == 'url':
        song_id = sys.argv[2] if len(sys.argv) > 2 else ''
        url = get_song_url(song_id)
        print(json.dumps({'url': url}, ensure_ascii=False))