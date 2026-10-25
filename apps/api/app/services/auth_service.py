"""认证业务逻辑：注册、登录、刷新、登出。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


import jwt
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair


class EmailAlreadyRegistered(Exception):
    """邮箱已被注册。"""


class InvalidCredentials(Exception):
    """邮箱或密码错误。

    对外统一返回这个错，不区分「邮箱不存在」和「密码错误」，
    否则接口可被用来枚举已注册邮箱。
    """


class InvalidRefreshToken(Exception):
    """刷新令牌无效、已过期或已吊销。"""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def has_goal(db: Session, user_id: uuid.UUID) -> bool:
    """该用户是否已设置过目标（前端据此决定是否跳引导页）。"""
    from app.models.goal import Goal

    return (
        db.scalar(select(Goal.id).where(Goal.user_id == user_id).limit(1))
        is not None
    )


def _is_expired(expires_at: datetime.datetime) -> bool:
    """判断刷新令牌是否已过期。

    库内统一按 UTC 存储。Postgres 的 timestamptz 回读带时区，
    而 SQLite 的 DATETIME 不保存时区、回读为 naive —— 这里补上 UTC 再比较。
    """
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= security.utc_now()


def _issue_tokens(
    db: Session,
    user: User,
    user_agent: str | None = None,
) -> TokenPair:
    """签发一对令牌，并把 refresh token 的哈希落库。"""
    access_token, _, _ = security.create_access_token(user.id)
    refresh_raw, _jti, expires_at = security.create_refresh_token(user.id)

    db.add(
        RefreshToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=security.hash_refresh_token(refresh_raw),
            expires_at=expires_at,
            user_agent=user_agent,
        )
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_raw,
        expires_in=settings.access_token_ttl_minutes * 60,
    )


def _revoke_all_for_user(db: Session, user_id: uuid.UUID) -> None:
    db.execute(
        sa.update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .values(revoked=True)
    )


def register(
    db: Session,
    payload: RegisterRequest,
    user_agent: str | None = None,
) -> tuple[User, TokenPair]:
    email = normalize_email(str(payload.email))

    if db.scalar(select(User).where(User.email == email)) is not None:
        raise EmailAlreadyRegistered(email)

    user = User(
        id=uuid.uuid4(),
        email=email,
        password_hash=security.hash_password(payload.password),
        nickname=payload.nickname,
    )
    db.add(user)
    db.flush()  # 先拿到 user.id，供 refresh token 外键使用

    tokens = _issue_tokens(db, user, user_agent=user_agent)
    db.commit()
    db.refresh(user)
    return user, tokens


def login(
    db: Session,
    payload: LoginRequest,
    user_agent: str | None = None,
) -> tuple[User, TokenPair]:
    email = normalize_email(str(payload.email))
    user = db.scalar(select(User).where(User.email == email))

    # 用户不存在时也跑一次哈希校验，避免响应时间差异泄露邮箱是否已注册
    if user is None or not security.verify_password(
        payload.password, user.password_hash
    ):
        raise InvalidCredentials()

    if not user.is_active:
        raise InvalidCredentials()

    tokens = _issue_tokens(db, user, user_agent=user_agent)
    db.commit()
    return user, tokens


def refresh(db: Session, refresh_token: str, user_agent: str | None = None) -> TokenPair:
    """轮换式刷新：旧 refresh token 立即吊销，同时签发新的一对。"""
    try:
        claims = security.decode_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise InvalidRefreshToken() from exc

    if claims.get("typ") != "refresh":
        raise InvalidRefreshToken()

    token_hash = security.hash_refresh_token(refresh_token)
    record = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if record is None:
        raise InvalidRefreshToken()

    if record.revoked:
        # 已吊销的 refresh token 被重复使用 = 疑似泄露，吊销该用户全部会话
        _revoke_all_for_user(db, record.user_id)
        db.commit()
        raise InvalidRefreshToken()

    if _is_expired(record.expires_at):
        raise InvalidRefreshToken()

    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise InvalidRefreshToken()

    record.revoked = True
    tokens = _issue_tokens(db, user, user_agent=user_agent)
    db.commit()
    return tokens


def logout(db: Session, refresh_token: str) -> None:
    token_hash = security.hash_refresh_token(refresh_token)
    record = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    if record is not None:
        record.revoked = True
        db.commit()
