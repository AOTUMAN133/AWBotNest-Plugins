#!/usr/bin/env python3
"""ParseHub 桥接脚本 - 被插件通过子进程调用"""
import asyncio
import json
import sys
import os

# 确保在 Python 3.12 的 venv 中运行
os.environ.setdefault("PARSEHUB_DOUYIN_DEVICE_ID", "")
os.environ.setdefault("PARSEHUB_DOUYIN_IID", "")

async def parse_url(url: str) -> dict:
    from parsehub import ParseHub
    ph = ParseHub()
    result = await ph.parse(url)
    
    out = {
        "platform": result.platform.id if result.platform else "unknown",
        "platform_name": result.platform.display_name if result.platform else "未知",
        "type": result.type.value if hasattr(result, "type") else "unknown",
        "title": result.title or "",
        "content": result.content or "",
        "media": [],
    }
    
    # 处理视频
    if hasattr(result, "video") and result.video:
        out["media"].append({
            "type": "video",
            "url": result.video.url,
            "width": result.video.width,
            "height": result.video.height,
            "duration": result.video.duration,
            "thumb_url": result.video.thumb_url or "",
        })
    
    # 处理图片
    if hasattr(result, "photo") and result.photo:
        for p in (result.photo if isinstance(result.photo, list) else [result.photo]):
            out["media"].append({
                "type": "image",
                "url": p.url,
                "width": p.width,
                "height": p.height,
            })
    
    # 处理 media 列表
    if hasattr(result, "media") and result.media:
        media_list = result.media if isinstance(result.media, list) else [result.media]
        for m in media_list:
            if hasattr(m, "url") and m.url:
                mt = type(m).__name__
                if "Video" in mt:
                    out["media"].append({
                        "type": "video",
                        "url": m.url,
                        "width": getattr(m, "width", 0),
                        "height": getattr(m, "height", 0),
                        "duration": getattr(m, "duration", 0),
                        "thumb_url": getattr(m, "thumb_url", "") or "",
                    })
                elif "Image" in mt:
                    out["media"].append({
                        "type": "image",
                        "url": m.url,
                        "width": getattr(m, "width", 0),
                        "height": getattr(m, "height", 0),
                    })
    
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: parse_bridge.py <url>"}))
        sys.exit(1)
    
    url = sys.argv[1]
    try:
        result = asyncio.run(parse_url(url))
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)