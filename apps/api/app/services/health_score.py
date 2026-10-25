"""健康指数计算核心 —— **纯函数，零 IO**。

所有评分规则都在这里，不碰数据库、不读配置，因此可以完整单测。
服务层（health_score_service）只负责取数后调用本模块。

## 评分规则（满分 100）

| 维度 | 满分 | 规则 |
|---|---|---|
| 热量达标 | 40 | 偏差 ≤10% 满分，≥50% 归零；**摄入低于 BMR 直接 0 分（防节食）** |
| 宏量营养素 | 30 | 蛋白质 / 碳水 / 脂肪各 10 分，同样按偏差给分 |
| 记录习惯 | 30 | 三餐及以上 15 分；连续打卡加成 15 分（满 14 天拿满） |

## 关键边界

**没设目标的用户**：热量与宏量都取不到目标值，两项记 0，
只算记录习惯，所以最高只有 30 分，并返回 `has_goal=False`。
这既避免了用 NaN 污染榜单，也形成「先设目标再冲榜」的自然引导。
"""

from __future__ import annotations

from dataclasses import dataclass


MAX_HEAT = 40.0
MAX_MACRO = 30.0
MAX_HABIT = 30.0
MAX_TOTAL = MAX_HEAT + MAX_MACRO + MAX_HABIT   # = 100

#: 偏差在 10% 以内给满分
DEV_FULL = 0.10
#: 偏差超过 50% 归零
DEV_ZERO = 0.50

#: 连续打卡满多少天拿满加成
STREAK_FULL_DAYS = 14

#: 宏量三项各自的满分
MACRO_ITEM_SCORE = MAX_MACRO / 3.0


@dataclass(frozen=True, slots=True)
class MacroAmounts:
    protein_g: float = 0.0
    carb_g: float = 0.0
    fat_g: float = 0.0


@dataclass(frozen=True, slots=True)
class ScoreInput:
    """计算一天得分所需的全部输入。"""

    consumed_kcal: float = 0.0
    consumed: MacroAmounts = MacroAmounts()
    #: 以下三项来自用户目标，未设目标时全为 None
    target_kcal: float | None = None
    target: MacroAmounts | None = None
    bmr_kcal: float | None = None
    #: 当天记录了多少个不同餐次
    meals_logged: int = 0
    #: 截至当天的连续打卡天数
    streak_days: int = 0

    @property
    def has_goal(self) -> bool:
        return self.target_kcal is not None and self.target_kcal > 0


@dataclass(frozen=True, slots=True)
class HealthScoreBreakdown:
    heat: float
    macro: float
    habit: float

    @property
    def total(self) -> int:
        """总分，取整并夹在 0~100。"""
        raw = self.heat + self.macro + self.habit
        return int(max(0.0, min(float(MAX_TOTAL), round(raw))))


def _deviation(consumed: float | None, target: float | None) -> float | None:
    """相对偏差。目标缺失或非正时返回 None（表示无法评估）。"""
    if consumed is None or target is None or target <= 0:
        return None
    return abs(consumed - target) / target


def _score_by_deviation(deviation: float | None, max_score: float) -> float:
    """按偏差线性给分：≤10% 满分，≥50% 归零，中间线性。"""
    if deviation is None:
        return 0.0
    if deviation <= DEV_FULL:
        return max_score
    if deviation >= DEV_ZERO:
        return 0.0
    return max_score * (DEV_ZERO - deviation) / (DEV_ZERO - DEV_FULL)


def heat_score(data: ScoreInput) -> float:
    """热量达标分（满分 40）。

    防节食：摄入低于基础代谢直接 0 分 —— 吃太少不是「达标」，是风险行为。
    """
    if not data.has_goal:
        return 0.0
    if data.bmr_kcal is not None and data.consumed_kcal < data.bmr_kcal:
        return 0.0
    return round(_score_by_deviation(_deviation(data.consumed_kcal, data.target_kcal), MAX_HEAT), 1)


def macro_score(data: ScoreInput) -> float:
    """宏量营养素分（满分 30，蛋白/碳水/脂肪各 10）。"""
    if data.target is None:
        return 0.0

    pairs = (
        (data.consumed.protein_g, data.target.protein_g),
        (data.consumed.carb_g, data.target.carb_g),
        (data.consumed.fat_g, data.target.fat_g),
    )
    total = sum(
        _score_by_deviation(_deviation(consumed, target), MACRO_ITEM_SCORE)
        for consumed, target in pairs
    )
    return round(total, 1)


def meal_habit_score(meals_logged: int) -> float:
    """餐次记录分（满分 15）。三餐及以上拿满。"""
    if meals_logged >= 3:
        return 15.0
    if meals_logged == 2:
        return 10.0
    if meals_logged >= 1:
        return 5.0
    return 0.0


def streak_score(streak_days: int) -> float:
    """连续打卡加成（满分 15，满 14 天拿满）。"""
    if streak_days <= 0:
        return 0.0
    return round(15.0 * min(streak_days, STREAK_FULL_DAYS) / STREAK_FULL_DAYS, 1)


def habit_score(data: ScoreInput) -> float:
    """记录习惯分（满分 30 = 餐次 15 + 打卡 15）。"""
    return round(meal_habit_score(data.meals_logged) + streak_score(data.streak_days), 1)


def compute_health_score(data: ScoreInput) -> HealthScoreBreakdown:
    """计算一天的健康指数。"""
    return HealthScoreBreakdown(
        heat=heat_score(data),
        macro=macro_score(data),
        habit=habit_score(data),
    )


def score_level(score: int) -> str:
    """分数档位，供前端展示文案与配色。"""
    if score >= 80:
        return "excellent"
    if score >= 60:
        return "good"
    if score >= 40:
        return "fair"
    return "poor"
