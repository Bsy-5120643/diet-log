"""食物库检索接口。

GET /foods?q=关键词&page=1&size=20
    同时匹配 name 和 aliases，按相关度排序，带分页。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.food import FoodSearchOut
from app.services import food_service

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("", response_model=FoodSearchOut)
def search_foods(
    q: str = Query(default="", description="关键词，同时匹配名称与别名"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FoodSearchOut:
    """模糊搜索食物。

    q 为空时返回默认列表（按名称排序），避免前端首次进入一片空白。
    """
    items, total = food_service.search(
        db,
        q,
        page=page,
        size=size,
        user_id=current_user.id,
    )

    return FoodSearchOut(
        keyword=q,
        items=items,
        total=total,
        page=page,
        size=size,
        has_more=page * size < total,
    )
