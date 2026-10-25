"""看板接口端到端测试。

覆盖 /summary、/summary/range、/weight-logs 的空态与累加行为。
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import security
from app.models.enums import ActivityLevel, GoalType, MealType, Sex
from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.goal import Goal
from app.models.user import User
from app.services.nutrition import scale, snapshot_of

BASE = "/api/v1"


def _auth_headers(client, email: str, password: str = "Password123") -> dict[str, str]:
    resp = client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


def _make_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        password_hash=security.hash_password("Password123"),
        timezone="Asia/Shanghai",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_goal(db: Session, user: User, on_date: datetime.date) -> Goal:
    goal = Goal(
        user_id=user.id,
        effective_from=on_date,
        source="calculated",
        energy_kcal=Decimal("2044"),
        protein_g=Decimal("140.0"),
        fat_g=Decimal("56.8"),
        carb_g=Decimal("243.2"),
        goal_type=GoalType.CUT.value,
        activity_level=ActivityLevel.MODERATE.value,
        age=30,
        sex=Sex.MALE.value,
        height_cm=Decimal("175.0"),
        weight_kg=Decimal("70.0"),
        bmr_kcal=Decimal("1648.8"),
        tdee_kcal=Decimal("2555.6"),
        deficit_pct=Decimal("0.200"),
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def _add_entry(
    db: Session,
    user: User,
    food: Food,
    on_date: datetime.date,
    quantity_g: Decimal,
    meal_type: MealType = MealType.LUNCH,
) -> FoodEntry:
    """模拟「添加一条饮食记录」—— 计算全部走 services.nutrition。"""
    amounts = scale(snapshot_of(food), quantity_g)
    entry = FoodEntry(
        user_id=user.id,
        food_id=food.id,
        entry_date=on_date,
        meal_type=meal_type.value,
        quantity_g=quantity_g,
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


def test_summary_returns_200_with_zero_when_no_entries(client, db_session):
    """没有任何记录时，/summary 必须返回 200 且 consumed 全 0，不能报错。"""
    user = _make_user(db_session, "empty@example.com")
    headers = _auth_headers(client, user.email)

    resp = client.get(f"{BASE}/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["entry_count"] == 0
    assert body["consumed"]["energy_kcal"] == 0
    assert body["consumed"]["protein_g"] == 0


def test_summary_no_goal_targets_is_null(client, db_session):
    """未设置目标时 targets / remaining / percent 为 null，前端据此走引导。"""
    user = _make_user(db_session, "nogoal@example.com")
    headers = _auth_headers(client, user.email)

    resp = client.get(f"{BASE}/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["targets"] is None
    assert body["remaining"] is None
    assert body["percent"] is None


def test_summary_reflects_added_entry(client, db_session):
    """核心验收：加 150g 鸡胸肉到午餐 → 热量 199.5 / 蛋白 29.1"""
    user = _make_user(db_session, "chicken@example.com")
    today = datetime.date.today()

    food = Food(
        name="鸡胸肉",
        energy_kcal=Decimal("133.00"),
        protein_g=Decimal("19.40"),
        fat_g=Decimal("5.00"),
        carb_g=Decimal("2.50"),
        fiber_g=Decimal("0.00"),
        sodium_mg=Decimal("34.40"),
        aliases=["鸡胸", "鸡脯肉", "鸡柳"],
        source="seed",
        is_public=True,
    )
    db_session.add(food)
    db_session.commit()
    _make_goal(db_session, user, today)

    _add_entry(db_session, user, food, today, Decimal("150"), MealType.LUNCH)

    headers = _auth_headers(client, user.email)
    resp = client.get(f"{BASE}/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["entry_count"] == 1
    assert body["consumed"]["energy_kcal"] == 199.5
    assert body["consumed"]["protein_g"] == 29.1
    assert body["consumed"]["fat_g"] == 7.5
    assert body["consumed"]["carb_g"] == 3.75


def test_summary_accumulates_two_entries(client, db_session):
    """再加一份 150g → 热量累计 399.0，验证是累加而非覆盖。"""
    user = _make_user(db_session, "chicken2@example.com")
    today = datetime.date.today()

    food = Food(
        name="鸡胸肉",
        energy_kcal=Decimal("133.00"),
        protein_g=Decimal("19.40"),
        fat_g=Decimal("5.00"),
        carb_g=Decimal("2.50"),
        fiber_g=Decimal("0.00"),
        sodium_mg=Decimal("34.40"),
        source="seed",
        is_public=True,
    )
    db_session.add(food)
    db_session.commit()
    _make_goal(db_session, user, today)

    _add_entry(db_session, user, food, today, Decimal("150"), MealType.LUNCH)
    _add_entry(db_session, user, food, today, Decimal("150"), MealType.LUNCH)

    headers = _auth_headers(client, user.email)
    resp = client.get(f"{BASE}/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["entry_count"] == 2
    assert body["consumed"]["energy_kcal"] == 399.0
    assert body["consumed"]["protein_g"] == 58.2


def test_summary_by_meal_groups_correctly(client, db_session):
    """按餐次分组统计。"""
    user = _make_user(db_session, "meal@example.com")
    today = datetime.date.today()

    food = Food(
        name="鸡蛋",
        energy_kcal=Decimal("144.00"),
        protein_g=Decimal("13.30"),
        fat_g=Decimal("8.80"),
        carb_g=Decimal("2.80"),
        fiber_g=Decimal("0.00"),
        sodium_mg=Decimal("131.50"),
        source="seed",
        is_public=True,
    )
    db_session.add(food)
    db_session.commit()
    _make_goal(db_session, user, today)

    _add_entry(db_session, user, food, today, Decimal("100"), MealType.BREAKFAST)
    _add_entry(db_session, user, food, today, Decimal("50"), MealType.LATE_NIGHT)

    headers = _auth_headers(client, user.email)
    resp = client.get(f"{BASE}/summary", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["by_meal"]["breakfast"]["entry_count"] == 1
    assert body["by_meal"]["breakfast"]["energy_kcal"] == 144.0
    assert body["by_meal"]["late_night"]["entry_count"] == 1
    assert body["by_meal"]["late_night"]["energy_kcal"] == 72.0
    assert body["by_meal"]["lunch"]["entry_count"] == 0


def test_summary_range_fills_missing_days(client, db_session):
    """区间接口必须补齐所有日期，缺的天为 0。"""
    user = _make_user(db_session, "range@example.com")
    today = datetime.date.today()
    _make_goal(db_session, user, today)

    from_date = today - datetime.timedelta(days=6)
    query = {"from": from_date.isoformat(), "to": today.isoformat()}

    resp = client.get(f"{BASE}/summary/range", params=query, headers=_auth_headers(client, user.email))
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert len(body["days"]) == 7
    assert [d["date"] for d in body["days"]] == [
        (from_date + datetime.timedelta(days=i)).isoformat() for i in range(7)
    ]
    assert all(d["energy_kcal"] == 0 for d in body["days"])
