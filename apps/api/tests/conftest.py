"""测试夹具：每个用例一套独立 SQLite 内存库 + 一份干净的会话。

生产用 Postgres，测试用 SQLite。模型和 CHECK 约束两边都能编译，
但要注意：SQLite 不校验类型长度，真正的约束验证必须在 Postgres 上再跑一遍。
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

# 必须在导入 app 之前准备好环境变量，否则 Settings 校验失败
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import app.models  # noqa: F401,E402 —— 确保所有模型注册进 metadata
from app.core import security  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.goal import Goal  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_PASSWORD = "Password123"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    # StaticPool + check_same_thread=False：让 TestClient 的工作线程
    # 也能复用同一个内存连接，否则跨线程会各开一个空库
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False, class_=Session
    )()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def test_user(db_session: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="tester@example.com",
        password_hash=security.hash_password(TEST_PASSWORD),
        nickname="测试用户",
        timezone="Asia/Shanghai",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(client: TestClient, test_user: User) -> dict[str, str]:
    """走完整登录流程，返回带 Bearer 的请求头。"""
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": test_user.email, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['tokens']['access_token']}"}
