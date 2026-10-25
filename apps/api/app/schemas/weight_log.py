"""体重记录出入参模型。"""

from __future__ import annotations

import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class WeightLogCreate(BaseModel):
    """新增/覆盖某天的体重。

    logged_on 可省略，省略时用「用户时区下的今天」。
    同一天重复提交按 upsert 处理（覆盖），不报错。
    """

    weight_kg: Decimal = Field(gt=Decimal("20"), le=Decimal("400"))
    logged_on: datetime.date | None = None
    note: str | None = Field(default=None, max_length=200)


class WeightLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    logged_on: str
    weight_kg: float
    note: str | None = None
    created_at: datetime.datetime


class WeightLogListOut(BaseModel):
    """GET /weight-logs 的返回。

    logs 按日期升序。即使一条都没有，也返回 200 + 空数组，
    由前端展示引导文案。
    """

    date_from: str
    date_to: str
    logs: list[WeightLogOut]
