"""饮食记录出入参模型。

设计约定：**客户端只提交原始输入，不提交算好的营养值。**
热量和营养素一律由服务端按「食物每 100g 值 × 克数」现算并落库快照，
否则前端可以随手提交任意数值，数据就不可信了。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import MEAL_TYPES, MealType


class FoodEntryCreate(BaseModel):
    """新增一条饮食记录。"""

    food_id: uuid.UUID
    meal_type: MealType
    #: 实际克数，权威值；所有计算基于它
    quantity_g: Decimal = Field(gt=Decimal("0"), le=Decimal("5000"))
    #: 省略时用「用户时区下的今天」
    entry_date: datetime.date | None = None
    #: 份量录入方式（可选，仅用于还原用户当时的操作）
    serving_unit: str | None = Field(default=None, max_length=16)
    serving_count: Decimal | None = Field(default=None, gt=Decimal("0"))
    note: str | None = Field(default=None, max_length=200)

    @field_validator("quantity_g", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.01"))
        if isinstance(value, (int, float, str)):
            return Decimal(str(value)).quantize(Decimal("0.01"))
        raise TypeError(f"克数无法转换: {type(value)!r}")


class FoodEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    food_id: uuid.UUID
    food_name: str
    entry_date: str
    meal_type: str
    meal_label: str

    quantity_g: float
    serving_unit: str | None = None
    serving_count: float | None = None

    #: 本次实际摄入（null 表示食物原始数据缺失）
    energy_kcal: float
    protein_g: float | None = None
    fat_g: float | None = None
    carb_g: float | None = None
    fiber_g: float | None = None
    sodium_mg: float | None = None

    #: 每 100g 快照，便于前端展示「这份食物的单位营养」
    per_100g: dict[str, float | None]

    note: str | None = None
    created_at: datetime.datetime


class FoodEntryListOut(BaseModel):
    date: str
    items: list[FoodEntryOut]
    total: int


#: 餐次中文名，供前端直接展示（避免前后端各写一份）
MEAL_LABEL_MAP: dict[str, str] = {
    "breakfast": "早餐",
    "lunch": "午餐",
    "dinner": "晚餐",
    "snack": "加餐",
    "late_night": "夜宵",
}

assert set(MEAL_LABEL_MAP) == set(MEAL_TYPES), "餐次标签与枚举不一致"
