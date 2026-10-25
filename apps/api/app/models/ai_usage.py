"""AI 识别的配额、限流与锁定状态。

对应 SPEC §5.5。按「用户 + 自然日」一行，重置维度是 usage_date。

两种计数分开存放，职责不同：
- `quota_used` —— 管**成本**，只统计成功调用
- `minute_count` —— 管**滥用**，任何发起都计数（含失败）

因为「失败不扣配额」会让反复调用变零成本，所以限流必须独立存在。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class AiRecognitionUsage(TimestampMixin, Base):
    __tablename__ = "ai_recognition_usage"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 自然日（按用户时区），配额重置维度
    usage_date: Mapped[datetime.date] = mapped_column(nullable=False)
    #: 当日已消耗配额，只统计成功调用
    quota_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: 当前分钟窗口起点（固定窗口法）
    minute_bucket: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: 该分钟窗口内已发起次数，无论成败
    minute_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: 连续「完全没认出」次数；成功即清零
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    #: 锁定截止时间（连续失败过多）
    locked_until: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship()  # noqa: F821

    def __repr__(self) -> str:
        return f"<AiRecognitionUsage {self.user_id} {self.usage_date} {self.quota_used}>"
