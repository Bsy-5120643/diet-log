"""目标计算测试。

三个规格用例 + 一个边界用例。
期望值用手算的 Mifflin-St Jeor 结果锁定，防止改常量时悄悄跑偏。
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from app.models.enums import ActivityLevel, GoalType, Sex
from app.services.goal_calculator import (
    MAX_CUT_DEFICIT_PCT,
    BodyProfile,
    build_goal_plan,
    calc_bmr,
    calc_tdee,
)


def _profile(
    *,
    sex: Sex,
    age: int,
    height_cm: str,
    weight_kg: str,
    activity_level: ActivityLevel,
) -> BodyProfile:
    return BodyProfile(
        sex=sex,
        age=age,
        height_cm=Decimal(height_cm),
        weight_kg=Decimal(weight_kg),
        activity_level=activity_level,
    )


def _kcal_sum(plan) -> Decimal:
    """三营养素折算回热量，用于校验自洽。"""
    m = plan.macros
    return m.protein_g * 4 + m.fat_g * 9 + m.carb_g * 4


# ---------------------------------------------------------------------------
# 用例 1：70kg / 175cm / 30 岁 男性，中等活动量，减脂
# ---------------------------------------------------------------------------


def test_case1_male_moderate_cut():
    profile = _profile(
        sex=Sex.MALE,
        age=30,
        height_cm="175",
        weight_kg="70",
        activity_level=ActivityLevel.MODERATE,
    )
    plan = build_goal_plan(profile, GoalType.CUT)

    # BMR = 10*70 + 6.25*175 - 5*30 + 5 = 1648.75 → 1648.8
    assert plan.bmr_kcal == Decimal("1648.8")
    # TDEE = 1648.8 * 1.55 = 2555.6
    assert plan.tdee_kcal == Decimal("2555.6")
    # 目标 = TDEE * 0.8 = 2044.5 → 2044（未触及 BMR 下限 1648.8）
    assert plan.target_kcal == Decimal("2044")
    assert plan.deficit_pct == Decimal("0.200")

    assert plan.macros.protein_g == Decimal("140.0")  # 2.0 g/kg
    assert plan.macros.fat_g == Decimal("56.8")  # 25% 热量
    assert plan.macros.carb_g == Decimal("243.2")  # 剩余热量

    # 三项折算回热量应约等于目标热量（误差来自四舍五入，容忍 2 kcal）
    assert abs(_kcal_sum(plan) - plan.target_kcal) <= Decimal("2")
    assert plan.safety_flags == ()


# ---------------------------------------------------------------------------
# 用例 2：60kg / 160cm / 25 岁 女性，轻度活动，维持
# ---------------------------------------------------------------------------


def test_case2_female_light_maintain():
    profile = _profile(
        sex=Sex.FEMALE,
        age=25,
        height_cm="160",
        weight_kg="60",
        activity_level=ActivityLevel.LIGHT,
    )
    plan = build_goal_plan(profile, GoalType.MAINTAIN)

    # BMR = 10*60 + 6.25*160 - 5*25 - 161 = 1314.0
    assert plan.bmr_kcal == Decimal("1314.0")
    # TDEE = 1314.0 * 1.375 = 1806.75 → 1806.8
    assert plan.tdee_kcal == Decimal("1806.8")
    # 维持：目标 = TDEE
    assert plan.target_kcal == Decimal("1807")
    assert plan.deficit_pct == Decimal("0")

    assert plan.macros.protein_g == Decimal("96.0")  # 1.6 g/kg
    assert plan.macros.fat_g == Decimal("50.2")
    assert plan.macros.carb_g == Decimal("242.8")
    assert plan.safety_flags == ()


# ---------------------------------------------------------------------------
# 用例 3：85kg / 180cm / 40 岁 男性，高强度活动，增肌
# ---------------------------------------------------------------------------


def test_case3_male_active_gain():
    profile = _profile(
        sex=Sex.MALE,
        age=40,
        height_cm="180",
        weight_kg="85",
        activity_level=ActivityLevel.ACTIVE,
    )
    plan = build_goal_plan(profile, GoalType.GAIN)

    # BMR = 10*85 + 6.25*180 - 5*40 + 5 = 1780.0
    assert plan.bmr_kcal == Decimal("1780.0")
    # TDEE = 1780.0 * 1.725 = 3070.5
    assert plan.tdee_kcal == Decimal("3070.5")
    # 增肌：TDEE * 1.10 = 3377.55 → 3378
    assert plan.target_kcal == Decimal("3378")
    assert plan.deficit_pct == Decimal("0")

    assert plan.macros.protein_g == Decimal("153.0")  # 1.8 g/kg
    assert plan.macros.fat_g == Decimal("93.8")
    assert plan.macros.carb_g == Decimal("480.5")
    assert plan.safety_flags == ()


# ---------------------------------------------------------------------------
# 边界用例：TDEE 本身低于常规推荐最低摄入量
# ---------------------------------------------------------------------------


def test_case4_edge_low_tdee_clamps_at_bmr():
    """50kg / 150cm / 70 岁 女性，久坐，减脂。

    TDEE ≈ 1112 kcal，20% 缺口后 ≈ 889 kcal，已低于 BMR 926.5。
    期望：目标被抬到 BMR（927），实际缺口小于 20%，并给出低摄入提示。
    """
    profile = _profile(
        sex=Sex.FEMALE,
        age=70,
        height_cm="150",
        weight_kg="50",
        activity_level=ActivityLevel.SEDENTARY,
    )
    plan = build_goal_plan(profile, GoalType.CUT)

    assert plan.bmr_kcal == Decimal("926.5")
    assert plan.tdee_kcal == Decimal("1111.8")
    # 缺口后只有 889，低于 BMR，被抬到 BMR（926.5 → 927）
    assert plan.target_kcal == Decimal("927")

    # 实际缺口约 16.6%，严格小于 20% 上限
    assert plan.deficit_pct < MAX_CUT_DEFICIT_PCT
    assert float(plan.deficit_pct) == pytest.approx(0.166, abs=1e-3)

    # 脂肪按 25% 只有 25.8g，低于 0.6g/kg = 30g，触发脂肪下限
    assert plan.macros.fat_g == Decimal("30.0")
    assert plan.macros.protein_g == Decimal("100.0")
    assert plan.macros.carb_g == Decimal("64.3")

    # 低于常规推荐最低摄入，给出提示
    assert "below_recommended_minimum" in plan.safety_flags


# ---------------------------------------------------------------------------
# 其他
# ---------------------------------------------------------------------------


def test_deficit_over_cap_rejected():
    profile = _profile(
        sex=Sex.MALE,
        age=30,
        height_cm="175",
        weight_kg="70",
        activity_level=ActivityLevel.MODERATE,
    )
    with pytest.raises(ValueError, match="不得超过"):
        build_goal_plan(profile, GoalType.CUT, Decimal("0.25"))


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("age", 5, "年龄"),
        ("age", 150, "年龄"),
        ("height_cm", "10", "身高"),
        ("height_cm", "300", "身高"),
        ("weight_kg", "5", "体重"),
        ("weight_kg", "500", "体重"),
    ],
)
def test_implausible_profile_rejected(field, value, expected):
    """越界输入必须被拒绝，而不是算出一个荒谬的热量。"""
    profile = _profile(
        sex=Sex.MALE,
        age=30,
        height_cm="175",
        weight_kg="70",
        activity_level=ActivityLevel.MODERATE,
    )
    broken = dataclasses.replace(profile, **{field: Decimal(value)})
    with pytest.raises(ValueError, match=expected):
        build_goal_plan(broken, GoalType.CUT)


def test_bmr_male_exceeds_female():
    """同样身高体重年龄，男性 BMR 应比女性高 166 kcal（+5 vs −161）。"""
    kwargs = dict(age=30, height_cm=Decimal("175"), weight_kg=Decimal("70"))
    male = calc_bmr(sex=Sex.MALE, **kwargs)
    female = calc_bmr(sex=Sex.FEMALE, **kwargs)
    assert male - female == Decimal("166.0")


def test_tdee_monotonic_in_activity():
    """活动水平越高，TDEE 越大。"""
    bmr = Decimal("1648.8")
    values = [calc_tdee(bmr, level) for level in ActivityLevel]
    assert values == sorted(values)
