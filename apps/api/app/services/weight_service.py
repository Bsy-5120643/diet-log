"""体重记录 service 的对外入口。"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import current_local_date
from app.models.user import User
from app.models.weight_log import WeightLog


def _zero_values() -> MacroValues:
    return MacroValues(
        energy_kcal=0.0,
        protein_g=0.0,
        fat_g=0.0,
        carb_g=0.0,
        fiber_g=0.0,
        sodium_mg=0.0,
    )


def list_between(
    db: Session,
    user: User,
    date_from: datetime.date,
    date_to: datetime.date,
) -> list[WeightLog]:
    """取某用户在 [date_from, date_to] 区间内的体重记录，按日期升序。"""
    return list(
        db.scalars(
            select(WeightLog)
            .where(
                WeightLog.user_id == user.id,
                WeightLog.logged_on >= date_from,
                WeightLog.logged_on <= date_to,
            )
            .order_by(WeightLog.logged_on.asc())
        ).all()
    )


def upsert(
    db: Session,
    user: User,
    weight_kg: Decimal,
    logged_on: datetime.date | None = None,
    note: str | None = None,
) -> WeightLog:
    """写入某天的体重；已存在则覆盖。

    一天一条既靠数据库唯一索引兜底，也在这里显式处理，
    避免依赖 ON CONFLICT 的方言差异。
    """
    target_date = logged_on or current_local_date(user.timezone)

    log = db.scalar(
        select(WeightLog).where(
            WeightLog.user_id == user.id,
            WeightLog.logged_on == target_date,
        )
    )

    if log is None:
        log = WeightLog(
            id=uuid.uuid4(),
            user_id=user.id,
            logged_on=target_date,
        )
        db.add(log)

    log.weight_kg = weight_kg
    log.note = note

    db.commit()
    db.refresh(log)
    return log


def delete(db: Session, user: User, log_id: uuid.UUID) -> bool:
    """删除一条体重记录；只能删自己的。返回是否真的删掉了。"""
    log = db.scalar(
        select(WeightLog).where(
            WeightLog.id == log_id,
            WeightLog.user_id == user.id,
        )
    )
    if log is None:
        return False

    db.delete(log)
    db.commit()
    return True
