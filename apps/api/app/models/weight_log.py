from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class WeightLog(TimestampMixin, Base):
    """体重记录。

    同一天只保留一条（唯一索引 user_id + logged_on），重复记录走 upsert。
    否则早晚各称一次会产生两条数据，把体重折线图画成锯齿。
    """

    __tablename__ = "weight_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 用户本地日期，不做时区转换
    logged_on: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    #: 体重 kg
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship()  # noqa: F821

    __table_args__ = (
        # 看板按「某用户最近 N 天」取数据，这是主查询路径
        Index("ix_weight_logs_user_date", "user_id", "logged_on"),
        # 同一天只允许一条
        Index("uq_weight_logs_user_logged_on", "user_id", "logged_on", unique=True),
        CheckConstraint("weight_kg BETWEEN 20 AND 400", name="weight_plausible"),
    )

    def __repr__(self) -> str:
        return f"<WeightLog {self.logged_on} {self.weight_kg}kg>"
