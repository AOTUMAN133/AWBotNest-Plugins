#!/usr/bin/env python3
"""ParseHub 桥接脚本 - 被插件通过子进程调用"""
import sys
import os
import subprocess
import json

# 尝试导入 parsehub，如果失败则自动安装
def _ensure_parsehub():
    try:
        from parsehub import ParseHub
        return True
    except ImportError:
        pass
    python = sys.executable
    for installer in [
        [python, "-m", "pip", "install", "parsehub", "-q"],
        ["uv", "pip", "install", "parsehub"],
    ]:
        try:
            subprocess.run(installer, capture_output=True, text=True, timeout=60)
            from parsehub import ParseHub
            return True
        except Exception:
            pass
    return False

if not _ensure_parsehub():
    print(json.dumps({"error": "parsehub 安装失败，请手动执行: pip install parsehub"}))
    sys.exit(1)

import asyncio

os.environ.setdefault("PARSEHUB_DOUYIN_DEVICE_ID", "")
os.environ.setdefault("PARSEHUB_DOUYIN_IID", "")

async def parse_url(url: str) -> dict:
    from parsehub import ParseHub
    ph = ParseHub()
    platform = ph.get_platform(url)
    if not platform:
        return {"error": f"不支持的平台: {url}"}
    try:
        raw_url = await ph.get_raw_url(url, clean_all=False)
        if raw_url and raw_url != url:
            url = raw_url
    except Exception:
        pass
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
    if hasattr(result, "video") and result.video:
        out["media"].append({
            "type": "video", "url": result.video.url,
            "width": result.video.width, "height": result.video.height,
            "duration": result.video.duration, "thumb_url": result.video.thumb_url or "",
        })
    if hasattr(result, "photo") and result.photo:
        for p in (result.photo if isinstance(result.photo, list) else [result.photo]):
            out["media"].append({"type": "image", "url": p.url, "width": p.width, "height": p.height})
    if hasattr(result, "media") and result.media:
        for m in (result.media if isinstance(result.media, list) else [result.media]):
            if hasattr(m, "url") and m.url:
                mt = type(m).__name__
                if "Video" in mt:
                    out["media"].append({"type": "video", "url": m.url, "width": getattr(m,"width",0), "height": getattr(m,"height",0), "duration": getattr(m,"duration",0), "thumb_url": getattr(m,"thumb_url","") or ""})
                elif "Image" in mt:
                    out["media"].append({"type": "image", "url": m.url, "width": getattr(m,"width",0), "height": getattr(m,"height",0)})
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