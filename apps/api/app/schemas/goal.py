"""目标相关出入参模型。

校验规则与前端 zod schema 一一对应（见 apps/web/lib/validation/schemas.ts），
前端负责即时反馈，这里负责权威校验。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ActivityLevel, GoalType, Sex

MIN_AGE, MAX_AGE = 14, 100
MIN_HEIGHT_CM, MAX_HEIGHT_CM = Decimal("50"), Decimal("250")
MIN_WEIGHT_KG, MAX_WEIGHT_KG = Decimal("20"), Decimal("400")
MAX_DEFICIT_PCT = Decimal("0.20")


def _round1(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


class GoalInputs(BaseModel):
    """计算目标所需的全部输入。"""

    sex: Sex
    age: int = Field(ge=MIN_AGE, le=MAX_AGE)
    height_cm: Decimal = Field(gt=MIN_HEIGHT_CM, le=MAX_HEIGHT_CM)
    weight_kg: Decimal = Field(gt=MIN_WEIGHT_KG, le=MAX_WEIGHT_KG)
    activity_level: ActivityLevel
    goal_type: GoalType
    # 减脂缺口，0~0.20；维持/增肌时忽略
    deficit_pct: Decimal = Field(default=MAX_DEFICIT_PCT, ge=Decimal("0"), le=MAX_DEFICIT_PCT)

    @field_validator("height_cm", "weight_kg", mode="before")
    @classmethod
    def _coerce_decimal(cls, value: object) -> Decimal:
        """前端可能传 int/float/str，统一转 Decimal 再校验精度。"""
        if isinstance(value, Decimal):
            return _round1(value)
        if isinstance(value, (int, float, str)):
            return _round1(Decimal(str(value)))
        raise TypeError(f"无法转换为 Decimal: {type(value)!r}")


class GoalEstimateRequest(GoalInputs):
    """只算不存：用于前端表单实时预览。"""


class GoalEstimateOut(BaseModel):
    bmr_kcal: float
    tdee_kcal: float
    target_kcal: int
    protein_g: float
    fat_g: float
    carb_g: float
    fiber_g: float
    sodium_mg: float
    deficit_pct: float


class GoalUpdateRequest(GoalInputs):
    effective_from: datetime.date | None = None


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    effective_from: datetime.date
    source: str

    # 目标值
    energy_kcal: float
    protein_g: float
    fat_g: float
    carb_g: float
    fiber_g: float | None = None
    sodium_mg: float | None = None

    # 计算依据（source='calculated' 时有值）
    goal_type: str | None = None
    activity_level: str | None = None
    bmr_kcal: float | None = None
    tdee_kcal: float | None = None
    deficit_pct: float | None = None

    # 输入快照
    sex: str | None = None
    age: int | None = None
    height_cm: float | None = None
    weight_kg: float | None = None

    updated_at: datetime.datetime
