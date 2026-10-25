"""营养计算：全项目唯一实现处。

任何地方都不许自己写 `kcal * g / 100`，一律走这里，
否则 CHECK 约束 ck_food_entries_computed_consistent 会直接拒绝写入。

重要约定：**数据缺失不能阻止用户记录。**
食物库里存在未检测营养素的条目（protein_g / fat_g / carb_g 为 NULL），
此时换算结果同样是 NULL，而不是 0 —— 0 会被误读成「确实是 0」。
汇总时按 0 计入总量，但 UI 应显示为「-」。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.models.food import Food

ONE_HUNDRED = Decimal("100")
_CENTS = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class NutrientPer100g:
    """每 100g 营养值。

    energy_kcal 必填：导入时已跳过无能量的食物，且总热量不允许算不出来。
    其余可为 None，表示「未检测」。
    """

    energy_kcal: Decimal
    protein_g: Optional[Decimal] = None
    fat_g: Optional[Decimal] = None
    carb_g: Optional[Decimal] = None
    fiber_g: Optional[Decimal] = None
    sodium_mg: Optional[Decimal] = None


@dataclass(frozen=True, slots=True)
class NutrientAmount:
    """按实际克数换算后的绝对值。可空性与输入保持一致。"""

    energy_kcal: Decimal
    protein_g: Optional[Decimal] = None
    fat_g: Optional[Decimal] = None
    carb_g: Optional[Decimal] = None
    fiber_g: Optional[Decimal] = None
    sodium_mg: Optional[Decimal] = None


def _round2(value: Decimal) -> Decimal:
    return value.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _scale(value: Optional[Decimal], factor: Decimal) -> Optional[Decimal]:
    """按系数换算；输入为 None（未检测）时输出仍是 None，绝不填 0。"""
    if value is None:
        return None
    return _round2(value * factor)


def scale(per_100g: NutrientPer100g, quantity_g: Decimal) -> NutrientAmount:
    """把每 100g 营养值按实际克数换算成绝对值。"""
    factor = quantity_g / ONE_HUNDRED
    return NutrientAmount(
        energy_kcal=_round2(per_100g.energy_kcal * factor),
        protein_g=_scale(per_100g.protein_g, factor),
        fat_g=_scale(per_100g.fat_g, factor),
        carb_g=_scale(per_100g.carb_g, factor),
        fiber_g=_scale(per_100g.fiber_g, factor),
        sodium_mg=_scale(per_100g.sodium_mg, factor),
    )


def snapshot_of(food: Food) -> NutrientPer100g:
    """从 Food 生成营养快照。缺失字段保持 None。"""
    return NutrientPer100g(
        energy_kcal=food.energy_kcal,
        protein_g=food.protein_g,
        fat_g=food.fat_g,
        carb_g=food.carb_g,
        fiber_g=food.fiber_g,
        sodium_mg=food.sodium_mg,
    )


def resolve_quantity(
    quantity_g: Optional[Decimal] = None,
    serving_count: Optional[Decimal] = None,
    serving_grams_per_unit: Optional[Decimal] = None,
) -> Decimal:
    """二选一录入：直接给克数，或给「几份 × 每份克数」。

    两者都给时以 quantity_g 为准，但调用方应保证两者一致。
    """
    if quantity_g is not None:
        return _round2(quantity_g)
    if serving_count is None or serving_grams_per_unit is None:
        raise ValueError("必须提供 quantity_g，或同时提供 serving_count 与 serving_grams_per_unit")
    return _round2(serving_count * serving_grams_per_unit)
