"""目标接口：估算（只算不存）/ 获取当前目标 / 新建或更新目标。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.core.deps import get_current_user
from app.core.errors import bad_request, not_found
from app.db.session import get_db
from app.models.user import User
from app.schemas.goal import (
    GoalEstimateOut,
    GoalEstimateRequest,
    GoalOut,
    GoalUpdateRequest,
)
from app.services import goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post("/estimate", response_model=GoalEstimateOut)
def estimate(payload: GoalEstimateRequest) -> GoalEstimateOut:
    """只算不存：前端表单每次改动都可调它实时预览目标值。

    无需登录 —— 落地页也能用「算算我的目标」做引流。
    """
    plan = goal_service.estimate(payload)
    return GoalEstimateOut(
        bmr_kcal=float(plan.bmr_kcal),
        tdee_kcal=float(plan.tdee_kcal),
        target_kcal=int(plan.target_kcal),
        deficit_pct=float(plan.deficit_pct),
        protein_g=float(plan.macros.protein_g),
        fat_g=float(plan.macros.fat_g),
        carb_g=float(plan.macros.carb_g),
        fiber_g=float(plan.fiber_g),
        sodium_mg=float(plan.sodium_mg),
    )


@router.get("/current", response_model=GoalOut)
def get_current(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalOut:
    """获取当前生效的目标。尚未设置返回 404，前端据此跳引导页。"""
    goal = goal_service.current(db, current_user)
    if goal is None:
        raise not_found("goal_not_set", "尚未设置营养目标")
    return goal_service.to_out(goal)


@router.put("/current", response_model=GoalOut)
def update_current(
    payload: GoalUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GoalOut:
    """新建或更新目标。

    刻意只接受原始身体数据，不接受客户端算好的目标数值 ——
    否则前端可以随手提交 500 kcal，20% 缺口上限就形同虚设。
    """
    try:
        goal = goal_service.upsert(db, current_user, payload)
    except ValueError as exc:
        raise bad_request("invalid_goal_input", str(exc)) from exc
    return goal_service.to_out(goal)
