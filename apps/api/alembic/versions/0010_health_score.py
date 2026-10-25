"""create daily_health_scores and users.avatar_url

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-25

健康指数与排行榜：
- `daily_health_scores` 缓存每日得分，排行榜只需一次 SQL 聚合即可算出
  「过去 7 天平均分」，避免实时计算把请求拖垮
- `users.avatar_url` 排行榜展示头像用
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("avatar_url", sa.String(length=500), nullable=True)
    )

    op.create_table(
        "daily_health_scores",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_daily_health_scores_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_health_scores")),
    )
    op.create_index(
        "uq_daily_scores_user_date",
        "daily_health_scores",
        ["user_id", "score_date"],
        unique=True,
    )
    op.create_index(
        "ix_daily_scores_date", "daily_health_scores", ["score_date"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_daily_scores_date", table_name="daily_health_scores")
    op.drop_index("uq_daily_scores_user_date", table_name="daily_health_scores")
    op.drop_table("daily_health_scores")
    op.drop_column("users", "avatar_url")
