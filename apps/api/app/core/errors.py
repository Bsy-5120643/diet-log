"""统一错误返回格式。

全站错误 body 形如：
    {"detail": {"code": "token_expired", "message": "访问令牌已过期"}}

前端根据 code 做分支（特别是 token_expired 触发刷新重试），
message 直接展示给用户。
"""

from __future__ import annotations

from fastapi import HTTPException, status
from typing import Any


def fail(
    status_code: int,
    code: str,
    message: str,
    **extra: Any,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def bad_request(code: str, message: str, **extra: Any) -> HTTPException:
    return fail(status.HTTP_400_BAD_REQUEST, code, message, **extra)


def unauthorized(code: str, message: str, **extra: Any) -> HTTPException:
    return fail(
        status.HTTP_401_UNAUTHORIZED, code, message, headers={"WWW-Authenticate": "Bearer"}, **extra
    )


def conflict(code: str, message: str, **extra: Any) -> HTTPException:
    return fail(status.HTTP_409_CONFLICT, code, message, **extra)


def not_found(code: str, message: str, **extra: Any) -> HTTPException:
    return fail(status.HTTP_404_NOT_FOUND, code, message, **extra)


def unprocessable(code: str, message: str, **extra: Any) -> HTTPException:
    return fail(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message, **extra)
