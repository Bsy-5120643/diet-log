"""饮食记录业务逻辑。

核心：**这里是营养计算的唯一入口。**
读食物当前每 100g 值 → 快照 → 按克数换算 → 落库。
客户端提交的任何营养值都不采信。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import current_local_date
from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.user import User
from app.schemas.food_entry import (
    MEAL_LABEL_MAP,
    FoodEntryCreate,
    FoodEntryOut,
)
from app.services.nutrition import scale, snapshot_of


class FoodNotFoundError(Exception):
    """食物不存在或已下架。"""


class EntryNotFoundError(Exception):
    """记录不存在，或不属于当前用户。"""


def create(db: Session, user: User, payload: FoodEntryCreate) -> FoodEntry:
    """新增一条饮食记录。

    快照在这里生成：把「当时食物的每 100g 值」固化下来，
    以后食物库被修正，历史记录也不会跟着变。
    """
    food = db.get(Food, payload.food_id)
    if food is None or not food.is_active:
        raise FoodNotFoundError(str(payload.food_id))

    on_date = payload.entry_date or current_local_date(user.timezone)
    quantity = payload.quantity_g

    # 快照 + 换算，缺失字段保持 None
    snapshot = snapshot_of(food)
    amounts = scale(snapshot, quantity)

    # 份量冗余：记录「几个什么单位」，便于下次一键复现
    serving_grams_per_unit: Decimal | None = None
    if payload.serving_count and payload.serving_count > 0:
        serving_grams_per_unit = (quantity / payload.serving_count).quantize(
            Decimal("0.01")
        )

    entry = FoodEntry(
        id=uuid.uuid4(),
        user_id=user.id,
        food_id=food.id,
        entry_date=on_date,
        meal_type=payload.meal_type.value,
        quantity_g=quantity,
        serving_unit=payload.serving_unit,
        serving_count=payload.serving_count,
        serving_grams_per_unit=serving_grams_per_unit,
        snapshot_energy_kcal=snapshot.energy_kcal,
        snapshot_protein_g=snapshot.protein_g,
        snapshot_fat_g=snapshot.fat_g,
        snapshot_carb_g=snapshot.carb_g,
        snapshot_fiber_g=snapshot.fiber_g,
        snapshot_sodium_mg=snapshot.sodium_mg,
        energy_kcal=amounts.energy_kcal,
        protein_g=amounts.protein_g,
        fat_g=amounts.fat_g,
        carb_g=amounts.carb_g,
        fiber_g=amounts.fiber_g,
        sodium_mg=amounts.sodium_mg,
        note=payload.note,
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_by_date(
    db: Session,
    user: User,
    on_date: datetime.date,
) -> list[FoodEntry]:
    """某天的全部记录，按创建时间升序。"""
    return list(
        db.scalars(
            select(FoodEntry)
            .where(
                FoodEntry.user_id == user.id,
                FoodEntry.entry_date == on_date,
            )
            .order_by(FoodEntry.created_at.asc())
        ).all()
    )


def delete(db: Session, user: User, entry_id: uuid.UUID) -> bool:
    """删除一条记录；只能删自己的。返回是否真的删掉了。"""
    entry = db.scalar(
        select(FoodEntry).where(
            FoodEntry.id == entry_id,
            FoodEntry.user_id == user.id,
        )
    )
    if entry is None:
        return False

    db.delete(entry)
    db.commit()
    return True


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def to_out(entry: FoodEntry, food_name: str) -> FoodEntryOut:
    return FoodEntryOut(
        id=entry.id,
        food_id=entry.food_id,
        food_name=food_name,
        entry_date=entry.entry_date.isoformat(),
        meal_type=entry.meal_type,
        meal_label=MEAL_LABEL_MAP.get(entry.meal_type, entry.meal_type),
        quantity_g=float(entry.quantity_g),
        serving_unit=entry.serving_unit,
        serving_count=_to_float(entry.serving_count),
        energy_kcal=float(entry.energy_kcal),
        protein_g=_to_float(entry.protein_g),
        fat_g=_to_float(entry.fat_g),
        carb_g=_to_float(entry.carb_g),
        fiber_g=_to_float(entry.fiber_g),
        sodium_mg=_to_float(entry.sodium_mg),
        per_100g={
            "energy_kcal": _to_float(entry.snapshot_energy_kcal),
            "protein_g": _to_float(entry.snapshot_protein_g),
            "fat_g": _to_float(entry.snapshot_fat_g),
            "carb_g": _to_float(entry.snapshot_carb_g),
            "fiber_g": _to_float(entry.snapshot_fiber_g),
            "sodium_mg": _to_float(entry.snapshot_sodium_mg),
        },
        note=entry.note,
        created_at=entry.created_at,
    )
