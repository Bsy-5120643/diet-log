from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Uuid,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RefreshToken(Base):
    """刷新令牌。

    安全要点：库里只存 hash，不存明文。DB 泄露也无法直接拿到可用 token。
    吊销用 revoked 标记而非物理删除，保留审计痕迹。
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # sha256(refresh_token) 的十六进制串
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship()  # noqa: F821

    __table_args__ = (
        # 按 hash 精确查找 —— 刷新接口的唯一查询路径
        Index("ix_refresh_tokens_token_hash", "token_hash", unique=True),
        # 清理过期 token 的定时任务会扫这个
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        # 用户维度查询（列出在线设备、全部踢下线）
        Index("ix_refresh_tokens_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} expires={self.expires_at}>"
