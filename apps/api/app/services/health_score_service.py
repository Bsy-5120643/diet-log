"""健康指数服务层：取数 → 调纯函数 → 落库。

本层只做 IO 与编排，**不含任何评分规则** —— 规则全在 `health_score.py`。

主要函数：
- `compute_streak_days` 连续打卡天数（按日期回溯）
- `count_meals_logged` 当天记录了多少个不同餐次
- `calculate_health_score` 计算并 upsert 当天得分
- `week_average` 近 7 天平均分
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.food_entry import FoodEntry
from app.models.health_score import DailyHealthScore
from app.models.user import User
from app.services import goal_service, summary_service
from app.services.health_score import (
    HealthScoreBreakdown,
    MacroAmounts,
    ScoreInput,
    compute_health_score as _compute,
)

#: streak 最多回溯多少天，防止有人几年前记过一次就一直循环
MAX_STREAK_LOOKBACK_DAYS = 365


# ---------------------------------------------------------------------------
# 取数辅助
# ---------------------------------------------------------------------------


def count_meals_logged(db: Session, user_id: uuid.UUID, on_date: datetime.date) -> int:
    """当天记录了多少个**不同餐次**（早餐/午餐/晚餐/加餐/夜宵）。"""
    value = db.scalar(
        select(func.count(func.distinct(FoodEntry.meal_type))).where(
            FoodEntry.user_id == user_id,
            FoodEntry.entry_date == on_date,
        )
    )
    return int(value or 0)


def compute_streak_days(
    db: Session,
    user_id: uuid.UUID,
    until: datetime.date,
    *,
    max_lookback: int = MAX_STREAK_LOOKBACK_DAYS,
) -> int:
    """连续打卡天数：从 `until` 往前回溯，遇到断档就停。

    几条约定：

    - **连续必须终止于 `until` 当天**。当天没记 → 0 分
      （即使前几天记了，streak 也已经断了）
    - 「昨天没记、今天记了」→ 1（从今天重新起算）
    - 「今天记了、昨天记了、前天没记」→ 2

    只查一次区间内的去重日期，然后在内存里回溯，
    避免每天一次 SQL 查询。
    """
    start = until - datetime.timedelta(days=max_lookback)
    logged_dates = set(
        db.scalars(
            select(FoodEntry.entry_date)
            .where(
                FoodEntry.user_id == user_id,
                FoodEntry.entry_date >= start,
                FoodEntry.entry_date <= until,
            )
            .distinct()
        ).all()
    )

    if until not in logged_dates:
        return 0

    streak = 0
    cursor = until
    while cursor in logged_dates:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return streak


def load_score_input(db: Session, user: User, on_date: datetime.date) -> ScoreInput:
    """汇总计算一天得分所需的全部输入。"""
    summary = summary_service.daily_summary(db, user, on_date)
    goal = goal_service.at(db, user, on_date)

    consumed = MacroAmounts(
        protein_g=summary.consumed.protein_g,
        carb_g=summary.consumed.carb_g,
        fat_g=summary.consumed.fat_g,
    )

    target: MacroAmounts | None = None
    target_kcal: float | None = None
    bmr_kcal: float | None = None

    if goal is not None:
        target = MacroAmounts(
            protein_g=float(goal.protein_g),
            carb_g=float(goal.carb_g),
            fat_g=float(goal.fat_g),
        )
        target_kcal = float(goal.energy_kcal)
        bmr_kcal = float(goal.bmr_kcal) if goal.bmr_kcal is not None else None

    return ScoreInput(
        consumed_kcal=summary.consumed.energy_kcal,
        consumed=consumed,
        target_kcal=target_kcal,
        target=target,
        bmr_kcal=bmr_kcal,
        meals_logged=count_meals_logged(db, user.id, on_date),
        streak_days=compute_streak_days(db, user.id, on_date),
    )


# ---------------------------------------------------------------------------
# 计算与落库
# ---------------------------------------------------------------------------


def _upsert(
    db: Session,
    user_id: uuid.UUID,
    on_date: datetime.date,
    breakdown: HealthScoreBreakdown,
) -> DailyHealthScore:
    """写入或更新当天得分。唯一索引保证同一天只有一行。"""
    row = db.scalar(
        select(DailyHealthScore).where(
            DailyHealthScore.user_id == user_id,
            DailyHealthScore.score_date == on_date,
        )
    )
    if row is None:
        row = DailyHealthScore(
            id=uuid.uuid4(),
            user_id=user_id,
            score_date=on_date,
        )
        db.add(row)

    row.score = breakdown.total
    row.breakdown = {
        "heat": breakdown.heat,
        "macro": breakdown.macro,
        "habit": breakdown.habit,
    }

    db.commit()
    db.refresh(row)
    return row


def calculate_health_score(
    db: Session,
    user: User,
    on_date: datetime.date | None = None,
) -> DailyHealthScore:
    """计算并持久化某天的健康指数。

    :param on_date: 默认按用户时区取今天
    """
    if on_date is None:
        from app.core.time import current_local_date

        on_date = current_local_date(user.timezone)

    data = load_score_input(db, user, on_date)
    breakdown = _compute(data)
    return _upsert(db, user.id, on_date, breakdown)


def calculate_health_score_by_id(
    db: Session,
    user_id: uuid.UUID,
    on_date: datetime.date,
) -> DailyHealthScore:
    """按 user_id 计算（批量任务用）。"""
    user = db.get(User, user_id)
    if user is None:
        raise ValueError(f"用户不存在: {user_id}")
    return calculate_health_score(db, user, on_date)


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------


def get_daily_score(
    db: Session,
    user_id: uuid.UUID,
    on_date: datetime.date,
) -> DailyHealthScore | None:
    """读取已落库的当天得分；没有则 None。"""
    return db.scalar(
        select(DailyHealthScore).where(
            DailyHealthScore.user_id == user_id,
            DailyHealthScore.score_date == on_date,
        )
    )


def week_average(
    db: Session,
    user_id: uuid.UUID,
    until: datetime.date,
    *,
    days: int = 7,
) -> tuple[float | None, int]:
    """近 N 天平均分。返回 (平均分, 有分数的天数)。

    只统计**已有分数**的天；没算过的不补算（由调用方决定要不要先补）。
    """
    start = until - datetime.timedelta(days=days - 1)
    rows = list(
        db.scalars(
            select(DailyHealthScore).where(
                DailyHealthScore.user_id == user_id,
                DailyHealthScore.score_date >= start,
                DailyHealthScore.score_date <= until,
            )
        ).all()
    )
    if not rows:
        return None, 0

    total = sum(row.score for row in rows)
    return round(total / len(rows), 1), len(rows)
