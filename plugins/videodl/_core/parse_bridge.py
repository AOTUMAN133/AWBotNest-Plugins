#!/usr/bin/env python3
"""ParseHub 桥接脚本 - 被插件通过子进程调用"""
import sys
import os

# 添加 venv 的 site-packages 到路径（确保 parsehub 可导入）
_venv_sp = "/root/.hermes/plugins_env/ph_venv3/lib/python3.13/site-packages"
if os.path.isdir(_venv_sp) and _venv_sp not in sys.path:
    sys.path.insert(0, _venv_sp)

import asyncio
import json

os.environ.setdefault("PARSEHUB_DOUYIN_DEVICE_ID", "")
os.environ.setdefault("PARSEHUB_DOUYIN_IID", "")

async def parse_url(url: str) -> dict:
    from parsehub import ParseHub, UnknownPlatform
    ph = ParseHub()
    
    # 先检查平台是否支持
    platform = ph.get_platform(url)
    if not platform:
        return {"error": f"不支持的平台: {url}"}
    
    # 先解析短链，获取原始链接
    try:
        raw_url = await ph.get_raw_url(url, clean_all=False)
        if raw_url and raw_url != url:
            url = raw_url
    except Exception:
        pass
    
    # 解析
    try:
        result = await ph.parse(url)
    except Exception as e:
        return {"error": str(e)}
    
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