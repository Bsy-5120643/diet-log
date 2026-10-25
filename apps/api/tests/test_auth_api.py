"""认证与目标接口的端到端测试。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.enums import ActivityLevel, GoalType, Sex

BASE = "/api/v1"

VALID_PROFILE = {
    "sex": "male",
    "age": 30,
    "height_cm": 175,
    "weight_kg": 70,
    "activity_level": "moderate",
    "goal_type": "cut",
}


def _register(client, email: str, password: str = "Password123"):
    return client.post(
        f"{BASE}/auth/register",
        json={"email": email, "password": password, "nickname": "测试"},
    )


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------


def test_register_returns_tokens(client):
    resp = _register(client, "a@example.com")
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["user"]["email"] == "a@example.com"
    assert body["user"]["has_goal"] is False
    assert body["tokens"]["token_type"] == "bearer"
    assert body["tokens"]["access_token"]


def test_register_duplicate_email_conflict(client):
    assert _register(client, "dup@example.com").status_code == 201
    resp = _register(client, "dup@example.com")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "email_taken"


def test_register_normalizes_email_case(client):
    assert _register(client, "MiXeD@Example.COM").status_code == 201
    resp = _register(client, "mixed@example.com")
    # 大小写不同应视为同一账号
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "password",
    ["short", "1234567", "a" * 129],
)
def test_register_rejects_bad_password(client, password):
    resp = client.post(
        f"{BASE}/auth/register",
        json={"email": "pw@example.com", "password": password},
    )
    assert resp.status_code == 422


def test_register_rejects_bad_email(client):
    resp = client.post(
        f"{BASE}/auth/register",
        json={"email": "not-an-email", "password": "Password123"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 登录
# ---------------------------------------------------------------------------


def test_login_success(client):
    _register(client, "login@example.com")
    resp = client.post(
        f"{BASE}/auth/login",
        json={"email": "login@example.com", "password": "Password123"},
    )
    assert resp.status_code == 200
    assert resp.json()["tokens"]["access_token"]


def test_login_wrong_password_unauthorized(client):
    _register(client, "wrong@example.com")
    resp = client.post(
        f"{BASE}/auth/login",
        json={"email": "wrong@example.com", "password": "WrongPassword1"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


def test_login_unknown_email_same_error(client):
    """未注册邮箱与密码错误必须返回同一错误码，防止邮箱枚举。"""
    resp = client.post(
        f"{BASE}/auth/login",
        json={"email": "nobody@example.com", "password": "Password123"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "invalid_credentials"


# ---------------------------------------------------------------------------
# 当前用户 / 鉴权
# ---------------------------------------------------------------------------


def test_me_requires_token(client):
    assert client.get(f"{BASE}/auth/me").status_code == 401


def test_me_with_token(client, auth_headers, test_user):
    resp = client.get(f"{BASE}/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == test_user.email


def test_refresh_token_cannot_be_used_as_access(client, test_user):
    """拿 refresh token 去访问业务接口必须被拒。"""
    login = client.post(
        f"{BASE}/auth/login",
        json={"email": test_user.email, "password": "Password123"},
    )
    refresh = login.json()["tokens"]["refresh_token"]
    resp = client.get(
        f"{BASE}/auth/me", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "wrong_token_type"


def test_refresh_rotates_and_rejects_reuse(client, test_user):
    login = client.post(
        f"{BASE}/auth/login",
        json={"email": test_user.email, "password": "Password123"},
    )
    first_refresh = login.json()["tokens"]["refresh_token"]

    ok = client.post(f"{BASE}/auth/refresh", json={"refresh_token": first_refresh})
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    # 轮换后旧的 refresh token 不可再用
    again = client.post(f"{BASE}/auth/refresh", json={"refresh_token": first_refresh})
    assert again.status_code == 401
    assert again.json()["detail"]["code"] == "invalid_refresh_token"


def test_garbage_refresh_token_rejected(client):
    resp = client.post(f"{BASE}/auth/refresh", json={"refresh_token": "garbage"})
    assert resp.status_code in (401, 422)


# ---------------------------------------------------------------------------
# 目标：估算 / 获取 / 更新
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload, expected_tdee",
    [
        (VALID_PROFILE, 2555.6),
        (
            {
                "sex": "female",
                "age": 25,
                "height_cm": 160,
                "weight_kg": 60,
                "activity_level": "light",
                "goal_type": "maintain",
            },
            1806.8,
        ),
    ],
)
def test_estimate_tdee(client, payload, expected_tdee):
    """估算接口无需登录，落地页可直接调用。"""
    resp = client.post(f"{BASE}/goals/estimate", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["tdee_kcal"] == pytest.approx(expected_tdee, abs=0.1)


def test_get_current_goal_404_before_set(client, auth_headers):
    resp = client.get(f"{BASE}/goals/current", headers=auth_headers)
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "goal_not_set"


def test_update_then_get_current_goal(client, auth_headers):
    resp = client.put(f"{BASE}/goals/current", json=VALID_PROFILE, headers=auth_headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["source"] == "calculated"
    assert body["goal_type"] == "cut"
    assert body["activity_level"] == "moderate"

    # 与计算器期望值一致
    assert body["energy_kcal"] == pytest.approx(2044, abs=1)
    assert body["protein_g"] == pytest.approx(140.0, abs=0.1)
    assert body["bmr_kcal"] == pytest.approx(1648.8, abs=0.1)
    assert body["tdee_kcal"] == pytest.approx(2555.6, abs=0.1)

    # 再取一次应能拿到
    again = client.get(f"{BASE}/goals/current", headers=auth_headers)
    assert again.status_code == 200
    assert again.json()["energy_kcal"] == pytest.approx(2044, abs=1)


def test_update_is_idempotent_same_day(client, auth_headers, db_session):
    """同一天重复更新应覆盖同一条，而不是新增多条。"""
    from app.models.goal import Goal
    from sqlalchemy import select

    client.put(f"{BASE}/goals/current", json=VALID_PROFILE, headers=auth_headers)
    client.put(f"{BASE}/goals/current", json=VALID_PROFILE, headers=auth_headers)

    count = len(db_session.scalars(select(Goal)).all())
    assert count == 1


def test_calculate_endpoint_rejects_invalid_input(client):
    bad = {**VALID_PROFILE, "age": 5}
    resp = client.post(f"{BASE}/goals/estimate", json=bad)
    assert resp.status_code == 422


def test_goals_require_auth(client):
    assert client.get(f"{BASE}/goals/current").status_code == 401
    assert client.put(f"{BASE}/goals/current", json=VALID_PROFILE).status_code == 401
