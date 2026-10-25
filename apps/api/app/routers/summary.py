"""汇总接口。

- GET /summary?date=YYYY-MM-DD     当日摄入 / 目标 / 剩余 / 达成率
- GET /summary/range?from=&to=     区间每日摄入，供趋势折线图使用
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import bad_request
from app.core.time import current_local_date, parse_iso_date
from app.db.session import get_db
from app.models.user import User
from app.schemas.summary import DailySummaryOut, SummaryRangeOut
from app.services import summary_service

router = APIRouter(prefix="/summary", tags=["summary"])

#: 区间最大天数，防止有人传 from=1970 把库扫穿
MAX_RANGE_DAYS = 366


def _resolve_date(raw: str | None, user: User) -> datetime.date:
    """没传日期就用用户时区下的今天 —— 绝不用 UTC。"""
    if raw is None:
        return current_local_date(user.timezone)
    try:
        return parse_iso_date(raw)
    except ValueError as exc:
        raise bad_request("invalid_date", "日期格式应为 YYYY-MM-DD") from exc


@router.get("", response_model=DailySummaryOut)
def get_daily_summary(
    date: str | None = Query(default=None, description="YYYY-MM-DD，默认今天"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailySummaryOut:
    """当日汇总。没设置目标时 targets / remaining / percent 为 null，接口仍返回 200。"""
    on_date = _resolve_date(date, current_user)
    return summary_service.daily_summary(db, current_user, on_date)


@router.get("/range", response_model=SummaryRangeOut)
def get_range_summary(
    date_from: str = Query(alias="from", description="起始日期 YYYY-MM-DD"),
    date_to: str = Query(alias="to", description="结束日期 YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryRangeOut:
    """区间每日汇总。days 按日期升序且补齐所有日期（无记录补 0）。"""
    d_from = _resolve_date(date_from, current_user)
    d_to = _resolve_date(date_to, current_user)

    if d_from > d_to:
        raise bad_request("invalid_range", "起始日期不能晚于结束日期")

    if (d_to - d_from).days + 1 > MAX_RANGE_DAYS:
        raise bad_request(
            "range_too_long",
            f"查询区间不能超过 {MAX_RANGE_DAYS} 天",
        )

    return summary_service.range_summary(db, current_user, d_from, d_to)
