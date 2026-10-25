"""密码哈希与 JWT 签发/校验。"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

_BCRYPT_ROUNDS = 12

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------------------
# 密码
# ---------------------------------------------------------------------------


def _prehash(password: str) -> bytes:
    """bcrypt 只处理前 72 字节，超长密码会被静默截断；另外部分实现对
    输入中的 NUL 字节处理不一致。先 sha256 再 base64 固定到 44 字节，
    既规避截断，也保证跨平台一致。
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        _prehash(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_token(
    *,
    subject: uuid.UUID,
    token_type: TokenType,
    ttl: timedelta,
) -> tuple[str, str, datetime]:
    """签发 JWT，返回 (token, jti, expires_at)。

    jti 用于在 refresh_tokens 表中定位并吊销单条会话。
    """
    now = datetime.now(tz=timezone.utc)
    expires_at = now + ttl
    jti = secrets.token_urlsafe(32)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "iat": now,
        "exp": expires_at,
        "jti": jti,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, jti, expires_at


def decode_token(token: str) -> dict[str, Any]:
    """校验签名与有效期；失败抛 jwt.PyJWTError 子类。"""
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "typ"]},
    )


def create_access_token(subject: uuid.UUID) -> tuple[str, str, datetime]:
    return create_token(
        subject=subject,
        token_type="access",
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
    )


def create_refresh_token(subject: uuid.UUID) -> tuple[str, str, datetime]:
    return create_token(
        subject=subject,
        token_type="refresh",
        ttl=timedelta(days=settings.refresh_token_ttl_days),
    )


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def hash_refresh_token(token: str) -> str:
    """刷新令牌入库前的哈希。

    刷新 token 是长期凭证，绝不能明文存库 —— 否则拖库即等于拿到全部会话。
    """
    return hashlib.sha256(token.encode("ascii")).hexdigest()
