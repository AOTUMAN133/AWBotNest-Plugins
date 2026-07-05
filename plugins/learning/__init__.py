# =============================================================================
# AWBotNest 插件：智能学习参与（learning）
#
# 通过学习你的聊天偏好和说话风格，在匹配话题的群聊中智能参与对话。
# 冷启动：未学到话题偏好前不参与任何群聊。
#
# 工作流程：
#   1. 监听自己发的消息 → 记录到缓冲，每 N 条（summarize_gap）做一次
#      LLM 话题+风格总结，建立该群的偏好画像 + 全局说话风格。
#   2. 监听所有群消息 → 全量缓冲（供 summarize 取上下文参考）。
#   3. 当群聊中有人发消息匹配画像的关键词/话题 → 按概率 roll，
#      通过则用学到的说话风格生成自然回复。
#   4. group ID 配置：一行一个，留空 = 不监听任何群。
#
# 默认不启用，手动打开后需要发一些消息让插件学习。
# =============================================================================
import time
import traceback

from ._config import parse_config
from ._judger import should_participate
from ._participator import participate
from ._profiler import (
    clear,
    format_keywords_display,
    get_context_lines,
    get_message_count,
    get_profile,
    get_recent_own_messages,
    push_all_message,
    push_own_message,
    reset_counter,
    summarize,
    update_manual_keyword_heat,
)
from ._social import record

__plugin__ = {
    "name": "智能学习",
    "id": "learning",
    "version": "2.7.0",
    "author": "Yy",
    "description": (
        "学习你的聊天偏好和说话风格，在匹配话题的群聊中智能参与对话。"
        "冷启动：未学到偏好前不参与。"
    ),
    "scope": "user",
    "default_enabled": False,
    "config_schema": {
        # —— 接口 ——
        "api_key": {
            "type": "password", "default": "", "label": "API Key",
            "section": "接口", "help": "OpenAI 兼容接口的密钥。",
        },
        "base_url": {
            "type": "string", "default": "", "label": "接口地址(Base URL)",
            "section": "接口", "help": "OpenAI 兼容接口地址，留空用官方默认。",
        },
        "model": {
            "type": "string", "default": "gpt-3.5-turbo", "label": "模型",
            "section": "接口", "help": "用于话题风格分析和参与回复。",
        },
        # —— 学习 ——
        "summarize_gap": {
            "type": "slider", "default": 10, "label": "总结间隔(条)",
            "min": 3, "max": 100, "step": 1, "section": "学习",
            "help": "每发这么多条消息，就总结一次话题偏好。越小越灵敏、越费 token。",
        },
        "max_context_lines": {
            "type": "slider", "default": 5, "label": "总结上下文行数",
            "min": 1, "max": 20, "step": 1, "section": "学习",
            "help": "总结时读取每条自己消息前 N 条群聊上下文作为参考。",
        },
        # —— 群组 ——
        "target_groups": {
            "type": "text", "default": "",
            "label": "监听群组",
            "section": "群组",
            "help": (
                "监听这些群组的消息来学习和参与。\n"
                "每个群 ID 一行，也兼容逗号分隔。\n"
                "留空 = 不监听任何群。"
            ),
        },
        # —— 参与 ——
        "enable_participation": {
            "type": "boolean", "default": True, "label": "启用智能参与",
            "section": "参与",
        },
        "participation_rate": {
            "type": "slider", "default": 20, "label": "参与概率(%)",
            "min": 1, "max": 100, "step": 1, "section": "参与",
            "show_if": {"enable_participation": True},
            "help": "匹配到偏好话题时，按此概率实际参与回复。20 = 20%概率。",
        },
        "participation_context_lines": {
            "type": "slider", "default": 5, "label": "参与时读取上文(条)",
            "min": 1, "max": 20, "step": 1, "section": "参与",
            "show_if": {"enable_participation": True},
            "help": "触发关键词参与时，读取最近 N 条群聊上文给 LLM 参考，减少乱说话。",
        },
        "min_participation_gap": {
            "type": "slider", "default": 60, "label": "发言冷却(秒)",
            "min": 10, "max": 600, "step": 10, "section": "参与",
            "show_if": {"enable_participation": True},
            "help": "每个群两次成功参与发言的最小间隔，防止刷屏。",
        },
        # —— 关键词（手动补充） ——
        "keywords": {
            "type": "text", "default": "", "label": "关键词（手动补充）",
            "section": "参与",
            "show_if": {"enable_participation": True},
            "help": (
                "补充你关心的关键词，每行或逗号分隔。\n"
                "与自动学习的关键词合并，共同决定是否参与群聊。\n"
                "留空则只使用自动学习的关键词。"
            ),
        },
        "max_keywords": {
            "type": "slider", "default": 20, "label": "关键词上限",
            "min": 5, "max": 100, "step": 5, "section": "参与",
            "show_if": {"enable_participation": True},
            "help": "自动学习的关键词数量上限。超出时按参与热度淘汰低频关键词。",
        },
        "keyword_display": {
            "type": "text",
            "default": "",
            "label": "关键词（按参与热度）",
            "section": "参与",
            "show_if": {"enable_participation": True},
            "help": (
                "自动学习的关键词，按你手动发送消息命中次数降序排列。\\n"
                "手动次数越高表示你越常聊这个关键词的话题。\\n"
                "留空 = 尚未学习到关键词。",
            ),
        },
        # —— 当前画像（自动生成，只读展示）——
        "profile_display": {
            "type": "text",
            "default": "",
            "label": "当前画像（自动累积）",
            "section": "身份模拟",
            "help": (
                "每次学习后自动更新，涵盖话题、关键词、语气、口癖、平均字数、\n"
                "标点习惯、emoji 频率、风格描述等全部维度。\n"
                "仅供参考，不可编辑。如字段为空，发送消息触发学习后自动填充。"
            ),
        },
        "profile_prompt_template": {
            "type": "text",
            "default": (
                "请根据以下聊天记录，分析我的说话风格和兴趣偏好。\n\n"
                "上下文（群聊最近的几条消息）：\n{context}\n\n"
                "我的发言：\n{my_messages}\n\n"
                "输出格式（JSON）：\n"
                '{{\n'
                '  "voice": {{\n'
                '    "tone": "语气特征（随意/正经/幽默/暴躁等）",\n'
                '    "avg_words": 平均每句话字数（数字）,\n'
                '    "habits": ["口癖1", "口癖2"],\n'
                '    "punctuation": "标点使用习惯",\n'
                '    "emoji_freq": "emoji 使用频率（很少/偶尔/经常/几乎每条）",\n'
                '    "style_prompt": "一段可读的中文文本，完整描述这个人的说话风格，供 LLM 模仿"\n'
                '  }},\n'
                '  "topics": ["话题1", "话题2"],\n'
                '  "keywords": ["关键词1", "关键词2"],\n'
                '  "summary": "一句话总结当前兴趣"\n'
                "}}"
            ),
            "label": "画像总结模板",
            "section": "身份模拟",
            "help": "占位符：{context} = 上下文，{my_messages} = 我自己的发言。输出含 voice 字段时自动提取风格描述。",
        },
    },
}

# 活跃群组跟踪（用于定时兜底检查）
_active_groups: set[int] = set()
# 发言冷却：chat_id -> 上次成功参与时间戳
_last_participate_time: dict[int, float] = {}
# 自动回复中标记集：chat_id 在集合中时，on_own_messages 跳过热词追踪
_auto_sending_chats: set[int] = set()


def _format_profile_display(profile: dict) -> str:
    """将画像 dict 格式化成可读的多行文本，供配置页显示（不含关键词，关键词在独立字段中）。"""
    parts = []

    topics = profile.get("topics", [])
    if topics:
        parts.append(f"【话题】{'、'.join(topics[:20])}")

    voice = profile.get("voice", {})
    if isinstance(voice, dict):
        tone = (voice.get("tone") or "").strip()
        if tone:
            parts.append(f"【语气】{tone}")
        habits = voice.get("habits", [])
        if habits:
            parts.append(f"【口癖】{'、'.join(habits[:15])}")
        avg_words = (voice.get("avg_words") or "").strip()
        if avg_words:
            parts.append(f"【平均字数】{avg_words}")
        punct = (voice.get("punctuation") or "").strip()
        if punct:
            parts.append(f"【标点习惯】{punct}")
        emoji = (voice.get("emoji_freq") or "").strip()
        if emoji:
            parts.append(f"【emoji】{emoji}")
        style = (voice.get("style_prompt") or "").strip()
        if style:
            parts.append(f"【风格描述】{style}")

    summary = (profile.get("summary") or "").strip()
    if summary:
        parts.append(f"【兴趣总结】{summary}")

    if not parts:
        return "（尚未学习到任何画像，发送消息后自动生成）"
    return "\n\n".join(parts)


def _build_keyword_display(kv) -> str:
    """跨所有活跃群构建带热度的关键词展示。"""
    entries = []
    for gid in sorted(_active_groups):
        profile = get_profile(gid, kv)
        if profile and profile.get("keywords"):
            entries.append(format_keywords_display(profile, gid))
    return "\n\n".join(entries) if entries else "（暂无自动学习的关键词）"


def _group_allowed(chat_id: int, cfg) -> bool:
    """检查 chat_id 是否在目标群组中（白名单模式）。"""
    if cfg.target_groups and chat_id not in cfg.target_groups:
        return False
    return True


def _update_config(ctx, **updates):
    """写入插件配置到持久存储。
    ctx.config['x'] = y 不会持久化（ctx.config 是只读 property），
    必须通过 registry.set_config 合并写入。"""
    reg = ctx._registry
    current = reg.get_config(ctx.plugin_id)
    current.update(updates)
    reg.set_config(ctx.plugin_id, current)


async def setup(ctx):
    kv = ctx.kv

    # ── 处理器 1：自己发的消息 → 学习（仅限 target_groups 中的群）──
    @ctx.on_message(ctx.filters.outgoing, group=-11)
    async def on_own_messages(client, message):
        try:
            cfg = parse_config(ctx.config)
            if not cfg.api_key or not cfg.target_groups:
                return
            if not message.text:
                return
            text = message.text.strip()
            if not text or text.startswith("/") or text.startswith("."):
                return

            chat_id = message.chat.id
            if chat_id > 0:
                return  # 私聊不学习
            if not _group_allowed(chat_id, cfg):
                return

            _active_groups.add(chat_id)
            ctx.log.info(
                "[学习] 收到手动消息: 群 %s | %s…",
                chat_id, text[:60],
            )

            fu = message.from_user
            me_name = getattr(fu, "first_name", "") if fu else ""
            push_all_message(chat_id, text, getattr(fu, "id", 0), me_name)

            # 社交：回复了某人则记录
            if message.reply_to_message:
                rfu = message.reply_to_message.from_user
                if rfu and not rfu.is_self and not rfu.is_bot:
                    record(chat_id, rfu.id, rfu.first_name or "", kv)

            # 学习：计数达标则 LLM 总结
            push_own_message(chat_id, text, kv)

            # 手动消息热词追踪（自动回复消息跳过）
            if chat_id not in _auto_sending_chats:
                # 用被回复的消息（话题来源）做热词匹配，与自动参与逻辑一致
                trigger_text = ""
                if message.reply_to_message and message.reply_to_message.text:
                    rfu = message.reply_to_message.from_user
                    # 排除自己回复自己 — 只有别人发的才算"我参与的话题"
                    if rfu and not rfu.is_self:
                        trigger_text = message.reply_to_message.text.strip()

                if trigger_text:
                    hresult = update_manual_keyword_heat(chat_id, kv, trigger_text)
                    _update_config(ctx, keyword_display=_build_keyword_display(kv))
                    reason = hresult.get("reason")
                    if reason:
                        ctx.log.info(
                            "[学习] 群 %s 手动热词跳过: %s",
                            chat_id, reason,
                        )
                    else:
                        matched = hresult.get("matched", [])
                        new = hresult.get("new", [])
                        msg = f"[学习] 群 {chat_id} 手动热词:"
                        if matched:
                            msg += f" 命中={matched}"
                        if new:
                            msg += f" 新增={new}"
                        ctx.log.info("%s | 话题=%s…", msg, trigger_text[:40])
                else:
                    ctx.log.debug("[学习] 群 %s 无外部话题来源，跳过热词更新", chat_id)
            else:
                ctx.log.debug("[学习] 群 %s 自动回复消息，跳过热词", chat_id)

            cnt = get_message_count(kv, chat_id)
            ctx.log.info(
                "[学习] 群 %s 手动消息计数: %d/%d (当前/阈值)",
                chat_id, cnt, cfg.summarize_gap,
            )
            if cnt >= cfg.summarize_gap:
                own_msgs = get_recent_own_messages(chat_id, cfg.summarize_gap)
                if own_msgs:
                    profile = await summarize(chat_id, kv, cfg, own_msgs)
                    if profile:
                        ctx.log.info(
                            "[学习] 群 %s 画像已更新: topics=%s",
                            chat_id, profile.get("topics", []),
                        )
                        _update_config(ctx, profile_display=_format_profile_display(profile), keyword_display=_build_keyword_display(kv))
                        reset_counter(chat_id, kv)
                        ctx.log.info(
                            "[学习] 群 %s 画像已更新，风格描述已写入 profile.voice.style_prompt",
                            chat_id,
                        )
        except Exception:
            ctx.log.error("[学习] on_own_messages 异常:\n%s", traceback.format_exc())

    # ── 处理器 2：所有人消息 → 全量缓冲 ──
    @ctx.on_message(~ctx.filters.outgoing, group=11)
    async def on_all_messages(client, message):
        cfg = parse_config(ctx.config)
        if not cfg.api_key:
            return
        if not message.text or not cfg.target_groups:
            return
        fu = message.from_user
        if not fu or fu.is_bot:
            return

        chat_id = message.chat.id
        if not _group_allowed(chat_id, cfg):
            return

        text = message.text.strip()
        if not text or text.startswith("/") or text.startswith("."):
            return

        push_all_message(chat_id, text, fu.id, fu.first_name or "")
        _active_groups.add(chat_id)

    # ── 处理器 3：判定是否参与 ──
    @ctx.on_message(ctx.filters.group & ctx.filters.text & ~ctx.filters.outgoing, group=12)
    async def on_participate(client, message):
        cfg = parse_config(ctx.config)
        if not cfg.api_key or not cfg.enable_participation:
            return
        if not cfg.target_groups:
            return
        fu = message.from_user
        if not fu or fu.is_self or fu.is_bot:
            return
        if not message.text:
            return
        text = message.text.strip()
        if not text or text.startswith("/") or text.startswith("."):
            return

        chat_id = message.chat.id
        if not _group_allowed(chat_id, cfg):
            return

        # 发言冷却检查
        now = time.time()
        last_ts = _last_participate_time.get(chat_id, 0)
        if now - last_ts < cfg.min_participation_gap:
            return

        ok, matched_kw = should_participate(chat_id, text, cfg, kv)
        if not ok:
            return

        ctx.log.info(
            "[学习] 群 %s 触发参与 (关键词: %s): %s…",
            chat_id, matched_kw, text[:30],
        )
        context_lines = get_context_lines(chat_id, cfg.participation_context_lines)
        _auto_sending_chats.add(chat_id)
        try:
            reply = await participate(client, chat_id, text, cfg, kv, context_lines=context_lines)
        finally:
            _auto_sending_chats.discard(chat_id)
        if reply:
            ctx.log.info("[学习] 群 %s 已回复: %s", chat_id, reply[:50])
            _last_participate_time[chat_id] = time.time()
            _update_config(ctx, keyword_display=_build_keyword_display(kv))

    # ── 定时兜底：检查未总结的群 ──
    async def summary_tick():
        cfg = parse_config(ctx.config)
        if not cfg.api_key:
            return
        for chat_id in list(_active_groups):
            cnt = get_message_count(kv, chat_id)
            if cnt >= cfg.summarize_gap:
                own_msgs = get_recent_own_messages(chat_id, cfg.summarize_gap)
                if own_msgs:
                    profile = await summarize(chat_id, kv, cfg, own_msgs)
                    if profile:
                        _update_config(ctx, profile_display=_format_profile_display(profile), keyword_display=_build_keyword_display(kv))
                        reset_counter(chat_id, kv)

    ctx.schedule(summary_tick, "interval", minutes=5, id="AI学习总结")


async def teardown(ctx):
    clear()
    _active_groups.clear()
    _last_participate_time.clear()
    _auto_sending_chats.clear()
