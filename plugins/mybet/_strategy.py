# -*- coding: utf-8 -*-
# 策略引擎：追龙/斩龙/破单跳/破双跳/顺势平推

def analyze_trend(matrix_str: str, dragon_start: int = 5, dragon_kill: int = 8,
                  enable_anti_alt: bool = False, enable_anti_double: bool = False):
    """
    根据最新走势矩阵决定下注方向。
    matrix_str: 由近及远的走势，'1'=大, '0'=小，如 "1100101..."
    返回: (target, mode_name, streak, streak_color)
    """
    if not matrix_str or len(matrix_str) < 4:
        return "大", "⚖️ 等待图谱对焦", 1, "⚪"

    last_code = matrix_str[0]
    last_res = "大" if last_code == "1" else "小"

    # 当前连开数
    streak = 1
    for c in matrix_str[1:]:
        if c == last_code:
            streak += 1
        else:
            break
    streak_color = "🔴" if last_res == "大" else "🟦"

    # 最新4局倒序 (时间正序)
    latest_4 = matrix_str[:4][::-1]

    # 战术1: 极境斩龙
    if streak >= dragon_kill:
        target = "小" if last_res == "大" else "大"
        return target, f"🔪 极境斩龙 ({dragon_kill}连死线)", streak, streak_color

    # 战术2: 狂暴追龙
    if streak >= dragon_start:
        return last_res, f"🐉 顺势追龙 ({streak}连中)", streak, streak_color

    # 战术3: 破双跳
    if enable_anti_double:
        if latest_4 == "1100":
            return "大", "🪓 粉碎双跳", streak, streak_color
        elif latest_4 == "0011":
            return "小", "🪓 粉碎双跳", streak, streak_color

    # 战术4: 破单跳
    if enable_anti_alt:
        if latest_4 == "1010":
            return "大", "🧲 重力反转(破单跳)", streak, streak_color
        elif latest_4 == "0101":
            return "小", "🧲 重力反转(破单跳)", streak, streak_color

    # 默认: 顺势平推
    return last_res, "📈 无脑顺势(硬抗震荡)", streak, streak_color
