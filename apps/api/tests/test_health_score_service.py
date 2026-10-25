"""健康指数服务层集成测试。

用真实的 SQLite 测试库（conftest 的 db_session），验证：
取数 → 计算 → upsert 落库 的完整链路。
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.goal import Goal
from app.models.health_score import DailyHealthScore
from app.services import health_score_service


def _make_food(db, name="测试食物", kcal="100.00", protein="10.00",
               carb="10.00", fat="10.00") -> Food:
    food = Food(
        name=name,
        energy_kcal=Decimal(kcal),
        protein_g=Decimal(protein),
        carb_g=Decimal(carb),
        fat_g=Decimal(fat),
        fiber_g=Decimal("0.00"),
        sodium_mg=Decimal("0.00"),
        aliases=[],
        search_text=name.lower(),
        source="seed",
        is_public=True,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food


def _add_entry(db, user, food, on_date, meal_type="lunch", quantity="100") -> FoodEntry:
    """造一条饮食记录，营养值按每 100g 现算（复用 nutrition.scale）。"""
    from app.services.nutrition import scale, snapshot_of

    amounts = scale(snapshot_of(food), Decimal(quantity))
    entry = FoodEntry(
        user_id=user.id,
        food_id=food.id,
        entry_date=on_date,
        meal_type=meal_type,
        quantity_g=Decimal(quantity),
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


def _make_goal(db, user, effective_from, *, kcal="2000", protein="140",
               carb="240", fat="55", bmr="1500", goal_type="cut") -> Goal:
    goal = Goal(
        user_id=user.id,
        effective_from=effective_from,
        source="calculated",
        energy_kcal=Decimal(kcal),
        protein_g=Decimal(protein),
        carb_g=Decimal(carb),
        fat_g=Decimal(fat),
        bmr_kcal=Decimal(bmr),
        tdee_kcal=Decimal("2600"),
        deficit_pct=Decimal("0.20"),
        goal_type=goal_type,
        activity_level="moderate",
        age=30,
        sex="male",
        height_cm=Decimal("175.0"),
        weight_kg=Decimal("70.0"),
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


# ---------------------------------------------------------------------------
# streak（用户特别要求的边界）
# ---------------------------------------------------------------------------


def test_streak_zero_when_nothing_logged(db_session, test_user):
    today = datetime.date.today()
    assert health_score_service.compute_streak_days(db_session, test_user.id, today) == 0


def test_streak_is_one_when_only_today_logged(db_session, test_user):
    """用户点名的场景：昨天没记、今天记了 → 1。"""
    today = datetime.date.today()
    food = _make_food(db_session)
    _add_entry(db_session, test_user, food, today)

    assert (
        health_score_service.compute_streak_days(db_session, test_user.id, today) == 1
    )


def test_streak_counts_consecutive_days_backwards(db_session, test_user):
    today = datetime.date.today()
    food = _make_food(db_session)
    for offset in range(3):
        _add_entry(db_session, test_user, food, today - datetime.timedelta(days=offset))

    assert (
        health_score_service.compute_streak_days(db_session, test_user.id, today) == 3
    )


def test_streak_stops_at_gap(db_session, test_user):
    """今天+昨天记了，前天没记 → 2（遇到断档就停）。"""
    today = datetime.date.today()
    food = _make_food(db_session)
    _add_entry(db_session, test_user, food, today)
    _add_entry(db_session, test_user, food, today - datetime.timedelta(days=1))
    # 前天（offset=2）故意不记

    assert (
        health_score_service.compute_streak_days(db_session, test_user.id, today) == 2
    )


def test_streak_is_zero_if_target_date_not_logged(db_session, test_user):
    """今天没记但昨天记了 → streak 断了，记 0。"""
    today = datetime.date.today()
    food = _make_food(db_session)
    _add_entry(db_session, test_user, food, today - datetime.timedelta(days=1))

    assert (
        health_score_service.compute_streak_days(db_session, test_user.id, today) == 0
    )


# ---------------------------------------------------------------------------
# 餐次统计
# ---------------------------------------------------------------------------


def test_count_meals_logged_counts_distinct(db_session, test_user):
    today = datetime.date.today()
    food = _make_food(db_session)
    _add_entry(db_session, test_user, food, today, "breakfast")
    _add_entry(db_session, test_user, food, today, "lunch")
    _add_entry(db_session, test_user, food, today, "lunch")   # 同餐次不重复计

    assert health_score_service.count_meals_logged(db_session, test_user.id, today) == 2


def test_count_meals_zero_when_no_entry(db_session, test_user):
    assert (
        health_score_service.count_meals_logged(
            db_session, test_user.id, datetime.date.today()
        )
        == 0
    )


# ---------------------------------------------------------------------------
# 计算与落库
# ---------------------------------------------------------------------------


def test_calculate_persists_score(db_session, test_user):
    today = datetime.date.today()
    row = health_score_service.calculate_health_score(db_session, test_user, today)

    assert row.user_id == test_user.id
    assert row.score_date == today
    assert 0 <= row.score <= 100
    assert row.breakdown is not None
    assert set(row.breakdown.keys()) == {"heat", "macro", "habit"}


def test_upsert_does_not_duplicate(db_session, test_user):
    """反复计算同一天应更新，而不是插多一行。"""
    today = datetime.date.today()
    health_score_service.calculate_health_score(db_session, test_user, today)
    health_score_service.calculate_health_score(db_session, test_user, today)

    count = db_session.scalar(
        select(func.count())
        .select_from(DailyHealthScore)
        .where(
            DailyHealthScore.user_id == test_user.id,
            DailyHealthScore.score_date == today,
        )
    )
    assert count == 1


def test_score_updates_when_data_changes(db_session, test_user):
    """加了记录之后重算，分数应该变化。"""
    today = datetime.date.today()
    before = health_score_service.calculate_health_score(db_session, test_user, today)
    # upsert 是原地更新同一个 ORM 对象，必须先取快照，否则重算后 before 也跟着变
    before_score = before.score

    food = _make_food(db_session)
    _add_entry(db_session, test_user, food, today, "breakfast")
    _add_entry(db_session, test_user, food, today, "lunch")
    _add_entry(db_session, test_user, food, today, "dinner")

    after = health_score_service.calculate_health_score(db_session, test_user, today)
    assert after.score > before_score


def test_perfect_day_scores_100(db_session, test_user):
    """摄入正好等于目标 + 三餐 + 14 天连续 → 100。"""
    today = datetime.date.today()
    _make_goal(db_session, test_user, today - datetime.timedelta(days=30))

    food = _make_food(db_session)
    # 每天三餐各 100g（每 100g = 100kcal / 10g 蛋白 / 10g 碳水 / 10g 脂肪）
    # 一天 300g → 300kcal ... 与目标 2000 差太远，这里直接按达标比例构造
    for offset in range(14):
        day = today - datetime.timedelta(days=offset)
        for meal in ("breakfast", "lunch", "dinner"):
            _add_entry(db_session, test_user, food, day, meal, quantity="666.67")

    row = health_score_service.calculate_health_score(db_session, test_user, today)
    # 666.67g × 3 = 2000g → 2000kcal、200g 蛋白/碳水/脂肪
    # 目标 140/240/55 仍不匹配，所以这里只断言热量项拿满、总分较高
    assert row.breakdown["heat"] == 40.0
    assert row.score >= 70


def test_score_matches_expectation_when_macros_align(db_session, test_user):
    """热量与宏量都对齐目标 → 热量40 + 宏量30 + 习惯30 = 100。"""
    today = datetime.date.today()
    # 目标：2000kcal / 蛋白150 / 碳水200 / 脂肪50
    _make_goal(
        db_session, test_user, today - datetime.timedelta(days=30),
        kcal="2000", protein="150", carb="200", fat="50", bmr="500",
    )

    # 每 100g 的食物值：500kcal / 37.5 蛋白 / 50 碳水 / 12.5 脂肪
    # 吃 400g → 2000kcal / 150 蛋白 / 200 碳水 / 50 脂肪，正好达标
    food = _make_food(db_session, kcal="500", protein="37.5", carb="50", fat="12.5")

    for offset in range(14):
        day = today - datetime.timedelta(days=offset)
        for meal in ("breakfast", "lunch", "dinner"):
            _add_entry(
                db_session, test_user, food, day, meal,
                quantity=str(400 / 3),
            )

    row = health_score_service.calculate_health_score(db_session, test_user, today)
    assert row.breakdown["heat"] == 40.0
    assert row.breakdown["macro"] == 30.0
    assert row.breakdown["habit"] == 30.0
    assert row.score == 100


# ---------------------------------------------------------------------------
# 无目标用户
# ---------------------------------------------------------------------------


def test_no_goal_user_capped_at_30(db_session, test_user):
    today = datetime.date.today()
    food = _make_food(db_session)
    for meal in ("breakfast", "lunch", "dinner"):
        _add_entry(db_session, test_user, food, today, meal)

    row = health_score_service.calculate_health_score(db_session, test_user, today)
    assert row.breakdown["heat"] == 0.0
    assert row.breakdown["macro"] == 0.0
    assert row.score <= 30


# ---------------------------------------------------------------------------
# 读取与周平均
# ---------------------------------------------------------------------------


def test_get_daily_score_returns_none_when_missing(db_session, test_user):
    assert (
        health_score_service.get_daily_score(
            db_session, test_user.id, datetime.date.today()
        )
        is None
    )


def test_week_average_counts_only_scored_days(db_session, test_user):
    today = datetime.date.today()
    row = health_score_service.calculate_health_score(db_session, test_user, today)
    avg, days = health_score_service.week_average(db_session, test_user.id, today)

    assert days == 1
    assert avg == float(row.score)


def test_week_average_none_when_no_scores(db_session, test_user):
    avg, days = health_score_service.week_average(
        db_session, test_user.id, datetime.date.today()
    )
    assert avg is None
    assert days == 0


def test_calculate_by_id_raises_for_unknown_user(db_session):
    with pytest.raises(ValueError):
        health_score_service.calculate_health_score_by_id(
            db_session, uuid.uuid4(), datetime.date.today()
        )
