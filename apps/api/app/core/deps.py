"""FastAPI 依赖：数据库会话 / 当前登录用户。"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core import security, errors
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization: Bearer <access_token> 解析当前用户。

    access token 由客户端存在内存里，BFF 代理转发时带上。
    """
    if credentials is None:
        raise errors.unauthorized("missing_token", "缺少访问令牌")

    raw = credentials.credentials
    try:
        claims = security.decode_token(raw)
    except jwt.ExpiredSignatureError as exc:
        raise errors.unauthorized("token_expired", "访问令牌已过期") from exc
    except jwt.PyJWTError as exc:
        raise errors.unauthorized("invalid_token", "访问令牌无效") from exc

    if claims.get("typ") != "access":
        raise errors.unauthorized("wrong_token_type", "令牌类型不正确")

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise errors.unauthorized("invalid_token", "访问令牌无效") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise errors.unauthorized("user_inactive", "用户不存在或已停用")

    return user


def get_user_agent(credentials: HTTPAuthorizationCredentials | None = None) -> str | None:
    """占位：真实实现应从 Request.headers 读取 user-agent。"""
    return None
