"""排行榜查询。

## 三步走，避免在 Python 里做大循环

1. **筛资格**：近 N 天有 ≥3 天记录的用户（一条 GROUP BY，走 `(user_id, entry_date)` 索引）
2. **按目标过滤**：取每个用户当前生效的目标，与 ① 取交集
3. **聚合排名**：只在候选集合上用 SQL `AVG` 求均分并排序——不做全表扫描

## 关于「当前生效目标」的可移植写法

Postgres 有 `DISTINCT ON`，但 **SQLite 不支持**，而我们的测试跑在 SQLite 上。
所以统一用「子查询取 MAX(effective_from) 再 JOIN」，两边都成立。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.food_entry import FoodEntry
from app.models.goal import Goal
from app.models.health_score import DailyHealthScore
from app.models.user import User
from app.schemas.health import LeaderboardEntryOut, LeaderboardMeOut, LeaderboardOut


#: 目标别名：前端传中文，内部用枚举值
GOAL_ALIASES: dict[str, str] = {
    # 减脂
    "cut": "cut", "减脂": "cut", "减重": "cut", "cutting": "cut",
    # 维持
    "maintain": "maintain", "维持": "maintain", "保持": "maintain",
    # 增肌
    "gain": "gain", "增肌": "gain", "增重": "gain", "bulking": "gain",
}


def normalize_goal(value: str | None) -> str | None:
    """把 `?goal=减脂` 这类输入归一化成内部枚举值。无法识别返回 None（不过滤）。"""
    if value is None:
        return None
    return GOAL_ALIASES.get(value.strip().lower())


def eligible_users(
    db: Session,
    date_from: datetime.date,
    date_to: datetime.date,
    min_days: int = 3,
) -> dict[uuid.UUID, int]:
    """近 N 天记录 ≥ min_days 天的用户。返回 {user_id: 有记录的天数}。

    这一步是防作弊 / 防偶然霸榜的关键：只记了一两天就拿高分的不进榜。
    """
    rows = db.execute(
        select(
            FoodEntry.user_id,
            func.count(func.distinct(FoodEntry.entry_date)).label("days"),
        )
        .where(FoodEntry.entry_date >= date_from, FoodEntry.entry_date <= date_to)
        .group_by(FoodEntry.user_id)
        .having(func.count(func.distinct(FoodEntry.entry_date)) >= min_days)
    ).all()
    return {row[0]: int(row[1]) for row in rows}


def logged_days(
    db: Session,
    user_id: uuid.UUID,
    date_from: datetime.date,
    date_to: datetime.date,
) -> int:
    """某用户在区间内有多少天记过录（**不带门槛**）。

    不能复用 `eligible_users` 的结果 —— 那只含够格的用户，
    没够格的会查成 0，前端就没法提示「再记录 N 天即可上榜」。
    """
    value = db.scalar(
        select(func.count(func.distinct(FoodEntry.entry_date))).where(
            FoodEntry.user_id == user_id,
            FoodEntry.entry_date >= date_from,
            FoodEntry.entry_date <= date_to,
        )
    )
    return int(value or 0)


def users_with_goal(db: Session, goal_type: str, as_of: datetime.date) -> set[uuid.UUID]:
    """当前生效目标为 goal_type 的用户集合。"""
    latest = (
        select(Goal.user_id, func.max(Goal.effective_from).label("mx"))
        .where(Goal.effective_from <= as_of)
        .group_by(Goal.user_id)
        .subquery()
    )
    rows = db.execute(
        select(Goal.user_id)
        .join(
            latest,
            (Goal.user_id == latest.c.user_id) & (Goal.effective_from == latest.c.mx),
        )
        .where(Goal.goal_type == goal_type)
    ).all()
    return {row[0] for row in rows}


def ensure_scores(
    db: Session,
    user_ids: set[uuid.UUID],
    date_from: datetime.date,
    date_to: datetime.date,
    max_users: int,
) -> None:
    """为候选用户补齐缺失日期的分数（有上限，防止请求被拖垮）。"""
    from app.services import health_score_service

    ordered = sorted(user_ids, key=str)[:max_users]
    users = db.scalars(select(User).where(User.id.in_(ordered))).all()

    for user in users:
        dates = set(
            db.scalars(
                select(FoodEntry.entry_date)
                .where(
                    FoodEntry.user_id == user.id,
                    FoodEntry.entry_date >= date_from,
                    FoodEntry.entry_date <= date_to,
                )
                .distinct()
            ).all()
        )
        for day in sorted(dates):
            if health_score_service.get_daily_score(db, user.id, day) is None:
                health_score_service.calculate_health_score(db, user, day)


def rank_rows(
    db: Session,
    user_ids: list[uuid.UUID],
    date_from: datetime.date,
    date_to: datetime.date,
) -> list[tuple[uuid.UUID, float]]:
    """按平均分降序排列。只查候选用户，不做全表聚合。"""
    if not user_ids:
        return []

    rows = db.execute(
        select(DailyHealthScore.user_id, func.avg(DailyHealthScore.score))
        .where(
            DailyHealthScore.user_id.in_(user_ids),
            DailyHealthScore.score_date >= date_from,
            DailyHealthScore.score_date <= date_to,
        )
        .group_by(DailyHealthScore.user_id)
        .order_by(func.avg(DailyHealthScore.score).desc())
    ).all()
    return [(row[0], float(row[1])) for row in rows]


def build_leaderboard(
    db: Session,
    *,
    viewer: User,
    goal: str | None = None,
    limit: int = 20,
    days: int = 7,
    until: datetime.date | None = None,
    min_days: int = 3,
) -> LeaderboardOut:
    """组装榜单。"""
    from app.core.time import current_local_date

    if until is None:
        until = current_local_date(viewer.timezone)
    date_from = until - datetime.timedelta(days=days - 1)

    # ① 资格
    eligible = eligible_users(db, date_from, until, min_days)

    # ② 目标过滤
    goal_norm = normalize_goal(goal)
    candidates = set(eligible.keys())
    if goal_norm is not None:
        candidates &= users_with_goal(db, goal_norm, until)

    # 补算缺失分数
    if candidates:
        ensure_scores(
            db,
            candidates,
            date_from,
            until,
            settings.leaderboard_max_compute_users,
        )

    # ③ 聚合排序
    ranked = rank_rows(db, list(candidates), date_from, until)
    top = ranked[:limit]

    # 脱敏：只取昵称与头像
    top_ids = [uid for uid, _ in top]
    users = {
        u.id: u for u in db.scalars(select(User).where(User.id.in_(top_ids))).all()
    }

    items: list[LeaderboardEntryOut] = []
    for index, (uid, avg) in enumerate(top):
        user = users.get(uid)
        if user is None:
            continue
        items.append(
            LeaderboardEntryOut(
                rank=index + 1,
                nickname=user.nickname or "匿名用户",
                avatar_url=user.avatar_url,
                avg_score=round(avg, 1),
            )
        )

    # 自己的排名
    me = LeaderboardMeOut(
        qualified=viewer.id in candidates,
        # 单独查：没够格也要知道记了几天，前端才能提示「再记 N 天即可上榜」
        logged_days=logged_days(db, viewer.id, date_from, until),
    )
    for index, (uid, avg) in enumerate(ranked):
        if uid == viewer.id:
            me.rank = index + 1
            me.avg_score = round(avg, 1)
            break

    return LeaderboardOut(
        goal=goal_norm,
        date_from=date_from.isoformat(),
        date_to=until.isoformat(),
        items=items,
        me=me,
    )
