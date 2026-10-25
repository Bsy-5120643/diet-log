"""食物库检索。

搜索走 foods.search_text 列（= lower(name + 所有别名)），
这样名称和别名一次 LIKE 就都能命中，且 PostgreSQL 上能走 pg_trgm GIN 索引。

为什么不直接查 aliases：SQLAlchemy 的 JSON 默认序列化会把中文转成 \\uXXXX，
在文本上做 LIKE 匹配不到字面中文（详见 0003 迁移的说明）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.models.food import Food
from app.schemas.food import FoodOut

DEFAULT_PAGE = 1
DEFAULT_SIZE = 20
MAX_SIZE = 50


def _visible_to(user_id: uuid.UUID | None):
    """公共食物 + 自己创建的食物。"""
    if user_id is None:
        return Food.is_public.is_(True)
    return or_(Food.is_public.is_(True), Food.created_by == user_id)


def _relevance(keyword: str):
    """相关度排序：完全匹配 > 名称前缀 > 名称/别名前缀 > 仅包含。"""
    return case(
        (func.lower(Food.name) == keyword, 0),
        (func.lower(Food.name).like(keyword + "%"), 1),
        (Food.search_text.like(keyword + "%"), 2),
        else_=3,
    )


def search(
    db: Session,
    keyword: str,
    *,
    page: int = DEFAULT_PAGE,
    size: int = DEFAULT_SIZE,
    user_id: uuid.UUID | None = None,
) -> tuple[list[FoodOut], int]:
    """模糊搜索食物，返回 (结果, 总条数)。"""
    keyword = (keyword or "").strip().lower()
    page = max(page, 1)
    size = min(max(size, 1), MAX_SIZE)

    base: Select = select(Food).where(
        Food.is_active.is_(True),
        _visible_to(user_id),
    )

    if keyword:
        base = base.where(Food.search_text.like(f"%{keyword}%"))
        base = base.order_by(_relevance(keyword), Food.name)
    else:
        # 无关键词时给出默认列表（按名称排序），避免前端一片空白
        base = base.order_by(Food.name)

    total = db.scalar(
        select(func.count()).select_from(base.order_by(None).subquery())
    ) or 0

    rows = list(
        db.scalars(base.offset((page - 1) * size).limit(size)).all()
    )

    items = [_to_out(food, keyword) for food in rows]
    return items, total


def _to_out(food: Food, keyword: str) -> FoodOut:
    """判断命中来源，便于前端提示「匹配到别名：西红柿」。"""
    match_on = "name"
    matched_alias: str | None = None

    if keyword:
        name_lower = (food.name or "").lower()
        if keyword not in name_lower:
            # 名称没命中，说明是别名命中的
            match_on = "alias"
            aliases = food.aliases or []
            for alias in aliases:
                if keyword in str(alias).lower():
                    matched_alias = str(alias)
                    break

    return FoodOut(
        id=food.id,
        name=food.name,
        brand=food.brand,
        energy_kcal=float(food.energy_kcal) if food.energy_kcal is not None else 0.0,
        protein_g=float(food.protein_g) if food.protein_g is not None else None,
        fat_g=float(food.fat_g) if food.fat_g is not None else None,
        carb_g=float(food.carb_g) if food.carb_g is not None else None,
        fiber_g=float(food.fiber_g) if food.fiber_g is not None else None,
        sodium_mg=float(food.sodium_mg) if food.sodium_mg is not None else None,
        match_on=match_on,
        matched_alias=matched_alias,
    )
