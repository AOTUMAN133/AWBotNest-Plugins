# NetEase Cloud Music API wrapper (pure Python, matching @meting/core eapi protocol)
# Uses cryptography (platform dependency) or pycryptodome as fallback
import json, requests, hashlib

# AES-128-ECB encryption using cryptography (preferred) or pycryptodome (fallback)
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    def _aes_ecb_encrypt(key, data):
        pad = 16 - len(data) % 16
        data_padded = data + bytes([pad] * pad)
        cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
        encryptor = cipher.encryptor()
        return encryptor.update(data_padded) + encryptor.finalize()
except ImportError:
    try:
        from Crypto.Cipher import AES
        def _aes_ecb_encrypt(key, data):
            pad = 16 - len(data) % 16
            data_padded = data + chr(pad) * pad
            cipher = AES.new(key, AES.MODE_ECB)
            return cipher.encrypt(data_padded.encode())
    except ImportError:
        def _aes_ecb_encrypt(key, data):
            raise ImportError("需要 cryptography 或 pycryptodome 库支持 AES 加密")

EAPI_KEY = b'e82ckenh8dichen8'


def _eapi_encrypt(url_path, body_dict):
    """NetEase EAPI encryption (matching @meting/core)"""
    body = json.dumps(body_dict, separators=(',', ':'))
    md5_input = f"nobody{url_path}use{body}md5forencrypt"
    md5 = hashlib.md5(md5_input.encode()).hexdigest()
    to_encrypt = f"{url_path}-36cd479b6b5-{body}-36cd479b6b5-{md5}"
    encrypted = _aes_ecb_encrypt(EAPI_KEY, to_encrypt.encode())
    return encrypted.hex().upper()


def search(keyword, limit=10, page=1):
    url_path = '/api/cloudsearch/pc'
    body = {'s': keyword, 'type': 1, 'limit': limit, 'total': 'true', 'offset': (page - 1) * limit}
    params = _eapi_encrypt(url_path, body)
    api_url = 'https://music.163.com/eapi/cloudsearch/pc'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36',
        'Referer': 'music.163.com',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    try:
        r = requests.post(api_url, data={'params': params}, headers=headers, timeout=15)
        if r.status_code != 200:
            return {'error': f'HTTP {r.status_code}'}
        result = r.json()
        if result.get('code') != 200:
            return {'error': f'API error: {result.get("code")}'}
        songs = result.get('result', {}).get('songs', [])
        return [{
            'id': s.get('id', ''),
            'name': s.get('name', '未知'),
            'artist': ', '.join(a.get('name', '') for a in (s.get('ar') or []) if isinstance(a, dict)),
            'album': s.get('al', {}).get('name', '') if isinstance(s.get('al'), dict) else '',
            'duration': s.get('duration', 0) // 1000,
            'cover': '',
        } for s in songs]
    except Exception as e:
        return {'error': str(e)}


def get_song_url(song_id, br=128000):
    url_path = '/api/song/enhance/player/url'
    body = {'ids': [int(song_id)], 'br': br}
    params = _eapi_encrypt(url_path, body)
    api_url = 'https://music.163.com/eapi/song/enhance/player/url'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36',
        'Referer': 'music.163.com',
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    try:
        r = requests.post(api_url, data={'params': params}, headers=headers, timeout=15)
        if r.status_code != 200:
            return {'error': f'HTTP {r.status_code}'}
        result = r.json()
        if result.get('code') != 200:
            return {'error': f'API error: {result.get("code")}'}
        data = result.get('data', [{}])[0]
        if data.get('uf') and data['uf'].get('url'):
            return {'url': data['uf']['url'], 'size': data.get('size', 0), 'br': data.get('br', 0) // 1000}
        return {'url': data.get('url', ''), 'size': data.get('size', 0), 'br': data.get('br', 0) // 1000}
    except Exception as e:
        return {'error': str(e)}


if __name__ == '__main__':
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else 'search'
    keyword = sys.argv[2] if len(sys.argv) > 2 else '猪之歌'
    try:
        if action == 'search':
            result = search(keyword)
            print(json.dumps(result, ensure_ascii=False))
        elif action == 'url':
            result = get_song_url(keyword)
            print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'error': str(e)}))