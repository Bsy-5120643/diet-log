from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.models.enums import (
    ACTIVITY_LEVELS,
    GOAL_SOURCES,
    GOAL_TYPES,
    SEXES,
)

_ACTIVITY_LIST = ", ".join(repr(a) for a in ACTIVITY_LEVELS)
_GOAL_TYPE_LIST = ", ".join(repr(g) for g in GOAL_TYPES)
_SEX_LIST = ", ".join(repr(s) for s in SEXES)


class Goal(TimestampMixin, Base):
    """每日热量与三大营养素目标。

    关键设计：用 effective_from 做生效日期，而不是覆盖写同一行。
    否则用户改了目标后，历史某天的汇总会按新目标计算，数据失真。
    """

    __tablename__ = "goals"

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
    effective_from: Mapped[datetime.date] = mapped_column(Date, nullable=False)

    energy_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 1), nullable=False)
    protein_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    fat_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    carb_g: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)

    # 第一版不设为目标项，仅记录，便于后续扩展
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 1), nullable=True)
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True)

    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'manual'")
    )

    # ---- 以下为「计算型目标」专用（source='calculated'）----
    # 目标类型与活动水平
    goal_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    activity_level: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # 输入快照：固化「当时用什么参数算的」，改了档案也不影响历史目标
    age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)

    # 计算中间量：便于前端展示「你的基础代谢/每日消耗」
    bmr_kcal: Mapped[Decimal | None] = mapped_column(Numeric(7, 1), nullable=True)
    tdee_kcal: Mapped[Decimal | None] = mapped_column(Numeric(7, 1), nullable=True)

    # 实际生效的缺口比例：可能小于配置值（撞到 BMR / 最低热量下限后）
    deficit_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)

    user: Mapped["User"] = relationship(back_populates="goals")  # noqa: F821

    __table_args__ = (
        # 防止同一天存在多条生效目标
        # 同时支撑查询：WHERE user_id=? AND effective_from<=? ORDER BY effective_from DESC LIMIT 1
        # 列顺序必须是 (等值列 user_id, 范围列 effective_from)，符合最左前缀
        UniqueConstraint(
            "user_id", "effective_from", name="uq_goals_user_effective_from"
        ),
        CheckConstraint("energy_kcal > 0", name="energy_positive"),
        CheckConstraint(
            "protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0",
            name="macros_non_negative",
        ),
        CheckConstraint(
            f"source IN ({', '.join(repr(s) for s in GOAL_SOURCES)})",
            name="source_valid",
        ),
        CheckConstraint(
            f"goal_type IS NULL OR goal_type IN ({_GOAL_TYPE_LIST})",
            name="goal_type_valid",
        ),
        CheckConstraint(
            f"activity_level IS NULL OR activity_level IN ({_ACTIVITY_LIST})",
            name="activity_level_valid",
        ),
        CheckConstraint(
            f"sex IS NULL OR sex IN ({_SEX_LIST})",
            name="sex_valid",
        ),
        # 计算型目标必须带全套计算依据，否则无法解释目标从哪来
        CheckConstraint(
            "source <> 'calculated'"
            " OR (goal_type IS NOT NULL AND activity_level IS NOT NULL"
            " AND age IS NOT NULL AND sex IS NOT NULL"
            " AND height_cm IS NOT NULL AND weight_kg IS NOT NULL"
            " AND bmr_kcal IS NOT NULL AND tdee_kcal IS NOT NULL)",
            name="calculated_goal_complete",
        ),
        # 减脂缺口不得超过 TDEE 的 20%
        CheckConstraint(
            "deficit_pct IS NULL OR deficit_pct <= 0.20",
            name="deficit_within_cap",
        ),
    )

    def __repr__(self) -> str:
        return f"<Goal user={self.user_id} from={self.effective_from}>"
