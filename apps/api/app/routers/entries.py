"""饮食记录接口。

POST   /food-entries            新增一条（服务端做快照计算）
GET    /food-entries?date=      查询某天记录
DELETE /food-entries/{id}       删除一条
"""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request, not_found
from app.core.time import current_local_date, parse_iso_date
from app.db.session import get_db
from app.models.user import User
from app.schemas.food_entry import (
    FoodEntryCreate,
    FoodEntryListOut,
    FoodEntryOut,
)
from app.services import entry_service

router = APIRouter(prefix="/food-entries", tags=["food-entries"])


def _resolve_date(raw: str | None, user: User) -> datetime.date:
    """没传日期就用用户时区下的今天 —— 绝不用 UTC。"""
    if raw is None:
        return current_local_date(user.timezone)
    try:
        return parse_iso_date(raw)
    except ValueError as exc:
        raise bad_request("invalid_date", "日期格式应为 YYYY-MM-DD") from exc


def _out(entry, db: Session) -> FoodEntryOut:
    from app.models.food import Food

    food = db.get(Food, entry.food_id)
    return entry_service.to_out(entry, food.name if food else "（已下架）")


@router.post("", response_model=FoodEntryOut, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: FoodEntryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FoodEntryOut:
    """新增记录。

    只接收 food_id / 克数 / 餐次 / 日期，营养值由服务端现算。
    """
    try:
        entry = entry_service.create(db, current_user, payload)
    except entry_service.FoodNotFoundError as exc:
        raise not_found("food_not_found", "食物不存在或已下架") from exc
    except ValueError as exc:
        raise bad_request("invalid_entry_input", str(exc)) from exc

    return _out(entry, db)


@router.get("", response_model=FoodEntryListOut)
def list_entries(
    date: str | None = Query(default=None, description="YYYY-MM-DD，默认今天"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FoodEntryListOut:
    """查询某天的全部记录。没有记录时返回 200 + 空数组。"""
    on_date = _resolve_date(date, current_user)
    entries = entry_service.list_by_date(db, current_user, on_date)

    return FoodEntryListOut(
        date=on_date.isoformat(),
        items=[_out(entry, db) for entry in entries],
        total=len(entries),
    )


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """删除一条记录，只能删自己的。"""
    entry_service.delete(db, current_user, entry_id)
