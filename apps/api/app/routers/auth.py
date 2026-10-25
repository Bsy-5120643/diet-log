"""认证接口：注册 / 登录 / 刷新 / 登出 / 当前用户。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import conflict, unauthorized
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(db: Session, user: User) -> UserOut:
    """附带 has_goal 标记，前端据此决定是否跳引导页。"""
    out = UserOut.model_validate(user)
    out.has_goal = auth_service.has_goal(db, user.id)
    return out


@router.post(
    "/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED
)
def register(
    payload: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """注册。邮箱统一转小写存储，密码用 bcrypt(cost=12) 哈希。"""
    try:
        user, tokens = auth_service.register(
            db, payload, user_agent=request.headers.get("user-agent")
        )
    except auth_service.EmailAlreadyRegistered as exc:
        raise conflict("email_taken", "该邮箱已被注册") from exc

    return AuthResponse(user=_user_out(db, user), tokens=tokens)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AuthResponse:
    """登录。失败统一返回 invalid_credentials，不泄露邮箱是否注册。"""
    try:
        user, tokens = auth_service.login(
            db, payload, user_agent=request.headers.get("user-agent")
        )
    except auth_service.InvalidCredentials as exc:
        raise unauthorized("invalid_credentials", "邮箱或密码错误") from exc

    return AuthResponse(user=_user_out(db, user), tokens=tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenPair:
    """用 refresh token 换一对新令牌（旧的立即吊销，防止重放）。"""
    try:
        return auth_service.refresh(
            db, payload.refresh_token, user_agent=request.headers.get("user-agent")
        )
    except auth_service.InvalidRefreshToken as exc:
        raise unauthorized("invalid_refresh_token", "登录已失效，请重新登录") from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> None:
    """吊销指定 refresh token。"""
    auth_service.logout(db, payload.refresh_token)


@router.get("/me", response_model=UserOut)
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    """当前登录用户信息。"""
    return _user_out(db, current_user)
