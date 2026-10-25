"""目标计算：Mifflin-St Jeor 公式 + 三大营养素分配。

设计原则：
- 纯函数，零 IO（不碰数据库、不发请求），全部可单测
- 一律用 Decimal，不用 float —— 同样是为了避免聚合漂移
- 所有魔法数字提取为具名常量，方便后续按人群调参

单位：重量 kg、身高 cm、热量 kcal、营养素 g、钠 mg。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import ActivityLevel, GoalType, Sex

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: Mifflin-St Jeor 的 TDEE 活动系数（学界通用取值）
ACTIVITY_FACTORS: dict[ActivityLevel, Decimal] = {
    ActivityLevel.SEDENTARY: Decimal("1.2"),
    ActivityLevel.LIGHT: Decimal("1.375"),
    ActivityLevel.MODERATE: Decimal("1.55"),
    ActivityLevel.ACTIVE: Decimal("1.725"),
    ActivityLevel.VERY_ACTIVE: Decimal("1.9"),
}

#: 蛋白质目标：每公斤体重克数。减脂期最高，用于保住瘦体重。
PROTEIN_G_PER_KG: dict[GoalType, Decimal] = {
    GoalType.CUT: Decimal("2.0"),
    GoalType.MAINTAIN: Decimal("1.6"),
    GoalType.GAIN: Decimal("1.8"),
}

#: 脂肪占总热量比例
FAT_KCAL_RATIO = Decimal("0.25")

#: 脂肪下限：每公斤体重克数。低于此值可能影响激素与脂溶性维生素吸收。
FAT_G_PER_KG_FLOOR = Decimal("0.6")

#: 减脂缺口上限（占 TDEE 比例）。缺口过大容易掉肌肉、代谢适应。
MAX_CUT_DEFICIT_PCT = Decimal("0.20")

#: 增肌盈余（占 TDEE 比例）。取 10% 偏保守，减少脂肪堆积。
GAIN_SURPLUS_PCT = Decimal("0.10")

#: 常规推荐最低摄入量。仅用于生成提示，**不做硬截断** ——
#  否则遇到 TDEE 本身就低于该值的用户（体型很小的久坐老人），
#  max(缺口后热量, 下限) 会把目标抬到 TDEE 以上，减脂反成增肥。
RECOMMENDED_MIN_KCAL: dict[Sex, Decimal] = {
    Sex.MALE: Decimal("1500"),
    Sex.FEMALE: Decimal("1200"),
}

#: 各营养素的能量系数（kcal/g）
KCAL_PER_G_PROTEIN = Decimal("4")
KCAL_PER_G_FAT = Decimal("9")
KCAL_PER_G_CARB = Decimal("4")

#: 膳食纤维参考摄入：每 1000 kcal 对应克数
FIBER_G_PER_1000_KCAL = Decimal("14")

#: 钠摄入上限（mg/天）。中国居民膳食指南（2022）：每天食盐不超过 5g ≈ 钠 2000mg。
SODIUM_CEILING_MG = Decimal("2000")

# 入参合理区间（与前端校验保持一致，后端做权威校验）
MIN_AGE, MAX_AGE = 14, 100
MIN_HEIGHT_CM, MAX_HEIGHT_CM = Decimal("50"), Decimal("250")
MIN_WEIGHT_KG, MAX_WEIGHT_KG = Decimal("20"), Decimal("400")

_Q0 = Decimal("1")
_Q1 = Decimal("0.1")
_Q3 = Decimal("0.001")


def _q(value: Decimal, exp: Decimal) -> Decimal:
    """四舍五入到指定精度。"""
    return value.quantize(exp, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BodyProfile:
    """身体档案，计算目标的输入。"""

    sex: Sex
    age: int
    height_cm: Decimal
    weight_kg: Decimal
    activity_level: ActivityLevel

    def validate(self) -> None:
        if not (MIN_AGE <= self.age <= MAX_AGE):
            raise ValueError(f"年龄需在 {MIN_AGE}~{MAX_AGE} 岁之间，当前 {self.age}")
        if not (MIN_HEIGHT_CM <= self.height_cm <= MAX_HEIGHT_CM):
            raise ValueError(
                f"身高需在 {MIN_HEIGHT_CM}~{MAX_HEIGHT_CM} cm 之间，当前 {self.height_cm}"
            )
        if not (MIN_WEIGHT_KG <= self.weight_kg <= MAX_WEIGHT_KG):
            raise ValueError(
                f"体重需在 {MIN_WEIGHT_KG}~{MAX_WEIGHT_KG} kg 之间，当前 {self.weight_kg}"
            )


@dataclass(frozen=True, slots=True)
class MacroTargets:
    """三大营养素目标克数。"""

    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal


@dataclass(frozen=True, slots=True)
class GoalPlan:
    """完整目标方案：中间量 + 最终结果。"""

    bmr_kcal: Decimal
    tdee_kcal: Decimal
    target_kcal: Decimal
    deficit_pct: Decimal  # 实际生效的缺口比例，可能为 0
    macros: MacroTargets
    fiber_g: Decimal
    sodium_mg: Decimal
    safety_flags: tuple[str, ...] = ()


#: 目标热量低于常规推荐最低摄入时给出的提示码
FLAG_BELOW_RECOMMENDED_MIN = "below_recommended_minimum"


# ---------------------------------------------------------------------------
# 计算
# ---------------------------------------------------------------------------


def calc_bmr(
    *, sex: Sex, age: int, height_cm: Decimal, weight_kg: Decimal
) -> Decimal:
    """Mifflin-St Jeor 基础代谢率 (kcal/天)。

    男：10×体重 + 6.25×身高 − 5×年龄 + 5
    女：10×体重 + 6.25×身高 − 5×年龄 − 161
    """
    base = (
        Decimal("10") * weight_kg
        + Decimal("6.25") * height_cm
        - Decimal("5") * Decimal(age)
    )
    offset = Decimal("5") if sex is Sex.MALE else Decimal("-161")
    return _q(base + offset, _Q1)


def calc_tdee(bmr_kcal: Decimal, activity_level: ActivityLevel) -> Decimal:
    """每日总消耗 = BMR × 活动系数。"""
    return _q(bmr_kcal * ACTIVITY_FACTORS[activity_level], _Q1)


def calc_target_kcal(
    *,
    sex: Sex,
    bmr_kcal: Decimal,
    tdee_kcal: Decimal,
    goal_type: GoalType,
    deficit_pct: Decimal = MAX_CUT_DEFICIT_PCT,
) -> tuple[Decimal, Decimal]:
    """计算目标热量，返回 (目标热量, 实际生效缺口比例)。

    减脂：TDEE × (1 − 缺口)，且缺口硬性不超过 20%，
          同时结果不得低于 BMR 和绝对下限（防止极端输入）。
    若触发下限保护，返回的实际缺口会小于请求的缺口。
    """
    if deficit_pct < 0:
        raise ValueError("缺口比例不能为负")
    if deficit_pct > MAX_CUT_DEFICIT_PCT:
        raise ValueError(
            f"减脂缺口不得超过 TDEE 的 {MAX_CUT_DEFICIT_PCT:.0%}，当前 {deficit_pct:.1%}"
        )

    if goal_type is GoalType.CUT:
        raw = tdee_kcal * (Decimal("1") - deficit_pct)
        # 唯一硬下限是 BMR：低于基础代谢即为饥饿节食，会掉肌肉、触发代谢适应。
        # 刻意不设「绝对最低 1200/1500」硬截断 —— 那会把 TDEE 本就偏低的用户
        # 的目标热量抬到维持值以上，减脂反成增肥。这种情况交给 safety_flags 提示。
        target = _q(max(raw, bmr_kcal), _Q0)
        # 缺口必须基于「最终落库的取整值」反算，
        # 否则会出现 目标热量=927 但缺口=0.167（按 926.5 算）这种对不上的情况。
        effective = (
            (tdee_kcal - target) / tdee_kcal if tdee_kcal > 0 else Decimal("0")
        )
        return target, _q(effective, _Q3)

    if goal_type is GoalType.GAIN:
        return _q(tdee_kcal * (Decimal("1") + GAIN_SURPLUS_PCT), _Q0), Decimal("0")

    return _q(tdee_kcal, _Q0), Decimal("0")


def calc_macro_targets(
    *, sex: Sex, weight_kg: Decimal, goal_type: GoalType, target_kcal: Decimal
) -> MacroTargets:
    """按目标分配三大营养素。

    顺序：蛋白质 → 脂肪 → 碳水（碳水吃剩余热量）。
    这样构造保证 蛋白×4 + 脂肪×9 + 碳水×4 ≈ 目标热量，不会出现三项加不上的情况。
    """
    protein_g = _q(PROTEIN_G_PER_KG[goal_type] * weight_kg, _Q1)

    fat_by_ratio = _q(target_kcal * FAT_KCAL_RATIO / KCAL_PER_G_FAT, _Q1)
    fat_by_floor = _q(FAT_G_PER_KG_FLOOR * weight_kg, _Q1)
    fat_g = max(fat_by_ratio, fat_by_floor)

    remaining_kcal = (
        target_kcal
        - protein_g * KCAL_PER_G_PROTEIN
        - fat_g * KCAL_PER_G_FAT
    )
    carb_g = max(Decimal("0"), _q(remaining_kcal / KCAL_PER_G_CARB, _Q1))

    return MacroTargets(protein_g=protein_g, fat_g=fat_g, carb_g=carb_g)


def calc_fiber_target(target_kcal: Decimal) -> Decimal:
    """膳食纤维参考摄入量。"""
    return _q(target_kcal / Decimal("1000") * FIBER_G_PER_1000_KCAL, _Q0)


def build_goal_plan(
    profile: BodyProfile,
    goal_type: GoalType,
    deficit_pct: Decimal = MAX_CUT_DEFICIT_PCT,
) -> GoalPlan:
    """一次算完：BMR → TDEE → 目标热量 → 三大营养素 → 纤维/钠参考值。"""
    profile.validate()

    bmr_kcal = calc_bmr(
        sex=profile.sex,
        age=profile.age,
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
    )
    tdee_kcal = calc_tdee(bmr_kcal, profile.activity_level)
    target_kcal, effective_deficit = calc_target_kcal(
        sex=profile.sex,
        bmr_kcal=bmr_kcal,
        tdee_kcal=tdee_kcal,
        goal_type=goal_type,
        deficit_pct=deficit_pct,
    )
    macros = calc_macro_targets(
        sex=profile.sex,
        weight_kg=profile.weight_kg,
        goal_type=goal_type,
        target_kcal=target_kcal,
    )

    flags: list[str] = []
    if target_kcal < RECOMMENDED_MIN_KCAL[profile.sex]:
        flags.append(FLAG_BELOW_RECOMMENDED_MIN)

    return GoalPlan(
        bmr_kcal=bmr_kcal,
        tdee_kcal=tdee_kcal,
        target_kcal=target_kcal,
        deficit_pct=effective_deficit,
        macros=macros,
        fiber_g=calc_fiber_target(target_kcal),
        sodium_mg=SODIUM_CEILING_MG,
        safety_flags=tuple(flags),
    )
