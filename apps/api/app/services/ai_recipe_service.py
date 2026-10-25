"""AI 识别的业务编排层。

把各层串起来：

    适配层 RawRecognition
      → 归一化菜品名
      → 查用户私有库（命中则覆盖 AI 估算 + 不扣配额）
      → 食材匹配 foods
      → 营养计算（明细累加）
      → 落临时菜品
      → 返回统一响应体

以及 confirm：把用户确认后的克数正式写入 recipes / recipe_ingredients / food_entries。

关于「缓存复用」的说明（SPEC + 第 4 轮决策 = 解法乙）：
缓存键是菜品名，而菜品名要调 AI 才知道，所以**每次拍照仍会调一次 AI**。
但拿到菜名后若私有库已有同名已确认菜品，就用库里的配比覆盖 AI 的估算
（用户改过的值更准），并且这次**不扣配额**。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import current_local_date, parse_iso_date
from app.models.enums import MEAL_TYPES
from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.recipe import Recipe, RecipeIngredient
from app.models.user import User
from app.schemas.ai import (
    ConfirmIn,
    ConfirmOut,
    QuotaOut,
    RecognizedIngredientOut,
    RecognitionCacheOut,
    RecognitionOut,
)
from app.services import ai_quota_service
from app.services.ai_recognizer import AIRecognizer, RawRecognition
from app.services.nutrition import scale, snapshot_of
from app.services.recipe_name import normalize_dish_name


class RecipeConflictError(Exception):
    """改名后与已有菜品同名冲突。"""


class UnmatchedIngredientError(Exception):
    """提交的请求里含未匹配食材（food_id 为空）。"""


class InvalidRequestError(Exception):
    """request_id 无效 / 过期 / 不属于当前用户。"""


# ---------------------------------------------------------------------------
# 食材匹配
# ---------------------------------------------------------------------------


def match_food(db: Session, ingredient_name: str) -> tuple[Food | None, str]:
    """把 AI 给的食材名匹配到 foods 表。

    返回 (food, matched_by)；匹配不到返回 (None, "unmatched")。
    matched_by: name / alias / unmatched
    """
    name = (ingredient_name or "").strip()
    if not name:
        return None, "unmatched"

    lower = name.lower()

    # 1. 名称精确匹配
    food = db.scalar(
        select(Food)
        .where(Food.is_active.is_(True), func.lower(Food.name) == lower)
        .order_by(Food.name)
        .limit(1)
    )
    if food is not None:
        return food, "name"

    # 2. 名称包含 / 别名包含（search_text = lower(name + aliases)）
    food = db.scalar(
        select(Food)
        .where(
            Food.is_active.is_(True),
            Food.is_public.is_(True),
            Food.search_text.like(f"%{lower}%"),
        )
        .order_by(Food.name)
        .limit(1)
    )
    if food is not None:
        # 判断到底命中名称还是别名
        return food, ("name" if lower in (food.name or "").lower() else "alias")

    return None, "unmatched"


def _to_ingredient_out(
    *,
    food: Food | None,
    display_name: str,
    quantity_g: Decimal,
    confidence: float | None,
    matched_by: str,
) -> RecognizedIngredientOut:
    """按克数换算营养。未匹配或食物缺数据时各项为 None（前端按 0 计入）。"""
    if food is None:
        return RecognizedIngredientOut(
            food_id=None,
            food_name=display_name,
            quantity_g=float(quantity_g),
            confidence=confidence,
            matched_by="unmatched",
        )

    amounts = scale(snapshot_of(food), quantity_g)
    return RecognizedIngredientOut(
        food_id=food.id,
        food_name=food.name,
        quantity_g=float(quantity_g),
        energy_kcal=float(amounts.energy_kcal),
        protein_g=None if amounts.protein_g is None else float(amounts.protein_g),
        fat_g=None if amounts.fat_g is None else float(amounts.fat_g),
        carb_g=None if amounts.carb_g is None else float(amounts.carb_g),
        fiber_g=None if amounts.fiber_g is None else float(amounts.fiber_g),
        sodium_mg=None if amounts.sodium_mg is None else float(amounts.sodium_mg),
        confidence=confidence,
        matched_by=matched_by,
    )


def _sum_energy(ingredients: list[RecognizedIngredientOut]) -> float:
    """总热量 = Σ 各项热量（SPEC §2.2：绝不采信 AI 直接给的总数）。"""
    total = Decimal("0")
    for item in ingredients:
        if item.energy_kcal is not None:
            total += Decimal(str(item.energy_kcal))
    return float(total)


# ---------------------------------------------------------------------------
# 私有库查询与写入
# ---------------------------------------------------------------------------


def _find_confirmed_recipe(
    db: Session, user: User, normalized_name: str
) -> Recipe | None:
    """查用户私有库里**已确认**的同名菜品。

    只认 is_temporary=false —— 未确认的临时结果不参与复用，
    否则 AI 认错后用户没确认，错误会被缓存下来反复复用。
    """
    if not normalized_name:
        return None
    return db.scalar(
        select(Recipe).where(
            Recipe.user_id == user.id,
            Recipe.normalized_name == normalized_name,
            Recipe.is_temporary.is_(False),
        )
    )


def _upsert_temp_recipe(
    db: Session,
    user: User,
    *,
    dish_name: str,
    normalized_name: str,
    ingredients: list[RecognizedIngredientOut],
) -> Recipe:
    """写入/覆盖临时菜品。同名已存在则覆盖，避免撞唯一索引。"""
    recipe = db.scalar(
        select(Recipe).where(
            Recipe.user_id == user.id,
            Recipe.normalized_name == normalized_name,
        )
    )

    is_new = recipe is None
    if is_new:
        recipe = Recipe(
            id=uuid.uuid4(),
            user_id=user.id,
            name=dish_name,
            normalized_name=normalized_name,
            source="ai",
            is_temporary=True,
            origin="user",
        )
        db.add(recipe)
        db.flush()

    # 覆盖明细
    for existing in list(recipe.ingredients):
        db.delete(existing)
    db.flush()

    order = 0
    for item in ingredients:
        if item.food_id is None:
            continue   # 未匹配食材不入库（后端不建占位数据，SPEC §8）
        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                food_id=item.food_id,
                quantity_g=Decimal(str(item.quantity_g)),
                display_order=order,
            )
        )
        order += 1

    recipe.name = dish_name
    recipe.total_energy_kcal = Decimal(str(_sum_energy(ingredients)))
    db.commit()
    db.refresh(recipe)
    return recipe


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


async def recognize(
    db: Session,
    user: User,
    recognizer: AIRecognizer,
    image: bytes | str,
    *,
    force: bool = False,
) -> RecognitionOut:
    """识别一张图片。

    :param force: True 则忽略私有库缓存，强制用 AI 结果（「重新识别」按钮）
    """
    # ① 调用前的三道闸（锁定 → 限流 → 配额），全部不产生费用
    ai_quota_service.ensure_allowed(db, user)

    # ② 调模型。网络/服务异常直接向上抛，不记账（失败不扣）
    raw: RawRecognition = await recognizer.recognize(image)

    # ③ 完全没认出 → 不扣配额，计入连续失败
    if raw.is_empty:
        ai_quota_service.record_empty(db, user)
        quota = ai_quota_service.get_quota(db, user)
        return RecognitionOut(
            request_id=uuid.uuid4(),   # 没有菜品可引用，给一个一次性 id
            dish_name="",
            normalized_name="",
            confidence=0.0,
            total_energy_kcal=0.0,
            ingredients=[],
            warnings=["未在图片中识别到食物"],
            cache=RecognitionCacheOut(hit=False, recipe_id=None, source="ai"),
            quota=QuotaOut(**quota),   # type: ignore[arg-type]
        )

    # ④ 归一化菜品名
    normalized = normalize_dish_name(raw.dish_name) or raw.dish_name.strip()

    # ⑤ 查私有库
    warnings: list[str] = []
    cache_hit = False
    confirmed = None if force else _find_confirmed_recipe(db, user, normalized)

    if confirmed is not None:
        # 命中：用私有库配比覆盖 AI 估算（用户改过的值更准），且本次不扣配额
        cache_hit = True
        ingredients: list[RecognizedIngredientOut] = []
        for ri in confirmed.ingredients:
            ingredients.append(
                _to_ingredient_out(
                    food=ri.food,
                    display_name=ri.food.name if ri.food else "",
                    quantity_g=ri.quantity_g,
                    confidence=None,
                    matched_by="user_recipe",
                )
            )
        recipe_id: uuid.UUID = confirmed.id
        dish_name = confirmed.name
        source = "user_recipe"
    else:
        # 未命中：用 AI 结果，扣 1 次配额
        ingredients = []
        for raw_item in raw.ingredients:
            food, matched_by = match_food(db, raw_item.name)
            if food is None:
                warnings.append(f"存在未匹配食材: {raw_item.name}")
            ingredients.append(
                _to_ingredient_out(
                    food=food,
                    display_name=raw_item.name,
                    quantity_g=raw_item.quantity_g,
                    confidence=raw_item.confidence,
                    matched_by=matched_by,
                )
            )

        ai_quota_service.record_success(db, user)
        recipe = _upsert_temp_recipe(
            db,
            user,
            dish_name=raw.dish_name,
            normalized_name=normalized,
            ingredients=ingredients,
        )
        recipe_id = recipe.id
        dish_name = raw.dish_name
        source = "ai"

    # ⑥ 置信度提示
    if raw.confidence < 0.7:
        warnings.append(f"AI 置信度较低（{raw.confidence:.2f}），请核对")

    quota = ai_quota_service.get_quota(db, user)

    return RecognitionOut(
        request_id=recipe_id,
        dish_name=dish_name,
        normalized_name=normalized,
        confidence=raw.confidence,
        total_energy_kcal=_sum_energy(ingredients),
        ingredients=ingredients,
        warnings=warnings,
        cache=RecognitionCacheOut(hit=cache_hit, recipe_id=recipe_id, source=source),
        quota=QuotaOut(**quota),   # type: ignore[arg-type]
    )


def confirm(db: Session, user: User, payload: ConfirmIn) -> ConfirmOut:
    """确认并正式写入。

    - 覆盖 recipe_ingredients 为用户最终克数
    - 菜品转正（is_temporary = False）
    - 创建 food_entries（带 recipe_id + entry_group_id）
    """
    recipe = db.get(Recipe, payload.request_id)
    if recipe is None or recipe.user_id != user.id:
        raise InvalidRequestError("识别请求不存在或已过期")

    # ① 落库阶段必须干净：不允许 food_id 为空
    if any(item.food_id is None for item in payload.ingredients):
        raise UnmatchedIngredientError("存在未匹配食材，请先删除或替换")

    # ② 改名冲突检查
    new_normalized = normalize_dish_name(payload.dish_name)
    conflict = db.scalar(
        select(Recipe).where(
            Recipe.user_id == user.id,
            Recipe.normalized_name == new_normalized,
            Recipe.id != recipe.id,
        )
    )
    if conflict is not None:
        raise RecipeConflictError("已存在同名菜品")

    # ③ 覆盖明细
    for existing in list(recipe.ingredients):
        db.delete(existing)
    db.flush()

    entry_date = (
        parse_iso_date(payload.entry_date)
        if payload.entry_date
        else current_local_date(user.timezone)
    )
    if payload.meal_type not in MEAL_TYPES:
        raise InvalidRequestError("餐次不合法")

    group_id = uuid.uuid4()
    total = Decimal("0")
    created = 0

    for order, item in enumerate(payload.ingredients):
        food = db.get(Food, item.food_id)
        if food is None or not food.is_active:
            raise UnmatchedIngredientError("食材不存在或已下架")

        db.add(
            RecipeIngredient(
                recipe_id=recipe.id,
                food_id=food.id,
                quantity_g=item.quantity_g,
                display_order=order,
            )
        )

        if not payload.save_as_recipe:
            continue

        amounts = scale(snapshot_of(food), item.quantity_g)
        snapshot = snapshot_of(food)
        db.add(
            FoodEntry(
                id=uuid.uuid4(),
                user_id=user.id,
                food_id=food.id,
                entry_date=entry_date,
                meal_type=payload.meal_type,
                quantity_g=item.quantity_g,
                snapshot_energy_kcal=snapshot.energy_kcal,
                snapshot_protein_g=snapshot.protein_g,
                snapshot_fat_g=snapshot.fat_g,
                snapshot_carb_g=snapshot.carb_g,
                snapshot_fiber_g=snapshot.fiber_g,
                snapshot_sodium_mg=snapshot.sodium_mg,
                energy_kcal=amounts.energy_kcal,
                protein_g=amounts.protein_g,
                fat_g=amounts.fat_g,
                carb_g=amounts.carb_g,
                fiber_g=amounts.fiber_g,
                sodium_mg=amounts.sodium_mg,
                recipe_id=recipe.id,
                entry_group_id=group_id,
            )
        )
        total += amounts.energy_kcal
        created += 1

    # ④ 转正
    recipe.name = payload.dish_name
    recipe.normalized_name = new_normalized
    recipe.is_temporary = False
    recipe.total_energy_kcal = total

    db.commit()
    db.refresh(recipe)

    return ConfirmOut(
        entry_group_id=group_id,
        recipe_id=recipe.id,
        total_energy_kcal=float(total),
        created_entries=created,
    )
