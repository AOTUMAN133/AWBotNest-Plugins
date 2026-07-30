# -*- coding: utf-8 -*-
# videodl 原生引擎（纯Python，100+平台）
# 使用 CharlesPikachu/videodl 的 VideoClient
# 异步后台安装，不阻塞插件启动

import asyncio
import subprocess
import sys

# 初始状态：未安装
_engine_available = False
_install_attempted = False


def is_available() -> bool:
    return _engine_available


async def try_install():
    """后台安装 videofetch，不阻塞插件启动"""
    global _engine_available, _install_attempted
    if _install_attempted:
        return
    _install_attempted = True

    # 先检查是否已安装
    try:
        from videodl.modules import VideoClientBuilder, BuildVideoClient  # noqa: F401
        _engine_available = True
        return
    except ImportError:
        pass

    # 尝试 pip 安装（先装全量，再试 --no-deps）
    python = sys.executable
    for installer in [
        [python, "-m", "pip", "install", "videofetch==0.9.1", "-q", "--timeout", "120"],
        [python, "-m", "pip", "install", "videofetch==0.9.1", "-q", "--no-deps"],
        ["pip3", "install", "videofetch==0.9.1", "-q", "--timeout", "120"],
        ["pip", "install", "videofetch==0.9.1", "-q", "--timeout", "120"],
        ["uv", "pip", "install", "videofetch==0.9.1"],
    ]:
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, lambda: subprocess.run(
                installer, capture_output=True, text=True, timeout=180
            ))
            from videodl.modules import VideoClientBuilder, BuildVideoClient  # noqa: F401
            _engine_available = True
            return
        except Exception:
            continue


async def parse_via_videodl(url: str) -> dict | None:
    """用 videodl 原生引擎解析链接"""
    if not _engine_available:
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