from __future__ import annotations

import uuid

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    Uuid,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.models.enums import SEXES


class User(TimestampMixin, Base):
    """用户基本信息。所有业务数据的权限锚点。"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        # Python 侧生成，ORM 插入时一定带值；
        # 迁移里同时保留 server_default，供裸 SQL 插入使用。
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    #: 头像地址，排行榜展示用。未设置时前端回落占位图。
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'Asia/Shanghai'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )

    # 身体档案：用于表单回显与目标计算。每次改目标时会快照进 goals，
    # 所以这里存的是「当前值」，可以放心被覆盖。
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True
    )
    weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1), nullable=True
    )

    #: 是否已同意 AI 拍照识别的隐私条款。未同意不得调用识别接口。
    #: 本期用单个布尔字段，未做条款版本管理（见 SPEC §8.4）。
    has_agreed_ai_privacy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )

    goals: Mapped[list["Goal"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    entries: Mapped[list["FoodEntry"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    recipes: Mapped[list["Recipe"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # 登录时 WHERE email = ? 是最高频查询，唯一约束自动建 B-tree 索引
        Index("ix_users_email", "email", unique=True),
        # 强制小写，杜绝 A@x.com 与 a@x.com 注册成两个账号
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # 身体档案要么全空（刚注册），要么全填（完成引导后）
        CheckConstraint(
            f"sex IN ({', '.join(repr(s) for s in SEXES)})",
            name="sex_valid",
        ),
        CheckConstraint(
            "(age IS NULL AND height_cm IS NULL AND weight_kg IS NULL)"
            " OR (age BETWEEN 14 AND 100 AND height_cm BETWEEN 50 AND 250"
            " AND weight_kg BETWEEN 20 AND 400)",
            name="profile_plausible",
        ),
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
