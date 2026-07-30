# =============================================================================
# AWBotNest 插件：自动报时昵称（myname）
#
# 定时把你的用户账号昵称改成当前时间+天气（按模板渲染）。
# 支持特殊字体数字（𝟏𝟔:𝟓𝟏）、天气图标、温度。
# 天气数据来源：wttr.in（免费，无需API Key）
# =============================================================================

import random
import httpx
from datetime import datetime, timedelta, timezone

__plugin__ = {
    "name": "自动报时昵称",
    "id": "myname",
    "version": "1.0.1",
    "author": "凹凸曼",
    "description": "定时把昵称改成当前时间+天气，支持特殊字体和天气图标。",
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        "interval_min": {
            "type": "slider", "default": 5, "label": "改名间隔(分钟)",
            "min": 1, "max": 60, "step": 1, "order": 10, "section": "更新计划",
            "help": "每隔多少分钟改一次。改这个值后需「重载」插件生效。",
        },
        "name_format": {
            "type": "string", "default": "{boldH}:{boldM} {weather_icon} {temp}°C", "label": "昵称模板",
            "order": 11, "section": "昵称规则",
            "help": "占位符: {boldH}:{boldM}特殊字体时:分  {H}:{M}普通时:分  {weather_icon}天气图标 {temp}温度 {emoji}随机表情 {date}日期 {week}星期",
        },
        "name_field": {
            "type": "select", "default": "last_name", "label": "改哪个名",
            "order": 12, "section": "昵称规则",
            "options": [
                {"value": "last_name", "label": "姓 (last name)"},
                {"value": "first_name", "label": "名 (first name)"},
                {"value": "both", "label": "姓和名都改"},
            ],
        },
        "location": {
            "type": "string", "default": "Guangzhou", "label": "城市(英文)",
            "order": 5, "section": "天气", "help": "城市英文名，如 Guangzhou/Beijing/Shanghai，或IP自动",
        },
        "weather_interval": {
            "type": "slider", "default": 30, "label": "天气刷新间隔(分钟)",
            "min": 10, "max": 120, "step": 5, "order": 6, "section": "天气",
            "help": "天气数据缓存时间，避免频繁请求",
        },
    },
}

DEFAULT_FORMAT = "{boldH}:{boldM} {weather_icon} {temp}°C"
_EMOJIS = [chr(i) for i in range(0x1F600, 0x1F637 + 1)]
_WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_TZ8 = timezone(timedelta(hours=8))

# 特殊字体数字映射（数学粗体）
_BOLD_DIGITS = str.maketrans("0123456789", "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗")


def _to_bold(s: str) -> str:
    return s.translate(_BOLD_DIGITS)


# 天气缓存
_WEATHER_CACHE = {"data": None, "time": 0}


async def _get_weather(location: str, cache_minutes: int = 30) -> dict:
    now = datetime.now(_TZ8).timestamp()
    if _WEATHER_CACHE["data"] and now - _WEATHER_CACHE["time"] < cache_minutes * 60:
        return _WEATHER_CACHE["data"]

    url = f"https://wttr.in/{location}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.get(url)
            if r.status_code == 200:
                data = r.json()
                current = data.get("current_condition", [{}])[0]
                result = {
                    "temp": current.get("temp_C", "?"),
                    "desc": current.get("weatherDesc", [{}])[0].get("value", ""),
                    "icon": _weather_code_to_icon(current.get("weatherCode", 0)),
                    "humidity": current.get("humidity", "?"),
                    "wind": current.get("windspeedKmph", "?"),
                }
                _WEATHER_CACHE["data"] = result
                _WEATHER_CACHE["time"] = now
                return result
    except Exception:
        pass
    return {"temp": "?", "desc": "", "icon": "🌤", "humidity": "?", "wind": "?"}


def _weather_code_to_icon(code: int) -> str:
    icons = {
        113: "☀️", 116: "⛅", 119: "☁️", 122: "☁️",
        143: "🌫", 176: "🌦", 179: "🌧", 182: "🌧",
        185: "🌧", 200: "⛈", 227: "🌨", 230: "🌨",
        248: "🌫", 260: "🌫", 263: "🌦", 266: "🌦",
        281: "🌧", 284: "🌧", 293: "🌦", 296: "🌦",
        299: "🌧", 302: "🌧", 305: "🌧", 308: "🌧",
        311: "🌧", 314: "🌧", 317: "🌧", 320: "🌨",
        323: "🌨", 326: "🌨", 329: "🌨", 332: "🌨",
        335: "🌨", 338: "🌨", 350: "🌧", 353: "🌦",
        356: "🌧", 359: "🌧", 362: "🌧", 365: "🌧",
        368: "🌨", 371: "🌨", 374: "🌧", 377: "🌧",
        386: "⛈", 389: "⛈", 392: "⛈", 395: "🌨",
    }
    return icons.get(code, "🌤")


def _render_name(fmt: str, now: datetime, weather: dict) -> str:
    return (
        fmt.replace("{emoji}", random.choice(_EMOJIS))
        .replace("{H}", now.strftime("%H"))
        .replace("{M}", now.strftime("%M"))
        .replace("{S}", now.strftime("%S"))
        .replace("{boldH}", _to_bold(now.strftime("%H")))
        .replace("{boldM}", _to_bold(now.strftime("%M")))
        .replace("{boldS}", _to_bold(now.strftime("%S")))
        .replace("{date}", now.strftime("%Y-%m-%d"))
        .replace("{md}", now.strftime("%m-%d"))
        .replace("{week}", _WEEK_CN[now.weekday()])
        .replace("{weather_icon}", weather.get("icon", "🌤"))
        .replace("{temp}", str(weather.get("temp", "?")))
        .replace("{desc}", weather.get("desc", ""))
        .replace("{humidity}", str(weather.get("humidity", "?")))
        .replace("{wind}", str(weather.get("wind", "?")))
    )


def _make_action(ctx):
    async def _action():
        user_apps = ctx.user_apps
        if not user_apps:
            return

        cfg = ctx.config
        fmt = cfg.get("name_format") or DEFAULT_FORMAT
        field = cfg.get("name_field") or "last_name"
        location = cfg.get("location", "Guangzhou") or "Guangzhou"
        weather_interval = int(cfg.get("weather_interval", 30) or 30)
        now = datetime.now(_TZ8)

        weather = await _get_weather(location, weather_interval)

        for app in user_apps:
            try:
                rendered = _render_name(fmt, now, weather)
                kwargs = {}
                if field in ("last_name", "both"):
                    kwargs["last_name"] = rendered
                if field in ("first_name", "both"):
                    kwargs["first_name"] = rendered
                if not kwargs:
                    kwargs["last_name"] = rendered
                await app.update_profile(**kwargs)
                ctx.log.info("[自动报时] 已改名为: %s", rendered)
            except Exception as e:
                ctx.log.warning("[自动报时] 改名失败: %r", e)

    return _action


async def setup(ctx):
    try:
        interval = int(ctx.config.get("interval_min", 5) or 5)
    except (ValueError, TypeError):
        interval = 5
    interval = max(1, min(interval, 60))

    ctx.schedule(_make_action(ctx), "interval", minutes=interval, id="自动报时昵称")
    ctx.log.info("[自动报时] 已启用，每 %d 分钟，城市: %s", interval, ctx.config.get("location", "Guangzhou"))


async def teardown(ctx):
    pass