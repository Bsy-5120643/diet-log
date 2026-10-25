"""宏量营养素可空性测试（迁移 0006 / 0007）。

核心约定：**数据缺失不能阻止用户记录。**
食物缺某项营养 -> 换算结果为 None -> 写入 NULL -> 汇总按 0 计入 ->
通过 incomplete_fields 告诉前端显示「-」。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.services.nutrition import NutrientPer100g, scale, snapshot_of


def _make_food(db, name: str, *, protein=None, energy=Decimal("133.00")) -> Food:
    food = Food(
        name=name,
        energy_kcal=energy,
        protein_g=protein,
        fat_g=Decimal("5.00"),
        carb_g=Decimal("2.50"),
        fiber_g=Decimal("0.00"),
        sodium_mg=Decimal("34.40"),
        aliases=[],
        search_text=name.lower(),
        source="seed",
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


def _add_entry(db, user, food, quantity=Decimal("150")) -> FoodEntry:
    amounts = scale(snapshot_of(food), quantity)
    entry = FoodEntry(
        user_id=user.id,
        food_id=food.id,
        entry_date=datetime.date.today(),
        meal_type="lunch",
        quantity_g=quantity,
        snapshot_energy_kcal=food.energy_kcal,
        snapshot_protein_g=food.protein_g,
        snapshot_fat_g=food.fat_g,
        snapshot_carb_g=food.carb_g,
        snapshot_fiber_g=food.fiber_g,
        snapshot_sodium_mg=food.sodium_mg,
        energy_kcal=amounts.energy_kcal,
        protein_g=amounts.protein_g,
        fat_g=amounts.fat_g,
        carb_g=amounts.carb_g,
        fiber_g=amounts.fiber_g,
        sodium_mg=amounts.sodium_mg,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# nutrition.scale 对 None 的处理
# ---------------------------------------------------------------------------


def test_scale_keeps_none_as_none():
    """缺失项换算后仍是 None，绝不填 0。"""
    per_100g = NutrientPer100g(
        energy_kcal=Decimal("133.00"),
        protein_g=None,
        fat_g=Decimal("5.00"),
        carb_g=Decimal("2.50"),
        fiber_g=None,
        sodium_mg=Decimal("34.40"),
    )
    amounts = scale(per_100g, Decimal("150"))

    assert amounts.energy_kcal == Decimal("199.50")
    assert amounts.protein_g is None       # 缺失 -> None
    assert amounts.fiber_g is None         # 缺失 -> None
    assert amounts.fat_g == Decimal("7.50")
    assert amounts.sodium_mg == Decimal("51.60")


def test_scale_none_is_not_zero():
    """None 与 0 必须可区分 —— 这是整个设计的基石。"""
    with_protein = scale(
        NutrientPer100g(energy_kcal=Decimal("100"), protein_g=Decimal("0")),
        Decimal("100"),
    )
    without_protein = scale(
        NutrientPer100g(energy_kcal=Decimal("100"), protein_g=None),
        Decimal("100"),
    )

    assert with_protein.protein_g == Decimal("0")   # 真实 0
    assert without_protein.protein_g is None        # 未知


def test_snapshot_of_missing_food():
    food = Food(name="X", energy_kcal=Decimal("100"), protein_g=None)
    snap = snapshot_of(food)
    assert snap.energy_kcal == Decimal("100")
    assert snap.protein_g is None


# ---------------------------------------------------------------------------
# 写入：宏量为 NULL 也能记录
# ---------------------------------------------------------------------------


def test_can_log_food_with_missing_macro(db_session, test_user):
    """关键场景：吃了「蛋白质缺失」的食物，必须能记录成功。"""
    food = _make_food(db_session, "缺蛋白测试食物", protein=None)
    entry = _add_entry(db_session, test_user, food)

    assert entry.protein_g is None          # 存 NULL 而非 0
    assert entry.energy_kcal == Decimal("199.50")  # 热量照常算


def test_check_rejects_mismatched_null(db_session, test_user):
    """一致性约束：快照为 NULL 时计算值不能是数字。"""
    import sqlalchemy as sa

    food = _make_food(db_session, "不一致测试", protein=None)
    entry = FoodEntry(
        user_id=test_user.id,
        food_id=food.id,
        entry_date=datetime.date.today(),
        meal_type="lunch",
        quantity_g=Decimal("150"),
        snapshot_energy_kcal=food.energy_kcal,
        snapshot_protein_g=None,
        snapshot_fat_g=food.fat_g,
        snapshot_carb_g=food.carb_g,
        energy_kcal=Decimal("199.50"),
        protein_g=Decimal("10.00"),   # 快照 NULL 但计算值是数字 -> 应被拒
        fat_g=Decimal("7.50"),
        carb_g=Decimal("3.75"),
    )
    db_session.add(entry)
    with pytest.raises(sa.exc.IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_energy_still_required():
    """热量不可为 NULL —— 总热量不允许算不出来。"""
    assert FoodEntry.__table__.c.energy_kcal.nullable is False
    assert FoodEntry.__table__.c.snapshot_energy_kcal.nullable is False


def test_macro_columns_are_nullable():
    assert FoodEntry.__table__.c.protein_g.nullable is True
    assert FoodEntry.__table__.c.fat_g.nullable is True
    assert FoodEntry.__table__.c.carb_g.nullable is True
    assert Food.__table__.c.protein_g.nullable is True


# ---------------------------------------------------------------------------
# 汇总：incomplete_fields
# ---------------------------------------------------------------------------


def test_summary_reports_incomplete_fields(db_session, test_user):
    """汇总要告诉前端哪一项其实是缺失的，不能只给个 0。"""
    from app.services import summary_service

    food = _make_food(db_session, "汇总缺失测试", protein=None)
    _add_entry(db_session, test_user, food)

    summary = summary_service.daily_summary(
        db_session, test_user, datetime.date.today()
    )

    # 缺失项按 0 计入总量，总热量不受影响
    assert summary.consumed.energy_kcal == 199.5
    assert summary.consumed.protein_g == 0.0
    # 但明确标记为不完整，前端据此显示「-」
    assert "protein_g" in summary.incomplete_fields


def test_summary_no_incomplete_when_data_complete(db_session, test_user):
    from app.services import summary_service

    food = _make_food(db_session, "完整食物", protein=Decimal("19.40"))
    _add_entry(db_session, test_user, food)

    summary = summary_service.daily_summary(
        db_session, test_user, datetime.date.today()
    )
    assert summary.incomplete_fields == []
    assert summary.consumed.protein_g == 29.1
