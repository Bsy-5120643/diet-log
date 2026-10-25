from __future__ import annotations

import enum


class MealType(str, enum.Enum):
    """餐次。用 varchar + CHECK 而非 PG ENUM，理由见 docs/plan-phase1.md。"""

    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    LATE_NIGHT = "late_night"  # 夜宵


MEAL_TYPES: tuple[str, ...] = tuple(m.value for m in MealType)

#: 前端展示用的中文名
MEAL_LABELS: dict[str, str] = {
    MealType.BREAKFAST.value: "早餐",
    MealType.LUNCH.value: "午餐",
    MealType.DINNER.value: "晚餐",
    MealType.SNACK.value: "加餐",
    MealType.LATE_NIGHT.value: "夜宵",
}

#: 餐次展示顺序
MEAL_ORDER: tuple[str, ...] = (
    MealType.BREAKFAST.value,
    MealType.LUNCH.value,
    MealType.DINNER.value,
    MealType.SNACK.value,
    MealType.LATE_NIGHT.value,
)


class FoodSource(str, enum.Enum):
    """食物数据来源。"""

    SEED = "seed"  # 内置种子数据
    USDA = "usda"  # 外部数据导入
    USER = "user"  # 用户自建


FOOD_SOURCES: tuple[str, ...] = tuple(s.value for s in FoodSource)


class GoalSource(str, enum.Enum):
    """目标数值来源。"""

    MANUAL = "manual"  # 手填
    CALCULATED = "calculated"  # 由 BMR/TDEE 估算


GOAL_SOURCES: tuple[str, ...] = tuple(s.value for s in GoalSource)


class Sex(str, enum.Enum):
    """生理性别。Mifflin-St Jeor 公式只有这两档，不做更多扩展。"""

    MALE = "male"
    FEMALE = "female"


SEXES: tuple[str, ...] = tuple(s.value for s in Sex)


class ActivityLevel(str, enum.Enum):
    """活动水平，对应 Mifflin-St Jeor 的 TDEE 系数。"""

    SEDENTARY = "sedentary"  # 久坐，几乎不运动
    LIGHT = "light"  # 轻度，每周 1~3 次
    MODERATE = "moderate"  # 中等，每周 3~5 次
    ACTIVE = "active"  # 高强度，每周 6~7 次
    VERY_ACTIVE = "very_active"  # 极高，体力工作或一天两练


ACTIVITY_LEVELS: tuple[str, ...] = tuple(a.value for a in ActivityLevel)


class GoalType(str, enum.Enum):
    """目标类型。"""

    CUT = "cut"  # 减脂
    MAINTAIN = "maintain"  # 维持
    GAIN = "gain"  # 增肌


GOAL_TYPES: tuple[str, ...] = tuple(g.value for g in GoalType)
