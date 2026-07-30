# -*- coding: utf-8 -*-
# videodl 原生引擎（纯Python，100+平台）
# 使用 CharlesPikachu/videodl 的 VideoClient
# 同步安装，模块加载时自动完成

import subprocess
import sys
from pathlib import Path


def _install() -> bool:
    """同步安装 videofetch"""
    # 先检查是否已安装
    try:
        from videodl.modules import VideoClientBuilder, BuildVideoClient  # noqa: F401
        return True
    except ImportError:
        pass

    python = sys.executable
    vendor_wheel = Path(__file__).parent / "_vendor" / "videofetch-0.9.1-py3-none-any.whl"
    proxy = "http://192.168.1.33:7890"

    # 尝试安装方式
    installers = []

    # 1. 本地 wheel（最快）
    if vendor_wheel.exists():
        installers.append([python, "-m", "pip", "install", str(vendor_wheel), "-q", "--timeout", "30"])
        installers.append([python, "-m", "pip", "install", str(vendor_wheel), "-q", "--no-deps", "--timeout", "30"])

    # 2. 在线安装（带代理）
    for pip_cmd in [
        [python, "-m", "pip"],
        ["pip3"],
        ["pip"],
    ]:
        installers.append(pip_cmd + ["install", "videofetch==0.9.1", "-q", "--proxy", proxy, "--timeout", "30"])
        installers.append(pip_cmd + ["install", "videofetch==0.9.1", "-q", "--timeout", "30"])

    # 3. uv 兜底
    installers.append(["uv", "pip", "install", "videofetch==0.9.1"])

    for installer in installers:
        try:
            r = subprocess.run(installer, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                continue
            from videodl.modules import VideoClientBuilder, BuildVideoClient  # noqa: F401
            return True
        except Exception:
            continue

    return False


HAS_VIDEODL = _install()


def is_available() -> bool:
    return HAS_VIDEODL


async def parse_via_videodl(url: str) -> dict | None:
    """用 videodl 原生引擎解析链接"""
    if not HAS_VIDEODL:
        return {"error": "videodl 引擎未安装"}

    from videodl.modules import VideoClientBuilder, BuildVideoClient

    loop = asyncio.get_running_loop()

    # 找出匹配的客户端
    matched_clients = []
    for name, cls in VideoClientBuilder.REGISTERED_MODULES.items():
        try:
            if cls.belongto(url):
                matched_clients.append(name)
        except Exception:
            continue

    if not matched_clients:
        return None  # 没有匹配的平台客户端

    for vc_name in matched_clients:
        try:
            result = await loop.run_in_executor(None, _try_parse, vc_name, url, BuildVideoClient)
            if result:
                return result
        except Exception:
            continue

    return None


def _try_parse(vc_name: str, url: str, BuildVideoClient) -> dict | None:
    """尝试用指定客户端解析"""
    import time
    start = time.time()

    client = BuildVideoClient(module_cfg={
        "type": vc_name,
        "auto_set_proxies": False,
        "random_update_ua": False,
        "max_retries": 1,
        "disable_print": True,
        "maintain_session": False,
    })

    results = client.parsefromurl(url)

    if not results:
        return None

    # 找有下载地址的结果
    video_info = None
    for v in results:
        if hasattr(v, 'with_valid_download_url') and v.with_valid_download_url:
            video_info = v
            break
    if not video_info and results:
        video_info = results[0]

    if not video_info:
        return None

    download_url = getattr(video_info, 'download_url', '') or ''
    if not download_url:
        return None

    title = getattr(video_info, 'title', '') or '视频'
    cover_url = getattr(video_info, 'cover_url', '') or ''
    ext = getattr(video_info, 'ext', 'mp4') or 'mp4'

    platform_name = _PLATFORM_MAP.get(vc_name, vc_name.replace("VideoClient", ""))
    media_type = "image" if ext in ("jpg", "jpeg", "png", "gif", "webp") else "video"

    return {
        "platform": platform_name,
        "platform_name": platform_name,
        "title": title,
        "media": [{"url": download_url, "type": media_type}],
        "thumbnail": cover_url,
        "source": "videodl",
    }


# 平台名映射
_PLATFORM_MAP = {
    "DouyinVideoClient": "抖音", "BilibiliVideoClient": "B站",
    "KuaishouVideoClient": "快手", "RednoteVideoClient": "小红书",
    "WeiboVideoClient": "微博", "ZhihuVideoClient": "知乎",
    "BaiduTiebaVideoClient": "贴吧", "AcFunVideoClient": "A站",
    "IQiyiVideoClient": "爱奇艺", "MGTVVideoClient": "芒果TV",
    "TencentVideoClient": "腾讯视频", "SohuVideoClient": "搜狐",
    "LeshiVideoClient": "乐视", "CCTVVideoClient": "央视网",
    "HuyaVideoClient": "虎牙", "EyepetizerVideoClient": "开眼",
    "DongchediVideoClient": "懂车帝", "HaokanVideoClient": "好看视频",
    "PearVideoClient": "梨视频", "MeipaiVideoClient": "美拍",
    "KugouMVVideoClient": "酷狗MV", "Ku6VideoClient": "酷6",
    "Open163VideoClient": "网易公开课", "CCtalkVideoClient": "CCtalk",
    "ChinaDailyVideoClient": "中国日报", "HuanQiuVideoClient": "环球网",
    "DuxiaoshiVideoClient": "度小视", "C56VideoClient": "56视频",
    "CCTVNewsVideoClient": "央视新闻", "ZuiyouVideoClient": "最右",
    "PipixVideoClient": "皮皮虾", "XiguaVideoClient": "西瓜视频",
    "WeishiVideoClient": "微视", "YinyuetaiVideoClient": "音悦台",
    "WeSingVideoClient": "全民K歌", "XinpianchangVideoClient": "新片场",
    "KanKanNewsVideoClient": "看看新闻", "XinhuaNetVideoClient": "新华网",
    "PeopleVideoClient": "人民网", "MingpaoVideoClient": "明报",
    "OrientalDailyVideoClient": "东方日报", "MyVideoGeVideoClient": "MyVideoGe",
    "NewsPicksVideoClient": "NewsPicks", "IYFVideoClient": "iYF.tv",
    "YouTubeVideoClient": "YouTube", "DailyMotionVideoClient": "Dailymotion",
    "RutubeVideoClient": "Rutube", "RedditVideoClient": "Reddit",
    "TedVideoClient": "TED", "FoxNewsVideoClient": "FoxNews",
    "ArteTVVideoClient": "ArteTV", "KakaoVideoClient": "Kakao",
    "GeniusVideoClient": "Genius", "BeaconVideoClient": "Beacon",
    "ABCVideoClient": "ABC", "WWEVideoClient": "WWE",
    "NuVidVideoClient": "NuVid", "UnityVideoClient": "Unity",
    "TBNUKVideoClient": "TBNUK", "PlayerPLVideoClient": "PlayerPL",
    "WittyTVVideoClient": "WittyTV", "SixRoomVideoClient": "六间房",
    "SinaVideoClient": "新浪视频", "M1905VideoClient": "1905电影网",
    "PipigaoxiaoVideoClient": "皮皮搞笑", "OasisVideoClient": "绿洲",
    "CCCVideoClient": "CC视频", "XuexiCNVideoClient": "学习强国",
    "WWW163VideoClient": "网易",
}