"""食物搜索 + 添加记录 的端到端测试。

锁定验收标准：
    搜「鸡胸肉」→ 添加 150g 到午餐 → 汇总里热量 +199.5、蛋白质 +29.1
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core import security
from app.models.food import Food
from app.models.food_entry import FoodEntry
from app.models.user import User

BASE = "/api/v1"


@pytest.fixture()
def user(db_session) -> User:
    u = User(
        email="loop@example.com",
        password_hash=security.hash_password("Password123"),
        timezone="Asia/Shanghai",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def headers(client, user) -> dict[str, str]:
    resp = client.post(
        f"{BASE}/auth/login", json={"email": user.email, "password": "Password123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}


def _food(db, name, *, kcal=Decimal("133.00"), protein=Decimal("19.40"),
          fat=Decimal("5.00"), carb=Decimal("2.50"), aliases=None, public=True):
    f = Food(
        name=name,
        energy_kcal=kcal, protein_g=protein, fat_g=fat, carb_g=carb,
        fiber_g=Decimal("0.00"), sodium_mg=Decimal("34.40"),
        aliases=aliases or [],
        search_text=(name + " " + " ".join(aliases or [])).lower(),
        source="seed", is_public=public,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------


def test_search_by_name(client, db_session, user, headers):
    _food(db_session, "鸡胸肉", aliases=["鸡胸", "鸡脯肉"])
    _food(db_session, "西兰花")

    resp = client.get(f"{BASE}/foods?q=鸡胸", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "鸡胸肉"


def test_search_by_alias(client, db_session, user, headers):
    """搜「西红柿」必须命中「番茄」—— 别名的价值所在。"""
    _food(db_session, "番茄", aliases=["西红柿", "圣女果"])

    resp = client.get(f"{BASE}/foods?q=西红柿", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["name"] == "番茄"
    assert item["match_on"] == "alias"
    assert item["matched_alias"] == "西红柿"


def test_search_relevance_exact_first(client, db_session, user, headers):
    """完全匹配应排在包含匹配之前。"""
    _food(db_session, "鸡蛋面")
    _food(db_session, "鸡蛋")

    resp = client.get(f"{BASE}/foods?q=鸡蛋", headers=headers)
    assert resp.status_code == 200, resp.text

    names = [i["name"] for i in resp.json()["items"]]
    assert names[0] == "鸡蛋"


def test_search_miss_returns_empty(client, db_session, user, headers):
    resp = client.get(f"{BASE}/foods?q=不存在的食物xyz", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_search_pagination(client, db_session, user, headers):
    for i in range(25):
        _food(db_session, f"测试食物{i:02d}")

    first = client.get(f"{BASE}/foods?page=1&size=10", headers=headers).json()
    second = client.get(f"{BASE}/foods?page=2&size=10", headers=headers).json()

    assert first["total"] == 25
    assert len(first["items"]) == 10
    assert first["has_more"] is True
    assert len(second["items"]) == 10
    assert second["page"] == 2
    # 两页不应有交集
    a = {i["id"] for i in first["items"]}
    b = {i["id"] for i in second["items"]}
    assert a & b == set()


def test_search_requires_auth(client, db_session):
    assert client.get(f"{BASE}/foods?q=鸡").status_code == 401


def test_search_hides_inactive(client, db_session, user, headers):
    """软删除的食物不应出现在搜索结果里。"""
    f = _food(db_session, "已下架食物")
    f.is_active = False
    db_session.commit()

    resp = client.get(f"{BASE}/foods?q=已下架", headers=headers)
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# 添加记录
# ---------------------------------------------------------------------------


def test_create_entry_computes_amounts(client, db_session, user, headers):
    """核心验收：150g 鸡胸肉 → 199.5 kcal / 29.1 g 蛋白。"""
    food = _food(db_session, "鸡胸肉")

    resp = client.post(
        f"{BASE}/food-entries",
        json={
            "food_id": str(food.id),
            "meal_type": "lunch",
            "quantity_g": 150,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["energy_kcal"] == 199.5
    assert body["protein_g"] == 29.1
    assert body["fat_g"] == 7.5
    assert body["carb_g"] == 3.75
    assert body["meal_label"] == "午餐"
    assert body["per_100g"]["energy_kcal"] == 133.0


def test_create_entry_snapshots_values(client, db_session, user, headers):
    """快照必须固化：事后改食物库，历史记录不能跟着变。"""
    food = _food(db_session, "快照测试")

    resp = client.post(
        f"{BASE}/food-entries",
        json={"food_id": str(food.id), "meal_type": "dinner", "quantity_g": 100},
        headers=headers,
    )
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    # 事后把食物的热量改掉
    food.energy_kcal = Decimal("999.00")
    db_session.commit()

    again = client.get(
        f"{BASE}/food-entries?date={datetime.date.today().isoformat()}",
        headers=headers,
    ).json()
    item = next(i for i in again["items"] if i["id"] == entry_id)
    assert item["energy_kcal"] == 133.0          # 仍是记录时的值
    assert item["per_100g"]["energy_kcal"] == 133.0


def test_create_entry_missing_macro_allowed(client, db_session, user, headers):
    """蛋白质缺失的食物也能记录 —— 数据缺失不阻止用户。"""
    food = _food(db_session, "缺蛋白食物", protein=None)

    resp = client.post(
        f"{BASE}/food-entries",
        json={"food_id": str(food.id), "meal_type": "snack", "quantity_g": 100},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["protein_g"] is None             # NULL 而非 0
    assert body["energy_kcal"] == 133.0          # 热量照常算


def test_create_entry_rejects_bad_quantity(client, db_session, user, headers):
    food = _food(db_session, "分量测试")
    for bad in (0, -10, 99999):
        resp = client.post(
            f"{BASE}/food-entries",
            json={
                "food_id": str(food.id), "meal_type": "lunch", "quantity_g": bad
            },
            headers=headers,
        )
        assert resp.status_code == 422, f"{bad} 应被拒"


def test_create_entry_rejects_unknown_food(client, db_session, user, headers):
    resp = client.post(
        f"{BASE}/food-entries",
        json={
            "food_id": str(uuid.uuid4()),
            "meal_type": "lunch",
            "quantity_g": 100,
        },
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "food_not_found"


def test_create_entry_rejects_bad_meal_type(client, db_session, user, headers):
    food = _food(db_session, "餐次测试")
    resp = client.post(
        f"{BASE}/food-entries",
        json={
            "food_id": str(food.id), "meal_type": "brunch", "quantity_g": 100
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_create_entry_accepts_late_night(client, db_session, user, headers):
    """夜宵是第 5 档餐次，必须能存。"""
    food = _food(db_session, "夜宵测试")
    resp = client.post(
        f"{BASE}/food-entries",
        json={
            "food_id": str(food.id), "meal_type": "late_night", "quantity_g": 100
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["meal_label"] == "夜宵"


# ---------------------------------------------------------------------------
# 闭环：添加后汇总立即正确
# ---------------------------------------------------------------------------


def test_full_loop(client, db_session, user, headers):
    """搜索 → 添加 → 汇总，三步闭环。"""
    _food(db_session, "鸡胸肉", aliases=["鸡胸"])

    # 1. 搜索
    found = client.get(f"{BASE}/foods?q=鸡胸肉", headers=headers).json()
    food_id = found["items"][0]["id"]

    # 2. 添加 150g 到午餐
    created = client.post(
        f"{BASE}/food-entries",
        json={"food_id": food_id, "meal_type": "lunch", "quantity_g": 150},
        headers=headers,
    )
    assert created.status_code == 201

    # 3. 汇总
    summary = client.get(f"{BASE}/summary", headers=headers).json()
    assert summary["entry_count"] == 1
    assert summary["consumed"]["energy_kcal"] == 199.5
    assert summary["consumed"]["protein_g"] == 29.1
    assert summary["by_meal"]["lunch"]["entry_count"] == 1


def test_summary_accumulates(client, db_session, user, headers):
    """再加一份，总量翻倍。"""
    food = _food(db_session, "累加测试")
    for _ in range(2):
        client.post(
            f"{BASE}/food-entries",
            json={"food_id": str(food.id), "meal_type": "lunch", "quantity_g": 150},
            headers=headers,
        )

    summary = client.get(f"{BASE}/summary", headers=headers).json()
    assert summary["entry_count"] == 2
    assert summary["consumed"]["energy_kcal"] == 399.0
    assert summary["consumed"]["protein_g"] == 58.2


def test_delete_entry(client, db_session, user, headers):
    food = _food(db_session, "待删除食物")
    created = client.post(
        f"{BASE}/food-entries",
        json={"food_id": str(food.id), "meal_type": "lunch", "quantity_g": 100},
        headers=headers,
    ).json()

    resp = client.delete(f"{BASE}/food-entries/{created['id']}", headers=headers)
    assert resp.status_code == 204

    summary = client.get(f"{BASE}/summary", headers=headers).json()
    assert summary["entry_count"] == 0


def test_cannot_delete_others_entry(client, db_session, user, headers):
    from app.models.user import User as U

    other = U(email="other@example.com",
              password_hash=security.hash_password("Password123"),
              timezone="Asia/Shanghai")
    db_session.add(other)
    db_session.commit()

    food = _food(db_session, "别人的食物")
    entry = FoodEntry(
        user_id=other.id, food_id=food.id,
        entry_date=datetime.date.today(), meal_type="lunch",
        quantity_g=Decimal("100"),
        snapshot_energy_kcal=Decimal("133.00"), snapshot_protein_g=Decimal("19.40"),
        snapshot_fat_g=Decimal("5.00"), snapshot_carb_g=Decimal("2.50"),
        energy_kcal=Decimal("133.00"), protein_g=Decimal("19.40"),
        fat_g=Decimal("5.00"), carb_g=Decimal("2.50"),
    )
    db_session.add(entry)
    db_session.commit()

    # 删除别人的记录返回 204（幂等），但记录还在
    client.delete(f"{BASE}/food-entries/{entry.id}", headers=headers)
    assert (
        db_session.scalar(
            select(func.count()).select_from(FoodEntry).where(
                FoodEntry.id == entry.id
            )
        )
        == 1
    )
