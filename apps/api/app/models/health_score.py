"""每日健康指数。

为什么要落库而不是实时算：排行榜要算「过去 7 天平均分」，
实时计算是 `用户数 × 7 天 × (加载记录 + 加载目标 + 计算)`，
MVP 后期上千用户就会把单次请求拖垮。这里把每天的得分缓存下来，
排行榜只做一次 SQL 聚合。

`breakdown` 存明细，供复盘页展示「热量/宏量/习惯」三项各拿了多少分。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, Date, ForeignKey, Index, Integer, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class DailyHealthScore(TimestampMixin, Base):
    __tablename__ = "daily_health_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    score_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    #: 0-100
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    #: {"heat": 32.0, "macro": 24.0, "habit": 22.0}
    breakdown: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    user: Mapped["User"] = relationship()  # noqa: F821

    __table_args__ = (
        # 幂等：同一天反复计算不会产生重复行
        Index("uq_daily_scores_user_date", "user_id", "score_date", unique=True),
        # 排行榜按日期区间聚合
        Index("ix_daily_scores_date", "score_date"),
    )

    def __repr__(self) -> str:
        return f"<DailyHealthScore {self.user_id} {self.score_date} {self.score}>"
