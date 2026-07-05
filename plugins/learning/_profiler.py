# =============================================================================
# 学习插件：话题画像 + 说话风格学习
# =============================================================================
import json
import re
import time
from collections import deque

from ._engine import generate

# 自己消息缓冲：chat_id -> deque[str]
_msg_buf: dict[int, deque] = {}
_BUF_MAX = 100

# 全消息缓冲
_all_buf: dict[int, deque] = {}
_ALL_MAX = 200

# 未总结计数器
_buf_counter: dict[int, int] = {}

# （全消息缓冲供 summarize 取上下文）

# kv key 模板
_PROFILE_KEY = "profile:{}"
_COUNTER_KEY = "bufcnt:{}"
# 说话风格直接存在 profile['voice']['style_prompt'] 中，无需单独 KV key

_JSON_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    m = _JSON_PATTERN.search(text)
    if m:
        text = m.group(1).strip()
    for candidate in (text, text.removeprefix("`").removesuffix("`")):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


# ── 话题画像访问 ─────────────────────────────────────────────────────

def get_profile(chat_id: int, kv) -> dict:
    return kv.get(_PROFILE_KEY.format(chat_id), {})


# （说话风格直接读 profile['voice']['style_prompt']，无需独立访问函数）


# ── 缓冲操作 ────────────────────────────────────────────────────────

def push_own_message(chat_id: int, text: str, kv):
    buf = _msg_buf.setdefault(chat_id, deque(maxlen=_BUF_MAX))
    buf.append(text)
    cnt = _buf_counter.get(chat_id, 0) + 1
    _buf_counter[chat_id] = cnt
    kv.set(_COUNTER_KEY.format(chat_id), cnt)


def push_all_message(chat_id: int, text: str, user_id: int, name: str):
    buf = _all_buf.setdefault(chat_id, deque(maxlen=_ALL_MAX))
    buf.append({"text": text, "user_id": user_id, "name": name, "ts": time.time()})


def _build_context_str(chat_id: int, n: int) -> str:
    buf = _all_buf.get(chat_id)
    if not buf:
        return ""
    recent = list(buf)[-n:]
    lines = []
    for m in recent:
        sender = m.get("name", f"user_{m['user_id']}")
        lines.append(f"| {sender}: {m['text']}")
    return "\n".join(lines)


def get_message_count(kv, chat_id: int) -> int:
    return _buf_counter.get(chat_id, 0)



def reset_counter(chat_id: int, kv):
    _buf_counter[chat_id] = 0
    kv.set(_COUNTER_KEY.format(chat_id), 0)


def get_recent_own_messages(chat_id: int, n: int) -> list[str]:
    buf = _msg_buf.get(chat_id)
    if not buf:
        return []
    return list(buf)[-n:]


def _safe_str(v) -> str:
    """将任意类型的值安全转为去除首尾空白的字符串。"""
    return str(v or "").strip()


# ── LLM 总结（话题 + 风格一起出）────────────────────────────────────

async def summarize(chat_id: int, kv, cfg, own_messages: list[str]) -> dict | None:
    """对该群做一次 LLM 话题总结 + 说话风格分析，**合并**保有画像。

    合并策略：
      - topics / keywords → 新旧取并集（去重）
      - voice.habits → 新旧取并集（去重）
      - voice.tone / avg_words / punctuation / emoji_freq → 用最新值
      - voice.style_prompt → LLM 在 prompt 中合并新旧风格，直接取最新结果
      失败则保留旧数据不变。
    """
    if not own_messages:
        return None

    context_str = _build_context_str(chat_id, cfg.max_context_lines)
    own_str = "\n".join(f"| 我: {m}" for m in own_messages)

    # 加载旧画像（用于在 prompt 中给出旧风格信息，让 LLM 合并）
    old_profile = get_profile(chat_id, kv)
    old_voice = old_profile.get("voice", {}) if isinstance(old_profile.get("voice"), dict) else {}
    old_style = (old_voice.get("style_prompt") or "").strip()

    prompt = cfg.profile_prompt_template.format(
        context=context_str,
        my_messages=own_str,
    )

    if old_style:
        prompt += (
            f"\n\n【之前的风格描述】\n{old_style}\n\n"
            f"【合并要求】把之前的风格描述和上面最新消息结合起来，"
            f"在 style_prompt 字段输出一段 **合并后的完整描述**（≤150字），"
            f"不要分点、不要标注『之前』『补充』——必须合并成一段连贯的话。\n"
            f"如果新的消息没有额外信息，保持原来的描述不变。"
        )

    messages = [
        {"role": "system", "content": "你是一个用户行为分析助手。只输出 JSON，不要多余文字。"},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = await generate(cfg.api_key, cfg.base_url, cfg.model, messages)
    except Exception:
        return None

    if not raw:
        return None

    parsed = _extract_json(raw)
    if not parsed:
        return old_profile if old_profile.get("ready") else {"topics": [], "keywords": [], "summary": "", "ready": False}
    else:
        # —— 话题、关键词：并集 ——
        new_topics = {str(t).strip() for t in parsed.get("topics", []) if t}
        old_topics = {str(t).strip() for t in old_profile.get("topics", []) if t}
        merged_topics = list(old_topics | new_topics)

        new_kws = {str(kw).strip().lower() for kw in parsed.get("keywords", []) if kw}
        old_kws = {str(kw).strip().lower() for kw in old_profile.get("keywords", []) if kw}
        merged_kws = list(old_kws | new_kws)

        profile = {
            "topics": merged_topics,
            "keywords": merged_kws,
            "summary": str(parsed.get("summary", "") or ""),
            "ready": True,
            "updated_ts": time.time(),
        }

        # —— voice 数据：合并各子维度 ——
        voice_data = parsed.get("voice")
        if isinstance(voice_data, dict):
            # 口癖并集
            new_habits = {str(h).strip() for h in voice_data.get("habits", []) if h}
            old_habits = {str(h).strip() for h in old_voice.get("habits", []) if h}
            merged_habits = list(old_habits | new_habits)

            # 标量字段：新值优先，新值空时保留旧值
            merged_voice = {
                "tone": _safe_str(voice_data.get("tone")) or _safe_str(old_voice.get("tone")),
                "avg_words": _safe_str(voice_data.get("avg_words")) or _safe_str(old_voice.get("avg_words")),
                "habits": merged_habits,
                "punctuation": _safe_str(voice_data.get("punctuation")) or _safe_str(old_voice.get("punctuation")),
                "emoji_freq": _safe_str(voice_data.get("emoji_freq")) or _safe_str(old_voice.get("emoji_freq")),
            }

            # style_prompt：LLM 已在 prompt 中合并旧风格，直接用新结果
            new_style = (voice_data.get("style_prompt") or "").strip()
            if new_style:
                merged_voice["style_prompt"] = new_style
            elif old_style:
                merged_voice["style_prompt"] = old_style

            profile["voice"] = merged_voice

        # —— 关键词热度：新词初始化 + 淘汰 ——
        kw_heat = profile.get("keyword_heat", {})
        now = time.time()
        for kw in merged_kws:
            if kw not in kw_heat:
                kw_heat[kw] = {"count": 0, "last_use": 0, "created_ts": now}
        profile["keyword_heat"] = kw_heat

        max_kw = getattr(cfg, "max_keywords", 20)
        if len(merged_kws) > max_kw:
            _prune_inplace(profile, max_kw)

    kv.set(_PROFILE_KEY.format(chat_id), profile)
    return profile


def clear():
    _msg_buf.clear()
    _all_buf.clear()
    _buf_counter.clear()


def _prune_inplace(profile: dict, max_keywords: int):
    """对内存中的 profile dict 执行关键词裁剪（不读写 KV）。
    
    评分公式：count × 10 + 最近使用奖赏(0~5)
    - 从未触发参与且创建>7天的词直接淘汰
    - 按分数降序保留前 max_keywords 个
    """
    keywords = profile.get("keywords", [])
    if not keywords or len(keywords) <= max_keywords:
        return
    heat = profile.get("keyword_heat", {})
    now = time.time()
    seven_days = 7 * 86400

    kw_scores = {}
    for kw in keywords:
        entry = heat.get(kw, {})
        manual_count = entry.get("manual_count", 0)
        count = entry.get("count", 0)
        last_use = entry.get("last_use", 0)
        created_ts = entry.get("created_ts", 0)
        # 从未触发过且创建超过7天 → 直接淘汰
        if manual_count == 0 and count == 0 and created_ts > 0 and (now - created_ts) > seven_days:
            continue
        # 最近使用奖赏
        if last_use > 0:
            days_since = (now - last_use) / 86400
            recency = max(0, 30 - days_since) / 30 * 5
        else:
            recency = 0
        kw_scores[kw] = manual_count * 10 + count + recency

    sorted_kws = sorted(kw_scores.keys(), key=lambda k: kw_scores[k], reverse=True)
    kept = sorted_kws[:max_keywords]
    profile["keywords"] = kept
    profile["keyword_heat"] = {k: v for k, v in heat.items() if k in kept}


# 分隔符集合 + 简单关键词提取（独立于 _judger 以避免循环导入）
_DELIMITERS = set(
    ' \t\n\r,，。！？、；：""\'\''
    '（）()'
    '[]【】'
    '/\\|@#'
    '$%^&*+=~`<>《》'
)


def _extract_keywords(text: str) -> set[str]:
    tokens = []
    current: list[str] = []
    for ch in text:
        if ch in _DELIMITERS:
            if current:
                tokens.append(''.join(current))
                current = []
        else:
            current.append(ch)
    if current:
        tokens.append(''.join(current))
    stopwords = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那",
        "什么", "怎么", "为啥", "吗", "呢", "啊", "吧", "嗯", "哦",
        "the", "a", "an", "is", "are", "was", "were", "it", "this",
        "that", "to", "in", "of", "for", "on", "and", "or", "with",
    }
    result = set()
    for t in tokens:
        t = t.strip().lower()
        if len(t) < 2 or t in stopwords or t.isdigit():
            continue
        result.add(t)
    return result


def update_keyword_heat(chat_id: int, kv, matched_keyword: str):
    """关键词参与热度+1，更新最后参与时间。"""
    profile = get_profile(chat_id, kv)
    if not profile:
        return
    heat = profile.get("keyword_heat", {})
    entry = heat.get(matched_keyword)
    now = time.time()
    if entry:
        entry["count"] = entry.get("count", 0) + 1
        entry["last_use"] = now
    else:
        heat[matched_keyword] = {"count": 1, "last_use": now, "created_ts": now}
    profile["keyword_heat"] = heat
    profile["updated_ts"] = now
    kv.set(_PROFILE_KEY.format(chat_id), profile)


def update_manual_keyword_heat(chat_id: int, kv, text: str) -> dict:
    """手动消息热词追踪：从用户手动发送的消息中匹配关键词并累积 manual_count。

    对消息文本做关键词提取，与画像 keywords 做子串匹配 + token 匹配，
    命中的关键词 manual_count +1，仅以手动发送消息为准。

    返回 dict 供调用方记录日志：
      - {"reason": "no_ready_profile"}  —— 画像尚未 ready
      - {"reason": "no_keywords"}        —— 画像无关键词
      - {"matched": [...], "new": [...]} —— 正常处理结果
    """
    profile = get_profile(chat_id, kv)
    if not profile or not profile.get("ready"):
        return {"reason": "no_ready_profile"}
    kw_list = profile.get("keywords", [])
    if not kw_list:
        return {"reason": "no_keywords"}

    msg_tokens = _extract_keywords(text)
    text_lower = text.lower()
    heat = profile.get("keyword_heat", {})
    now = time.time()
    matched_kws: list[str] = []
    new_kws: list[str] = []
    has_update = False

    for kw in kw_list:
        kw_lower = kw.lower()
        matched = kw_lower in text_lower or any(
            kw_lower in mk or mk in kw_lower for mk in msg_tokens
        )
        if matched:
            entry = heat.get(kw)
            if entry:
                entry["manual_count"] = entry.get("manual_count", 0) + 1
                entry["last_manual_use"] = now
                entry["last_use"] = now
                matched_kws.append(kw)
            else:
                heat[kw] = {
                    "count": 0, "manual_count": 1,
                    "last_use": now, "last_manual_use": now,
                    "created_ts": now,
                }
                new_kws.append(kw)
            has_update = True

    if has_update:
        profile["keyword_heat"] = heat
        profile["updated_ts"] = now
        kv.set(_PROFILE_KEY.format(chat_id), profile)

    return {"matched": matched_kws, "new": new_kws}


def prune_keywords(chat_id: int, kv, max_keywords: int):
    """从 KV 读取画像，执行关键词裁剪并写回。"""
    profile = get_profile(chat_id, kv)
    if not profile:
        return
    _prune_inplace(profile, max_keywords)
    kv.set(_PROFILE_KEY.format(chat_id), profile)


def format_keywords_display(profile: dict, chat_id: int) -> str:
    """按手动消息命中热度降序格式化关键词展示文本。"""
    keywords = profile.get("keywords", [])
    heat = profile.get("keyword_heat", {})
    if not keywords:
        return "（暂无自动学习的关键词，发送消息后自动生成）"
    # 按手动消息命中次数降序，相同按最后命中时间降序
    def _sort_key(kw):
        entry = heat.get(kw, {})
        manual_count = entry.get("manual_count", 0)
        last_manual = entry.get("last_manual_use", entry.get("last_use", 0))
        return (manual_count, last_manual)
    sorted_kws = sorted(keywords, key=_sort_key, reverse=True)
    lines = [f"群 {chat_id}"]
    for kw in sorted_kws:
        entry = heat.get(kw, {})
        manual_count = entry.get("manual_count", 0)
        if manual_count > 0:
            lines.append(f"  {kw}（手动{manual_count}次）")
        else:
            lines.append(f"  {kw}（未手动发送过）")
    return "\n".join(lines)


def get_context_lines(chat_id: int, n: int) -> list[str]:
    """获取触发消息之前的 N 条群聊上下文文本（排除当前消息）。
    
    handler2 (group=11) 已把当前消息 push 进 _all_buf，
    所以取倒数 n+1 条 ~ 倒数第 2 条 = 最近 N 条上文。
    不足 N 条时返回全部（不含当前消息）。
    """
    buf = _all_buf.get(chat_id)
    if not buf or len(buf) < 2:
        return []
    recent = list(buf)[-(n + 1):-1]
    return [m.get("text", "") for m in recent if m.get("text")]
