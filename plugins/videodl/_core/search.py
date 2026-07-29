# -*- coding: utf-8 -*-
"""抖音搜索模块 - 使用 httpx 直接调用搜索 API，替代 cloakbrowser"""

from urllib.parse import urlencode, quote

import httpx

from aBogus import ABogus
from custom import USERAGENT
from verifyFp import VerifyFp

__all__ = ["douyin_search"]

_DOUYIN_SEARCH_URL = "https://www.douyin.com/aweme/v1/web/search/item/"
_DOUYIN_HEADERS = {
    "User-Agent": USERAGENT,
    "Referer": "https://www.douyin.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Connection": "keep-alive",
}


def _gen_verify_fp() -> str:
    """生成 verify_fp 参数"""
    return VerifyFp.get_verify_fp()


def _gen_a_bogus(params_str: str, user_agent: str = USERAGENT) -> str:
    """使用 ABogus 类从 URL 编码字符串生成 a_bogus 签名"""
    bogus = ABogus(user_agent=user_agent)
    return bogus.get_value(params_str, data=None, method="GET", user_agent=user_agent)


async def douyin_search(keyword: str, count: int = 5, cookie: str = "") -> list:
    """
    搜索抖音视频 - 使用 httpx + aBogus 直接调用搜索 API (异步)

    Args:
        keyword: 搜索关键词
        count: 返回结果数量
        cookie: 抖音登录Cookie（必需）

    Returns:
        list[dict]: 包含 title、url、platform 的列表
    """
    results = []
    headers = dict(_DOUYIN_HEADERS)
    verify_fp = _gen_verify_fp()
    headers["Cookie"] = f"verify_fp={verify_fp}; s_v_web_id={verify_fp}"
    if cookie:
        headers["Cookie"] = cookie.strip() + f"; verify_fp={verify_fp}; s_v_web_id={verify_fp}"

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            params = {
                "keyword": keyword,
                "search_id": "",
                "type": "3",  # 3=video
                "offset": "0",
                "count": str(count),
                "source": "search",
                "aid": "6383",
                "device_platform": "web",
                "publish_time": "0",
                "sort_type": "0",
                "version_code": "170400",
                "cookie_enabled": "true",
                "screen_width": "1920",
                "screen_height": "1080",
                "browser_language": "zh-CN",
                "browser_platform": "Win32",
                "browser_name": "Chrome",
                "browser_version": "120.0.0.0",
                "browser_online": "true",
                "verifyFp": verify_fp,
            }

            # 生成 aBogus 参数（从 URL 编码后的字符串生成，不包含 a_bogus 自身）
            params_str = urlencode(params, safe="=", quote_via=quote)
            a_bogus = _gen_a_bogus(params_str, USERAGENT)
            url = f"{_DOUYIN_SEARCH_URL}?{params_str}&a_bogus={a_bogus}"

            r = await client.get(
                url,
                headers=headers,
                timeout=15,
            )

            if r.status_code != 200:
                return results

            data = r.json()
            status_code = data.get("status_code", -1)
            if status_code != 0:
                # 2483 = 需要登录
                if status_code == 2483:
                    import logging
                    logging.warning("抖音搜索需要登录Cookie（请检查Cookie是否包含sessionid）")
                return results

            for item in data.get("data", []):
                # 尝试从 aweme_info 或 video 字段提取
                aweme = item.get("aweme_info") or item.get("video") or {}
                if not aweme:
                    continue

                desc = aweme.get("desc", "") or ""
                aweme_id = aweme.get("aweme_id", "") or ""
                if not aweme_id:
                    aweme_id = aweme.get("video_id", "") or ""
                    if not aweme_id:
                        share_url = aweme.get("share_url", "") or ""
                        import re
                        m = re.search(r"/video/(\d+)", share_url)
                        if m:
                            aweme_id = m.group(1)
                if not aweme_id:
                    continue

                results.append({
                    "title": (desc or "抖音视频")[:50],
                    "url": f"https://www.douyin.com/video/{aweme_id}",
                    "platform": "抖音",
                })

                if len(results) >= count:
                    break

    except Exception:
        pass

    return results