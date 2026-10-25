"""健康指数与排行榜 API 集成测试。

重点验证：
- 资格过滤（近 7 天 < 3 天不进榜）
- 目标过滤（?goal=减脂 只出减脂用户）
- 聚合排序正确
- **脱敏**：响应里绝不出现体重 / 热量 / 宏量
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import security
from app.db.session import get_db
from app.main import app
from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.goal import Goal
from app.models.user import User
from app.services.nutrition import scale, snapshot_of

BASE = "/api/v1"

#: 敏感字段，绝不能出现在排行榜响应里
FORBIDDEN_KEYS = {
    "weight_kg", "height_cm", "energy_kcal", "kcal", "protein_g",
    "fat_g", "carb_g", "bmr_kcal", "tdee_kcal", "target_kcal", "email",
}


@pytest.fixture()
def client(db_session: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _user(db: Session, email: str, nickname: str | None = None) -> User:
    u = User(
        email=email,
        password_hash=security.hash_password("Password123"),
        nickname=nickname,
        timezone="Asia/Shanghai",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _headers(client: TestClient, user: User, password="Password123") -> dict[str, str]:
    resp = client.post(
        f"{BASE}/auth/login", json={"email": user.email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


def _food(db: Session, name: str, kcal: str, protein: str, carb: str, fat: str) -> Food:
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


def _log(db: Session, user: User, food: Food, day: datetime.date, meal: str, grams: str) -> None:
    amounts = scale(snapshot_of(food), Decimal(grams))
    db.add(
        FoodEntry(
            user_id=user.id,
            food_id=food.id,
            entry_date=day,
            meal_type=meal,
            quantity_g=Decimal(grams),
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
        )
    )
    db.commit()


def _goal(db: Session, user: User, goal_type: str, kcal="2000", protein="150",
          carb="200", fat="50", bmr="500") -> Goal:
    g = Goal(
        user_id=user.id,
        effective_from=datetime.date.today() - datetime.timedelta(days=60),
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
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# ---------------------------------------------------------------------------
# /health-score
# ---------------------------------------------------------------------------


def test_health_score_requires_auth(client):
    assert client.get(f"{BASE}/health-score").status_code == 401


def test_health_score_returns_breakdown(client, db_session):
    user = _user(db_session, "hs@example.com", nickname="测试")
    headers = _headers(client, user)

    resp = client.get(f"{BASE}/health-score", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert 0 <= body["score"] <= 100
    assert set(body["breakdown"].keys()) == {"heat", "macro", "habit"}
    assert body["has_goal"] is False          # 没设目标
    assert body["level"] in {"excellent", "good", "fair", "poor"}
    assert body["meals_logged"] == 0
    assert body["streak_days"] == 0
    # 端点会先算当天分数并落库，再读周均分 —— 所以均分天然包含今天
    assert body["scored_days"] == 1
    assert body["week_avg"] == float(body["score"])


def test_health_score_reports_goal_and_meals(client, db_session):
    user = _user(db_session, "hs2@example.com")
    _goal(db_session, user, "cut")
    food = _food(db_session, "F", "500", "37.5", "50", "12.5")
    today = datetime.date.today()
    for meal in ("breakfast", "lunch", "dinner"):
        _log(db_session, user, food, today, meal, "133.33")

    resp = client.get(f"{BASE}/health-score", headers=_headers(client, user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["has_goal"] is True
    assert body["meals_logged"] == 3
    assert body["streak_days"] == 1
    assert body["week_avg"] is not None


def test_health_score_accepts_date_param(client, db_session):
    user = _user(db_session, "hs3@example.com")
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    resp = client.get(
        f"{BASE}/health-score?date={yesterday}", headers=_headers(client, user)
    )
    assert resp.status_code == 200
    assert resp.json()["date"] == yesterday


def test_health_score_rejects_bad_date(client, db_session):
    user = _user(db_session, "hs4@example.com")
    resp = client.get(
        f"{BASE}/health-score?date=2026-13-99", headers=_headers(client, user)
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /leaderboard 资格过滤
# ---------------------------------------------------------------------------


def test_user_with_fewer_than_three_days_is_excluded(client, db_session):
    """近 7 天只记 2 天 → 不进榜，me.qualified = False。"""
    user = _user(db_session, "lb1@example.com", nickname="两天用户")
    _goal(db_session, user, "cut")
    food = _food(db_session, "F", "500", "37.5", "50", "12.5")
    today = datetime.date.today()
    # 只记 2 天，且分数会很高
    for offset in range(2):
        for meal in ("breakfast", "lunch", "dinner"):
            _log(db_session, user, food, today - datetime.timedelta(days=offset), meal, "133.33")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, user))
    assert resp.status_code == 200
    body = resp.json()

    assert body["items"] == []                 # 没人进榜
    assert body["me"]["qualified"] is False
    assert body["me"]["rank"] is None
    assert body["me"]["logged_days"] == 2


def test_user_with_three_days_qualifies(client, db_session):
    """记满 3 天 → 进榜。"""
    user = _user(db_session, "lb2@example.com", nickname="三天用户")
    _goal(db_session, user, "cut")
    food = _food(db_session, "F", "500", "37.5", "50", "12.5")
    today = datetime.date.today()
    for offset in range(3):
        for meal in ("breakfast", "lunch", "dinner"):
            _log(db_session, user, food, today - datetime.timedelta(days=offset), meal, "133.33")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, user))
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["nickname"] == "三天用户"
    assert body["me"]["qualified"] is True
    assert body["me"]["rank"] == 1


# ---------------------------------------------------------------------------
# 目标过滤
# ---------------------------------------------------------------------------


def _build_user(db, email, nickname, goal_type, *, days=3, grams="133.33"):
    user = _user(db, email, nickname=nickname)
    _goal(db, user, goal_type)
    food = db.scalar(select_food(db))
    today = datetime.date.today()
    for offset in range(days):
        for meal in ("breakfast", "lunch", "dinner"):
            _log(db, user, food, today - datetime.timedelta(days=offset), meal, grams)
    return user


def select_food(db):
    from sqlalchemy import select

    return select(Food).where(Food.name == "F")


def test_goal_filter_shows_only_matching_users(client, db_session):
    """?goal=减脂 只出减脂用户；增肌用户被排除。"""
    food = _food(db_session, "F", "500", "37.5", "50", "12.5")
    cut_user = _build_user(db_session, "cut1@example.com", "减脂A", "cut")
    gain_user = _build_user(db_session, "gain1@example.com", "增肌B", "gain")

    resp = client.get(
        f"{BASE}/leaderboard?goal=减脂", headers=_headers(client, cut_user)
    )
    assert resp.status_code == 200
    body = resp.json()

    nicknames = [i["nickname"] for i in body["items"]]
    assert "减脂A" in nicknames
    assert "增肌B" not in nicknames
    assert body["goal"] == "cut"


def test_goal_filter_accepts_enum_value(client, db_session):
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    gain_user = _build_user(db_session, "gain2@example.com", "增肌C", "gain")

    resp = client.get(
        f"{BASE}/leaderboard?goal=gain", headers=_headers(client, gain_user)
    )
    assert resp.status_code == 200
    assert resp.json()["goal"] == "gain"
    assert len(resp.json()["items"]) == 1


def test_unknown_goal_is_ignored(client, db_session):
    """无法识别的 goal 值不过滤，而不是返回空榜。"""
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    user = _build_user(db_session, "u@example.com", "某人", "cut")

    resp = client.get(
        f"{BASE}/leaderboard?goal=乱写的", headers=_headers(client, user)
    )
    assert resp.status_code == 200
    assert resp.json()["goal"] is None
    assert len(resp.json()["items"]) == 1


# ---------------------------------------------------------------------------
# 排序
# ---------------------------------------------------------------------------


def test_leaderboard_is_sorted_by_avg_score_desc(client, db_session):
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    # 高分用户：吃得更接近目标
    high = _user(db_session, "high@example.com", nickname="高分")
    _goal(db_session, high, "cut")
    # 低分用户：随便吃
    low = _user(db_session, "low@example.com", nickname="低分")
    _goal(db_session, low, "cut")

    today = datetime.date.today()
    for offset in range(4):
        day = today - datetime.timedelta(days=offset)
        for meal in ("breakfast", "lunch", "dinner"):
            _log(db_session, high, db_session.scalar(select_food(db_session)), day, meal, "133.33")
            _log(db_session, low, db_session.scalar(select_food(db_session)), day, meal, "10")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, high))
    body = resp.json()

    assert len(body["items"]) == 2
    scores = [i["avg_score"] for i in body["items"]]
    assert scores == sorted(scores, reverse=True)
    assert body["items"][0]["nickname"] == "高分"
    assert body["items"][0]["rank"] == 1


def test_limit_caps_results(client, db_session):
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    for i in range(5):
        _build_user(db_session, f"u{i}@example.com", f"用户{i}", "cut")

    viewer = db_session.scalar(
        __import__("sqlalchemy").select(User).where(User.email == "u0@example.com")
    )
    resp = client.get(
        f"{BASE}/leaderboard?limit=2", headers=_headers(client, viewer)
    )
    assert len(resp.json()["items"]) == 2


# ---------------------------------------------------------------------------
# 脱敏（最重要）
# ---------------------------------------------------------------------------


def test_leaderboard_contains_no_sensitive_data(client, db_session):
    """响应里绝不能出现体重、热量、宏量等字段。"""
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    user = _build_user(db_session, "priv@example.com", "隐私用户", "cut")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, user))
    assert resp.status_code == 200
    body = resp.json()

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in FORBIDDEN_KEYS, f"泄露敏感字段: {key}"
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)

    # 每一行只应有这四个字段
    for item in body["items"]:
        assert set(item.keys()) == {"rank", "nickname", "avatar_url", "avg_score"}


def test_nickname_falls_back_for_anonymous(client, db_session):
    """未设昵称的用户显示「匿名用户」，不暴露邮箱。"""
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    user = _build_user(db_session, "anon@example.com", None, "cut")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, user))
    body = resp.json()
    assert body["items"][0]["nickname"] == "匿名用户"
    assert "anon@example.com" not in resp.text


def test_me_uses_own_rank(client, db_session):
    """me 反映当前用户自己的排名。"""
    _food(db_session, "F", "500", "37.5", "50", "12.5")
    first = _build_user(db_session, "first@example.com", "第一", "cut")
    second = _build_user(db_session, "second@example.com", "第二", "cut")

    resp = client.get(f"{BASE}/leaderboard", headers=_headers(client, second))
    body = resp.json()

    assert body["me"]["rank"] in (1, 2)
    assert body["me"]["qualified"] is True
    assert body["me"]["avg_score"] is not None
