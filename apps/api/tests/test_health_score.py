"""健康指数纯函数测试。

这些测试是算法的**规格说明** —— 以后调阈值如果改坏了，这里会立刻报警。
"""

from __future__ import annotations

import pytest

from app.services.health_score import (
    MAX_HABIT,
    MAX_HEAT,
    MAX_MACRO,
    HealthScoreBreakdown,
    MacroAmounts,
    ScoreInput,
    compute_health_score,
    heat_score,
    macro_score,
    meal_habit_score,
    score_level,
    streak_score,
)


def _input(**kwargs) -> ScoreInput:
    defaults = dict(
        consumed_kcal=2000.0,
        consumed=MacroAmounts(protein_g=140.0, carb_g=240.0, fat_g=55.0),
        target_kcal=2000.0,
        target=MacroAmounts(protein_g=140.0, carb_g=240.0, fat_g=55.0),
        bmr_kcal=1500.0,
        meals_logged=3,
        streak_days=14,
    )
    defaults.update(kwargs)
    return ScoreInput(**defaults)


# ---------------------------------------------------------------------------
# 满分与基本构成
# ---------------------------------------------------------------------------


def test_perfect_day_scores_100():
    result = compute_health_score(_input())
    assert result.heat == MAX_HEAT
    assert result.macro == MAX_MACRO
    assert result.habit == MAX_HABIT
    assert result.total == 100


def test_max_dimensions_sum_to_100():
    assert MAX_HEAT + MAX_MACRO + MAX_HABIT == 100


# ---------------------------------------------------------------------------
# 热量分（含防节食）
# ---------------------------------------------------------------------------


def test_heat_full_when_within_10_percent():
    assert heat_score(_input(consumed_kcal=2100.0, target_kcal=2000.0)) == MAX_HEAT


def test_heat_zero_when_deviation_over_50_percent():
    assert heat_score(_input(consumed_kcal=3200.0, target_kcal=2000.0)) == 0.0


def test_heat_is_linear_between_bounds():
    """偏差 30%（中点）应拿一半分。"""
    score = heat_score(_input(consumed_kcal=2600.0, target_kcal=2000.0))
    assert score == pytest.approx(MAX_HEAT / 2, abs=0.1)


def test_heat_zero_when_below_bmr_even_if_close_to_target():
    """防节食：目标设得很低也不能靠节食拿分。"""
    data = _input(consumed_kcal=1200.0, target_kcal=1250.0, bmr_kcal=1500.0)
    assert data.consumed_kcal < data.bmr_kcal
    assert heat_score(data) == 0.0


def test_heat_not_penalized_when_at_bmr():
    """刚好等于 BMR 不算节食。"""
    data = _input(consumed_kcal=1500.0, target_kcal=1500.0, bmr_kcal=1500.0)
    assert heat_score(data) == MAX_HEAT


def test_heat_zero_without_goal():
    assert heat_score(_input(target_kcal=None, bmr_kcal=None)) == 0.0


def test_heat_symmetric_for_over_and_under_eating():
    over = heat_score(_input(consumed_kcal=2400.0, target_kcal=2000.0))
    under = heat_score(_input(consumed_kcal=1600.0, target_kcal=2000.0))
    assert over == under


# ---------------------------------------------------------------------------
# 宏量分
# ---------------------------------------------------------------------------


def test_macro_full_when_all_match():
    assert macro_score(_input()) == MAX_MACRO


def test_macro_partial_when_one_macro_off():
    """碳水偏差 30%（该项拿一半），另两项满分 → 30 - 5 = 25。"""
    data = _input(
        consumed=MacroAmounts(protein_g=140.0, carb_g=312.0, fat_g=55.0),
    )
    score = macro_score(data)
    assert score == pytest.approx(25.0, abs=0.5)


def test_macro_zero_without_goal():
    assert macro_score(_input(target=None)) == 0.0


def test_macro_zero_target_item_scores_zero():
    """目标为 0 的项无法评估，记 0 而不是除零崩溃。"""
    data = _input(target=MacroAmounts(protein_g=140.0, carb_g=0.0, fat_g=55.0))
    score = macro_score(data)
    assert score == pytest.approx(20.0, abs=0.5)


# ---------------------------------------------------------------------------
# 记录习惯分
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "meals, expected",
    [(0, 0.0), (1, 5.0), (2, 10.0), (3, 15.0), (5, 15.0)],
)
def test_meal_habit_score(meals, expected):
    assert meal_habit_score(meals) == expected


@pytest.mark.parametrize(
    "streak, expected",
    [(0, 0.0), (1, 15 / 14), (7, 7.5), (14, 15.0), (30, 15.0)],
)
def test_streak_score(streak, expected):
    assert streak_score(streak) == pytest.approx(expected, abs=0.05)


def test_streak_capped_at_14_days():
    assert streak_score(100) == streak_score(14)


# ---------------------------------------------------------------------------
# 无目标用户（重要边界）
# ---------------------------------------------------------------------------


def test_no_goal_user_maxes_at_30():
    """没设目标 → 只有记录习惯能得分，最高 30。"""
    data = _input(target_kcal=None, target=None, bmr_kcal=None)
    result = compute_health_score(data)
    assert result.heat == 0.0
    assert result.macro == 0.0
    assert result.total == 30


def test_no_goal_flag_is_exposed():
    assert _input().has_goal is True
    assert _input(target_kcal=None).has_goal is False
    assert _input(target_kcal=0).has_goal is False


# ---------------------------------------------------------------------------
# 总分边界
# ---------------------------------------------------------------------------


def test_total_never_exceeds_100():
    result = compute_health_score(_input())
    assert result.total <= 100


def test_total_never_below_zero():
    data = _input(consumed_kcal=0.0, meals_logged=0, streak_days=0)
    assert compute_health_score(data).total >= 0


def test_nothing_logged_scores_low():
    data = _input(consumed_kcal=0.0, meals_logged=0, streak_days=0)
    result = compute_health_score(data)
    # 只可能拿到少量分（热量偏差大、无餐次、无连续）
    assert result.total < 40


def test_breakdown_total_property_is_int():
    result = compute_health_score(_input())
    assert isinstance(result.total, int)


# ---------------------------------------------------------------------------
# 档位
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "score, level",
    [(100, "excellent"), (80, "excellent"), (65, "good"), (50, "fair"), (10, "poor")],
)
def test_score_level(score, level):
    assert score_level(score) == level
