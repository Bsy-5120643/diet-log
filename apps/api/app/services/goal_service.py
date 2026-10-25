"""目标业务逻辑：把 goal_calculator 的纯计算结果落库。"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import current_local_date
from app.models.enums import GoalSource, GoalType
from app.models.goal import Goal
from app.models.user import User
from app.schemas.goal import (
    GoalEstimateRequest,
    GoalOut,
    GoalUpdateRequest,
)
from app.services.goal_calculator import BodyProfile, GoalPlan, build_goal_plan


def _to_profile(payload: GoalEstimateRequest | GoalUpdateRequest) -> BodyProfile:
    return BodyProfile(
        sex=payload.sex,
        age=payload.age,
        height_cm=payload.height_cm,
        weight_kg=payload.weight_kg,
        activity_level=payload.activity_level,
    )


def estimate(payload: GoalEstimateRequest) -> GoalPlan:
    """只算不存，供前端表单实时预览。"""
    return build_goal_plan(
        profile=_to_profile(payload),
        goal_type=payload.goal_type,
        deficit_pct=payload.deficit_pct,
    )


def at(db: Session, user: User, on_date: datetime.date) -> Goal | None:
    """取某天生效的目标：生效日期 <= 该日期，取最新一条。"""
    return db.scalar(
        select(Goal)
        .where(Goal.user_id == user.id, Goal.effective_from <= on_date)
        .order_by(Goal.effective_from.desc())
        .limit(1)
    )


def current(db: Session, user: User) -> Goal | None:
    """取当前（用户时区下的今天）生效的目标。"""
    return at(db, user, current_local_date(user.timezone))


def upsert(db: Session, user: User, payload: GoalUpdateRequest) -> Goal:
    """新建或更新目标，并同步刷新 users 上的当前身体档案。"""
    plan = build_goal_plan(
        profile=_to_profile(payload),
        goal_type=payload.goal_type,
        deficit_pct=payload.deficit_pct,
    )

    # 生效日期：优先用客户端传的（客户端最清楚用户本地日期），
    # 否则按用户档案里的时区自行推算。
    target_date = payload.effective_from or current_local_date(user.timezone)

    goal = db.scalar(
        select(Goal).where(
            Goal.user_id == user.id, Goal.effective_from == target_date
        )
    )

    if goal is None:
        goal = Goal(
            id=uuid.uuid4(),
            user_id=user.id,
            effective_from=target_date,
            source=GoalSource.CALCULATED.value,
        )
        db.add(goal)

    goal.source = GoalSource.CALCULATED.value

    # 目标值
    goal.energy_kcal = plan.target_kcal
    goal.protein_g = plan.macros.protein_g
    goal.fat_g = plan.macros.fat_g
    goal.carb_g = plan.macros.carb_g
    goal.fiber_g = plan.fiber_g
    goal.sodium_mg = plan.sodium_mg

    # 目标类型与活动水平
    goal.goal_type = payload.goal_type.value
    goal.activity_level = payload.activity_level.value

    # 输入快照 + 计算中间量：让这条目标可以自证来源
    goal.age = payload.age
    goal.sex = payload.sex.value
    goal.height_cm = payload.height_cm
    goal.weight_kg = payload.weight_kg
    goal.bmr_kcal = plan.bmr_kcal
    goal.tdee_kcal = plan.tdee_kcal
    goal.deficit_pct = plan.deficit_pct

    # 同步刷新当前身体档案，下次进设置页直接回显
    user.sex = payload.sex.value
    user.age = payload.age
    user.height_cm = payload.height_cm
    user.weight_kg = payload.weight_kg

    db.commit()
    db.refresh(goal)
    return goal


def to_out(goal: Goal) -> GoalOut:
    return GoalOut.model_validate(goal)
