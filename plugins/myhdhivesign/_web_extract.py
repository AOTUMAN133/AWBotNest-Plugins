"""
网页内容提取工具模块
轻量版（requests + BeautifulSoup）+ 增强版（Crawl4AI）

用法：
    from _web_extract import extract_lightweight, extract_enhanced

    # 轻量版：不需要额外依赖，适合简单页面
    result = extract_lightweight("https://example.com")
    print(result["title"], result["text"][:200])

    # 增强版：需要 crawl4ai，适合 JS 渲染页面
    result = await extract_enhanced("https://example.com")
    print(result["title"], result["markdown"][:200])
"""

import re
from typing import Optional

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ===== 轻量版 =====

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def extract_lightweight(url: str, timeout: int = 15) -> dict:
    """
    轻量版网页内容提取
    使用 requests + BeautifulSoup，无需额外依赖
    适合不需要 JS 渲染的简单页面

    返回:
        {title, text, links, images, success, error}
    """
    if not HAS_REQUESTS or not HAS_BS4:
        return {"success": False, "error": "需要安装 requests 和 beautifulsoup4"}

    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # 提取标题
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        # 删除无用标签
        for tag in ["script", "style", "nav", "footer", "header", "noscript", "iframe"]:
            for el in soup.find_all(tag):
                el.decompose()

        # 提取正文
        body = soup.find("body") or soup
        text = body.get_text(separator="\n", strip=True)
        # 过滤短行（大概率是导航/广告）
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 15]
        text = "\n".join(lines)

        # 提取链接
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http"):
                links.append({"url": href, "text": a.get_text(strip=True)[:100]})

        # 提取图片
        images = []
        for img in soup.find_all("img", src=True):
            src = img["src"]
            if src.startswith("http"):
                images.append({"url": src, "alt": img.get("alt", "")[:100]})

        return {
            "success": True,
            "url": url,
            "title": title,
            "text": text,
            "links": links,
            "images": images,
            "html_len": len(resp.text),
        }

    except requests.Timeout:
        return {"success": False, "error": f"请求超时 ({timeout}s)"}
    except requests.RequestException as e:
        return {"success": False, "error": f"请求失败: {e}"}
    except Exception as e:
        return {"success": False, "error": f"解析失败: {e}"}


# ===== 增强版（Crawl4AI）=====

try:
    from crawl4ai import AsyncWebCrawler
    HAS_CRAWL4AI = True
except ImportError:
    HAS_CRAWL4AI = False


async def extract_enhanced(url: str, wait_for: str = None) -> dict:
    """
    增强版网页内容提取
    使用 Crawl4AI，支持 JS 渲染
    适合需要 JavaScript 渲染的复杂页面

    参数:
        url: 目标 URL
        wait_for: 可选，等待条件（如 "js:() => document.querySelector('.content')"）

    返回:
        {title, markdown, fit_markdown, links, media, success, error}
    """
    if not HAS_CRAWL4AI:
        return {"success": False, "error": "需要安装 crawl4ai: uv pip install crawl4ai"}

    try:
        kwargs = {"url": url, "bypass_cache": True, "word_count_threshold": 10}
        if wait_for:
            kwargs["wait_for"] = wait_for

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(**kwargs)

        if not result.success:
            return {"success": False, "error": f"爬取失败: {result.error_message}"}

        # 提取 markdown
        md = result.markdown
        raw_md = ""
        if hasattr(md, "raw_markdown"):
            raw_md = md.raw_markdown or ""

        # 提取标题（从 markdown 第一行）
        title = ""
        if raw_md:
            first_line = raw_md.strip().split("\n")[0]
            if first_line.startswith("# "):
                title = first_line[2:].strip()
            elif first_line.startswith("#"):
                title = first_line[1:].strip()

        # 提取链接
        links = {"internal": [], "external": []}
        if hasattr(result, "links") and result.links:
            links = result.links

        # 提取媒体
        media = {"images": [], "videos": [], "audios": []}
        if hasattr(result, "media") and result.media:
            media = result.media

        return {
            "success": True,
            "url": url,
            "title": title,
            "markdown": raw_md,
            "links": links,
            "media": media,
            "status_code": result.status_code,
            "html_len": len(result.html) if hasattr(result, "html") and result.html else 0,
        }

    except Exception as e:
        return {"success": False, "error": f"增强提取失败: {e}"}


# ===== 自动选择版 =====

async def extract(url: str, use_enhanced: bool = False, wait_for: str = None) -> dict:
    """
    自动选择提取方式
    默认用轻量版（快），需要 JS 渲染时用增强版

    参数:
        url: 目标 URL
        use_enhanced: 是否使用增强版（需要 crawl4ai）
        wait_for: 增强版等待条件
    """
    if use_enhanced and HAS_CRAWL4AI:
        return await extract_enhanced(url, wait_for)
    return extract_lightweight(url)


# ===== 测试 =====
async def test():
    print("=" * 60)
    print("轻量版测试")
    print("=" * 60)
    r = extract_lightweight("https://httpbin.org/html")
    print(f"  成功: {r.get('success')}")
    print(f"  标题: {r.get('title', '')[:100]}")
    print(f"  正文: {r.get('text', '')[:200]}")
    print(f"  链接数: {len(r.get('links', []))}")
    print(f"  图片数: {len(r.get('images', []))}")

    if HAS_CRAWL4AI:
        print("\n" + "=" * 60)
        print("增强版测试")
        print("=" * 60)
        r2 = await extract_enhanced("https://httpbin.org/html")
        print(f"  成功: {r2.get('success')}")
        print(f"  标题: {r2.get('title', '')[:100]}")
        print(f"  Markdown: {r2.get('markdown', '')[:200]}")
        print(f"  链接数: {len(r2.get('links', {}).get('internal', []) + r2.get('links', {}).get('external', []))}")

    print("\n✅ 测试完成")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test())