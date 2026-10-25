"""AI 识别接口的出入参模型。

对应 SPEC §6.1 / §6.2 / §6.4。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class RecognizedIngredientOut(BaseModel):
    """识别结果里的一个食材。"""

    #: 匹配到 foods 表时非空；未匹配为 null（前端显示 <未匹配>）
    food_id: uuid.UUID | None = None
    food_name: str
    quantity_g: float
    #: 本次摄入，未匹配或食物缺数据时为 null
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None
    confidence: float | None = None
    #: ai = AI 给的并按名称匹配；user_recipe = 来自私有库配比；unmatched = 库里没有
    matched_by: str


class RecognitionCacheOut(BaseModel):
    hit: bool
    recipe_id: uuid.UUID | None = None
    #: ai / user_recipe
    source: str


class QuotaOut(BaseModel):
    used: int
    limit: int
    remaining: int
    resets_at: str
    locked_until: str | None = None


class RecognitionOut(BaseModel):
    """POST /ai/recognize 的返回。

    无论识别质量如何都返回 200，问题放进 warnings（SPEC §7）。
    """

    request_id: uuid.UUID
    dish_name: str
    normalized_name: str
    confidence: float
    total_energy_kcal: float
    ingredients: list[RecognizedIngredientOut]
    warnings: list[str] = []
    cache: RecognitionCacheOut
    quota: QuotaOut


class ConfirmIngredientIn(BaseModel):
    food_id: uuid.UUID
    quantity_g: Decimal = Field(gt=Decimal("0"), le=Decimal("5000"))


class ConfirmIn(BaseModel):
    """POST /ai/confirm 的入参。

    只接收 food_id + 克数，**不接收算好的热量** —— 一律服务端重算。
    """

    request_id: uuid.UUID
    dish_name: str = Field(min_length=1, max_length=200)
    entry_date: str | None = None
    meal_type: str
    ingredients: list[ConfirmIngredientIn] = Field(min_length=1)
    #: 是否保存/更新为自己的菜品
    save_as_recipe: bool = True


class ConfirmOut(BaseModel):
    entry_group_id: uuid.UUID
    recipe_id: uuid.UUID
    total_energy_kcal: float
    created_entries: int
