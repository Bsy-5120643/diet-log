"""体重记录接口。

- GET    /weight-logs?from=&to=    查询区间内记录，升序
- POST   /weight-logs              记录某天体重（同日覆盖）
- DELETE /weight-logs/{id}         删除一条
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request
from app.core.time import current_local_date, parse_iso_date
from app.db.session import get_db
from app.models.user import User
from app.schemas.weight_log import (
    WeightLogCreate,
    WeightLogListOut,
    WeightLogOut,
)
from app.services import weight_service

router = APIRouter(prefix="/weight-logs", tags=["weight-logs"])

#: 看板默认取最近 7 天
DEFAULT_RANGE_DAYS = 7
MAX_RANGE_DAYS = 366


def _resolve_date(raw: str | None, user: User) -> datetime.date:
    """没传日期就用用户时区下的今天 —— 绝不用 UTC。"""
    if raw is None:
        return current_local_date(user.timezone)
    try:
        return parse_iso_date(raw)
    except ValueError as exc:
        raise bad_request("invalid_date", "日期格式应为 YYYY-MM-DD") from exc


def _to_out(log) -> WeightLogOut:
    return WeightLogOut(
        id=str(log.id),
        logged_on=log.logged_on.isoformat(),
        weight_kg=float(log.weight_kg),
        note=log.note,
        created_at=log.created_at,
    )


@router.get("", response_model=WeightLogListOut)
def list_weight_logs(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightLogListOut:
    """查询区间内的体重记录，按日期升序。

    不传参数时默认返回最近 7 天（含今天）。没有任何记录时返回 200 + 空数组。
    """
    d_to = _resolve_date(date_to, current_user)
    if date_from is None:
        d_from = d_to - datetime.timedelta(days=DEFAULT_RANGE_DAYS - 1)
    else:
        d_from = _resolve_date(date_from, current_user)

    if d_from > d_to:
        raise bad_request("invalid_range", "起始日期不能晚于结束日期")

    if (d_to - d_from).days + 1 > MAX_RANGE_DAYS:
        raise bad_request("range_too_long", f"查询区间不能超过 {MAX_RANGE_DAYS} 天")

    logs = weight_service.list_between(db, current_user, d_from, d_to)

    return WeightLogListOut(
        date_from=d_from.isoformat(),
        date_to=d_to.isoformat(),
        logs=[_to_out(log) for log in logs],
    )


@router.post("", response_model=WeightLogOut, status_code=status.HTTP_201_CREATED)
def create_weight_log(
    payload: WeightLogCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightLogOut:
    """记录某天体重。同一天已存在则覆盖更新。"""
    try:
        log = weight_service.upsert(
            db,
            current_user,
            weight_kg=payload.weight_kg,
            logged_on=payload.logged_on,
            note=payload.note,
        )
    except ValueError as exc:
        raise bad_request("invalid_weight_input", str(exc)) from exc

    return _to_out(log)
