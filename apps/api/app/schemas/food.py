"""食物库出入参模型。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class FoodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None = None

    #: 每 100g 可食部
    energy_kcal: float
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None

    #: 命中来源：name 表示名称匹配，alias 表示别名匹配
    match_on: str = "name"
    #: 命中的别名（match_on == "alias" 时有值）
    matched_alias: str | None = None


class FoodSearchOut(BaseModel):
    """GET /foods 的返回。"""

    keyword: str
    items: list[FoodOut]
    total: int
    page: int
    size: int
    has_more: bool
