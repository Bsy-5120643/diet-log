"""健康指数与排行榜接口。

路由保持薄：只做参数校验、调服务层、组装响应。
所有评分规则和查询策略都在 service 里。

路径刻意做成 `/health-score` 与 `/leaderboard` 两个独立路径（而不是 `/health/*`），
与需求文档里的接口命名保持一致。
"""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.errors import bad_request
from app.core.time import current_local_date, parse_iso_date
from app.db.session import get_db
from app.models.user import User
from app.schemas.health import HealthScoreOut, LeaderboardOut
from app.services import goal_service, health_score_service, leaderboard_service
from app.services.health_score import score_level

router = APIRouter(tags=["health"])


def _resolve_date(raw: str | None, user: User) -> datetime.date:
    """没传日期就用用户时区下的今天 —— 绝不用 UTC。"""
    if raw is None:
        return current_local_date(user.timezone)
    try:
        return parse_iso_date(raw)
    except ValueError as exc:
        raise bad_request("invalid_date", "日期格式应为 YYYY-MM-DD") from exc


@router.get("/health-score", response_model=HealthScoreOut)
def get_health_score(
    date: str | None = Query(default=None, description="YYYY-MM-DD，默认今天"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HealthScoreOut:
    """获取某天的健康指数。

    会**顺便计算并落库**该天的分数（幂等，重复调用不会重复插入）。
    """
    on_date = _resolve_date(date, current_user)

    row = health_score_service.calculate_health_score(db, current_user, on_date)
    week_avg, scored_days = health_score_service.week_average(
        db, current_user.id, on_date
    )

    goal = goal_service.at(db, current_user, on_date)

    return HealthScoreOut(
        date=on_date.isoformat(),
        score=row.score,
        level=score_level(row.score),
        has_goal=goal is not None,
        breakdown=row.breakdown or {"heat": 0.0, "macro": 0.0, "habit": 0.0},
        week_avg=week_avg,
        scored_days=scored_days,
        meals_logged=health_score_service.count_meals_logged(
            db, current_user.id, on_date
        ),
        streak_days=health_score_service.compute_streak_days(
            db, current_user.id, on_date
        ),
    )


@router.get("/leaderboard", response_model=LeaderboardOut)
def get_leaderboard(
    goal: str | None = Query(
        default=None,
        description="按目标过滤：减脂 / 维持 / 增肌，或 cut/maintain/gain",
    ),
    limit: int = Query(default=20, ge=1, le=50),
    days: int = Query(default=7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaderboardOut:
    """排行榜：近 N 天平均健康指数排名。

    进榜门槛为「近 N 天记录 ≥ 3 天」，防止只记一两天就霸榜。
    返回内容只含昵称、头像、平均分 —— **不含体重与热量**。
    """
    return leaderboard_service.build_leaderboard(
        db,
        viewer=current_user,
        goal=goal,
        limit=limit,
        days=days,
        min_days=settings.leaderboard_min_logged_days,
    )
