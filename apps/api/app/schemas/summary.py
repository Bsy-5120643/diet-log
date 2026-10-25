"""当日 / 区间汇总出参模型。

设计约定：
- targets / remaining / percent 允许为 null
  用户尚未设置目标时，接口正常返回 200，只是这几个字段为 null，
  前端据此展示「先去设置目标」的引导，而不是抛错或显示 NaN。
- consumed 永远有值（没有记录时为全 0），前端可以直接渲染。
"""

from __future__ import annotations

import datetime

from pydantic import BaseModel, ConfigDict


class MacroValues(BaseModel):
    """热量与三大营养素的数值（绝对值，非每 100g）。"""

    energy_kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    fiber_g: float = 0.0
    sodium_mg: float = 0.0


class MacroTargets(BaseModel):
    """目标值。"""

    energy_kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    fiber_g: float | None = None
    sodium_mg: float | None = None


class MealBreakdown(BaseModel):
    """单个餐次的汇总。"""

    energy_kcal: float = 0.0
    entry_count: int = 0


class DailySummaryOut(BaseModel):
    """GET /summary 的返回。

    前端看板直接拿它渲染环形进度与三条进度条。

    incomplete_fields 用来解决「0 还是未知」：
    汇总时 SQL 的 SUM 把 NULL 当 0 计入，consumed 里缺数据的项看起来就是 0。
    但「真实 0」与「数据缺失导致算不出来」必须区分 —— 后者 UI 要显示「-」，
    不能显示 0，否则用户会以为自己今天蛋白质摄入确实是 0。
    """

    date: str
    consumed: MacroValues
    targets: MacroTargets | None = None
    remaining: MacroValues | None = None
    percent: MacroValues | None = None
    by_meal: dict[str, MealBreakdown] = {}
    entry_count: int = 0
    #: 当天有记录但因原始数据缺失而无法计算的字段名
    incomplete_fields: list[str] = []


class DailyPointOut(BaseModel):
    """区间汇总里单天的数据点。"""

    date: str
    energy_kcal: float = 0.0
    protein_g: float = 0.0
    fat_g: float = 0.0
    carb_g: float = 0.0
    target_kcal: float | None = None
    entry_count: int = 0


class SummaryRangeOut(BaseModel):
    """GET /summary/range 的返回。

    days 按日期升序，且**补齐区间内所有日期**（没有记录的天补 0），
    这样折线图不会出现断点或错位的 x 轴。
    """

    date_from: str
    date_to: str
    days: list[DailyPointOut]
