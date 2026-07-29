# -*- coding: utf-8 -*-
# 测试：使用平台浏览器搜索抖音
import asyncio, json, re
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=8))

async def test_browser_search(ctx):
    """测试用浏览器搜索抖音"""
    keyword = "风景"
    url = f"https://www.douyin.com/search/{keyword}?type=video"
    
    print(f"正在用浏览器搜索抖音: {keyword}")
    
    try:
        # 方法1: 获取页面源码
        html = await ctx.browser.page_source(url, timeout=60)
        print(f"页面获取成功, 长度: {len(html)}")
        
        # 提取视频信息
        # 抖音页面数据通常在 <script> 标签或 window.__INITIAL_STATE__ 中
        m = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', html, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            print(f"找到 __INITIAL_STATE__")
            # 提取视频列表
            videos = []
            # 尝试不同的路径
            for path in ['wordList', 'searchData', 'videoList', 'awemeList']:
                items = data.get(path, [])
                if items:
                    print(f"  {path}: {len(items)}条")
                    for v in items[:5]:
                        desc = v.get('desc', v.get('title', ''))
                        print(f"    {desc[:50]}")
                    break
        else:
            print("未找到 __INITIAL_STATE__")
            # 试试用正则提取视频数据
            urls = re.findall(r'https://www\.douyin\.com/video/(\d+)', html)
            print(f"找到 {len(urls)} 个视频链接")
            for u in urls[:5]:
                print(f"  https://www.douyin.com/video/{u}")
    
    except Exception as e:
        print(f"方法1失败: {e}")
    
    try:
        # 方法2: 用浏览器运行JS提取数据
        data = await ctx.browser.run(url, lambda p: p.inner_text("body"), headless=True)
        print(f"\n方法2(JS提取): {data[:200]}")
    except Exception as e:
        print(f"方法2失败: {e}")

# 这个测试需要在实际插件环境中运行
# 先保存为测试代码，等插件加载后调用
print("测试代码已保存，需在插件中运行")