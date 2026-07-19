# -*- coding: utf-8 -*-
# 策略引擎：连错反击（简化版）

def analyze_trend(matrix_str: str, dragon_start: int = 5, dragon_kill: int = 8,
                  enable_anti_alt: bool = False, enable_anti_double: bool = False):
    """
    简易策略：只判断下一把押大还是押小。
    永远顺势（押上一局的结果）。
    """
    if not matrix_str or len(matrix_str) < 2:
        return "大", "⚖️ 等待图谱", 1, "⚪"

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

    return last_res, "📈 顺势", streak, streak_color