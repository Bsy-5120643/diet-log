"""汇总业务逻辑：当日汇总与区间趋势。

所有营养数值都从 food_entries 已落库的计算结果列聚合，
不在查询时重新计算 —— 保证与用户记录当时看到的值完全一致。
"""

from __future__ import annotations

import datetime
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import MEAL_ORDER
from app.models.food_entry import FoodEntry
from app.models.goal import Goal
from app.models.user import User
from app.schemas.summary import (
    DailyPointOut,
    DailySummaryOut,
    MacroTargets,
    MacroValues,
    MealBreakdown,
    SummaryRangeOut,
)
from app.services import goal_service


#: 可能为 NULL 的字段（数据缺失时算不出来，但汇总仍按 0 计入）
NULLABLE_FIELDS: tuple[str, ...] = (
    "protein_g",
    "fat_g",
    "carb_g",
    "fiber_g",
    "sodium_mg",
)


def _zero_values() -> MacroValues:
    return MacroValues(
        energy_kcal=0.0,
        protein_g=0.0,
        fat_g=0.0,
        carb_g=0.0,
        fiber_g=0.0,
        sodium_mg=0.0,
    )


def _add(dst: MacroValues, entry: FoodEntry) -> None:
    dst.energy_kcal += float(entry.energy_kcal or 0)
    dst.protein_g += float(entry.protein_g or 0)
    dst.fat_g += float(entry.fat_g or 0)
    dst.carb_g += float(entry.carb_g or 0)
    dst.fiber_g += float(entry.fiber_g or 0)
    dst.sodium_mg += float(entry.sodium_mg or 0)


def _targets_of(goal: Goal | None) -> MacroTargets | None:
    if goal is None:
        return None
    return MacroTargets(
        energy_kcal=float(goal.energy_kcal),
        protein_g=float(goal.protein_g),
        fat_g=float(goal.fat_g),
        carb_g=float(goal.carb_g),
        fiber_g=float(goal.fiber_g) if goal.fiber_g is not None else None,
        sodium_mg=float(goal.sodium_mg) if goal.sodium_mg is not None else None,
    )


def _percent(consumed: MacroValues, targets: MacroTargets | None) -> MacroValues | None:
    if targets is None:
        return None

    def ratio(value: float, target: float | None) -> float:
        if not target or target <= 0:
            return 0.0
        return round(value / target * 100, 1)

    return MacroValues(
        energy_kcal=ratio(consumed.energy_kcal, targets.energy_kcal),
        protein_g=ratio(consumed.protein_g, targets.protein_g),
        fat_g=ratio(consumed.fat_g, targets.fat_g),
        carb_g=ratio(consumed.carb_g, targets.carb_g),
        fiber_g=ratio(consumed.fiber_g, targets.fiber_g),
        sodium_mg=ratio(consumed.sodium_mg, targets.sodium_mg),
    )


def _remaining(
    consumed: MacroValues, targets: MacroTargets | None
) -> MacroValues | None:
    if targets is None:
        return None
    return MacroValues(
        energy_kcal=round(targets.energy_kcal - consumed.energy_kcal, 1),
        protein_g=round(targets.protein_g - consumed.protein_g, 1),
        fat_g=round(targets.fat_g - consumed.fat_g, 1),
        carb_g=round(targets.carb_g - consumed.carb_g, 1),
        fiber_g=round((targets.fiber_g or 0) - consumed.fiber_g, 1),
        sodium_mg=round((targets.sodium_mg or 0) - consumed.sodium_mg, 1),
    )


def _meal_rank(meal: str) -> int:
    try:
        return MEAL_ORDER.index(meal)
    except ValueError:
        return len(MEAL_ORDER)


def _goals_between(
    db: Session,
    user: User,
    date_from: datetime.date,
    date_to: datetime.date,
) -> dict[datetime.date, Goal]:
    """一次性取出区间内生效的目标段，按日期建索引。

    避免对每一天单独查一次目标（N+1 查询）。
    """
    goals = list(
        db.scalars(
            select(Goal)
            .where(Goal.user_id == user.id, Goal.effective_from <= date_to)
            .order_by(Goal.effective_from.asc())
        )
    )

    ordered: list[tuple[datetime.date, Goal]] = []
    for index, goal in enumerate(goals):
        start = max(goal.effective_from, date_from)
        end = goals[index + 1].effective_from if index + 1 < len(goals) else date_to
        cursor = start
        while cursor <= min(end, date_to):
            ordered.append((cursor, goal))
            cursor += datetime.timedelta(days=1)

    return dict(ordered)


def daily_summary(
    db: Session,
    user: User,
    on_date: datetime.date,
) -> DailySummaryOut:
    """单日汇总：摄入总量、目标、剩余、达成率、按餐次拆分。"""
    entries = list(
        db.scalars(
            select(FoodEntry).where(
                FoodEntry.user_id == user.id,
                FoodEntry.entry_date == on_date,
            )
        ).all()
    )

    consumed = _zero_values()
    by_meal: dict[str, MealBreakdown] = {
        meal: MealBreakdown(energy_kcal=0.0, entry_count=0) for meal in MEAL_ORDER
    }

    # 记录哪些字段因为原始数据缺失而算不出来。
    # 只要当天任意一条记录的该字段是 NULL，就认为这项数据不完整。
    incomplete: set[str] = set()

    for entry in entries:
        _add(consumed, entry)
        for field in NULLABLE_FIELDS:
            if getattr(entry, field) is None:
                incomplete.add(field)

        bucket = by_meal.get(entry.meal_type)
        if bucket is None:
            bucket = MealBreakdown(energy_kcal=0.0, entry_count=0)
            by_meal[entry.meal_type] = bucket
        bucket.energy_kcal = round(bucket.energy_kcal + float(entry.energy_kcal or 0), 1)
        bucket.entry_count += 1

    goal = goal_service.at(db, user, on_date)
    targets = _targets_of(goal)

    return DailySummaryOut(
        date=on_date.isoformat(),
        consumed=consumed,
        targets=targets,
        remaining=None if targets is None else _remaining(consumed, targets),
        percent=None if targets is None else _percent(consumed, targets),
        by_meal=by_meal,
        entry_count=len(entries),
        incomplete_fields=sorted(incomplete),
    )


def range_summary(
    db: Session,
    user: User,
    date_from: datetime.date,
    date_to: datetime.date,
) -> SummaryRangeOut:
    """区间每日汇总。

    days 会**补齐区间内所有日期**：没有记录的天以 0 出现。
    否则前端折线图会有断点、x 轴刻度错位。
    """
    rows = list(
        db.execute(
            select(
                FoodEntry.entry_date,
                func.count(FoodEntry.id).label("entry_count"),
                func.coalesce(func.sum(FoodEntry.energy_kcal), 0).label("energy_kcal"),
                func.coalesce(func.sum(FoodEntry.protein_g), 0).label("protein_g"),
                func.coalesce(func.sum(FoodEntry.fat_g), 0).label("fat_g"),
                func.coalesce(func.sum(FoodEntry.carb_g), 0).label("carb_g"),
            )
            .where(
                FoodEntry.user_id == user.id,
                FoodEntry.entry_date >= date_from,
                FoodEntry.entry_date <= date_to,
            )
            .group_by(FoodEntry.entry_date)
        )
    )

    totals = {row.entry_date: row for row in rows}
    goals_by_date = _goals_between(db, user, date_from, date_to)

    days: list[DailyPointOut] = []
    cursor = date_from
    while cursor <= date_to:
        row = totals.get(cursor)
        goal = goals_by_date.get(cursor)
        days.append(
            DailyPointOut(
                date=cursor.isoformat(),
                energy_kcal=round(float(row.energy_kcal), 1) if row else 0.0,
                protein_g=round(float(row.protein_g), 1) if row else 0.0,
                fat_g=round(float(row.fat_g), 1) if row else 0.0,
                carb_g=round(float(row.carb_g), 1) if row else 0.0,
                target_kcal=float(goal.energy_kcal) if goal else None,
                entry_count=int(row.entry_count) if row else 0,
            )
        )
        cursor += datetime.timedelta(days=1)

    return SummaryRangeOut(
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        days=days,
    )
