# =============================================================================
# 多站点转账 - 排行榜渲染（文本默认，出图可选）
#
# 默认输出 Markdown/纯文本排行榜（无需任何系统二进制，保证可用）。
# 可选增强：若环境装了 imgkit + wkhtmltoimage，可渲染成 PNG（render_image）。
# 出图失败/不可用一律回退文本，绝不抛错。
#
# 不 import pyrogram / core / config。
# =============================================================================

import os
import shutil
import uuid

_MEDALS = ["🥇", "🥈", "🥉"]


def _mask_uid(uid: int | str) -> str:
    s = str(uid)
    if not s or s == "0":
        return "—"
    if len(s) <= 4:
        return s
    if len(s) > 6:
        return f"{s[:3]}***{s[-2:]}"
    return f"{s[:2]}**{s[-1:]}"


def _fmt_amount(v: float) -> str:
    # 整数不带小数，否则保留 1 位
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    return f"{v:,.1f}"


def render_text(entries: list[dict], site_name: str, bonus_name: str,
                direction: str, owner_name: str = "") -> str:
    """渲染文本排行榜。direction: 'in'=打赏总榜 / 'out'=赏赐总榜。"""
    title_word = "打赏" if direction == "in" else "赏赐"
    head = f"🏆 {site_name} {title_word}总榜 TOP{len(entries)}"
    if owner_name:
        head = f"🏆 {owner_name} · {site_name} {title_word}总榜 TOP{len(entries)}"
    if not entries:
        return f"{head}\n\n暂无数据。"
    lines = [head, ""]
    for e in entries:
        rank = e["rank"]
        medal = _MEDALS[rank - 1] if rank <= 3 else f"{rank:>2}."
        name = e["user_name"]
        name = (name[:10] + "…") if len(name) > 11 else name
        amt = _fmt_amount(e["total"])
        lines.append(f"{medal} {name}  {amt} {bonus_name}（{e['count']}次）")
    return "\n".join(lines)


def render_user_summary(stat: dict, bonus_name: str, direction: str,
                        user_name: str, amount: float) -> str:
    """单笔转账后的个人累计文案（用于 notification）。"""
    title_word = "打赏" if direction == "in" else "赏赐"
    if direction == "in":
        head = (f"👤 {user_name} 大佬，感谢打赏！\n"
                f"💰 本次收到：{_fmt_amount(abs(amount))} {bonus_name}")
    else:
        head = (f"👤 {user_name}\n"
                f"🎁 这是赏赐你的 {_fmt_amount(abs(amount))} {bonus_name}，拿去花！")
    rank_str = f"第 {stat['rank']} 名" if stat.get("rank", -1) > 0 else "—"
    tail = (f"📊 累计{title_word}：{stat['count']} 次，共 "
            f"{_fmt_amount(stat['total'])} {bonus_name}\n"
            f"🏆 {title_word}总榜：{rank_str}")
    return f"{head}\n{tail}"


def image_available() -> bool:
    """imgkit + wkhtmltoimage 是否可用。"""
    try:
        import imgkit  # noqa: F401
    except Exception:
        return False
    return shutil.which("wkhtmltoimage") is not None


def render_image(entries: list[dict], site_name: str, bonus_name: str,
                 direction: str, owner_name: str, out_dir) -> str | None:
    """渲染 PNG 排行榜，返回文件路径；不可用/失败返回 None（调用方回退文本）。"""
    if not entries or not image_available():
        return None
    try:
        import imgkit
        title_word = "打赏" if direction == "in" else "赏赐"
        rows = ""
        for e in entries:
            rank = e["rank"]
            medal = _MEDALS[rank - 1] if rank <= 3 else f"TOP{rank}"
            rows += (
                f"<tr><td class='r'>{medal}</td>"
                f"<td class='i'>{_mask_uid(e['user_id'])}</td>"
                f"<td class='n'>{_html_escape(e['user_name'])}</td>"
                f"<td class='c'>{e['count']}</td>"
                f"<td class='a'>{_fmt_amount(e['total'])}</td></tr>"
            )
        owner = owner_name or site_name
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
        body{{background:#667eea;font-family:Arial,'Microsoft YaHei',sans-serif;padding:6px;margin:0}}
        .box{{background:#fff;padding:10px;width:500px;border-radius:6px}}
        .t{{text-align:center;color:#333;font-size:20px;font-weight:bold;margin-bottom:4px}}
        .s{{text-align:center;color:#666;font-size:14px;margin-bottom:10px}}
        table{{width:100%;border-collapse:collapse;font-size:14px}}
        thead{{background:#667eea}} th{{padding:7px 4px;color:#fff;font-size:13px}}
        td{{padding:6px 4px;text-align:center;color:#333;border-bottom:1px solid #eee;font-size:13px}}
        .r{{font-weight:bold}} .i{{color:#667eea}} .n{{font-weight:600}}
        .c{{color:#4ecdc4;font-weight:bold}} .a{{color:#ff6b6b;font-weight:bold}}
        </style></head><body><div class="box">
        <div class="t">🌟 {_html_escape(owner)} 的{title_word}数据终端 🌟</div>
        <div class="s">&gt;&gt;&gt; {site_name} TOP{len(entries)} 排行榜 &lt;&lt;&lt;</div>
        <table><thead><tr><th>⚡排名</th><th>🆔ID</th><th>👤用户</th>
        <th>📊次数</th><th>💰{bonus_name}</th></tr></thead><tbody>{rows}</tbody></table>
        </div></body></html>"""

        out_dir = str(out_dir)
        os.makedirs(out_dir, exist_ok=True)
        uid = uuid.uuid4().hex
        html_path = os.path.join(out_dir, f"_lb_{uid}.html")
        img_path = os.path.join(out_dir, f"_lb_{uid}.png")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        options = {"encoding": "UTF-8", "format": "png", "width": 500, "quiet": ""}
        try:
            imgkit.from_file(html_path, img_path, options=options)
        finally:
            if os.path.exists(html_path):
                os.unlink(html_path)
        return img_path if os.path.exists(img_path) else None
    except Exception:
        return None


def _html_escape(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))
