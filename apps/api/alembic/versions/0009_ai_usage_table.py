"""create ai_recognition_usage table

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25

对应 SPEC §5.5：配额（管成本）与限流（管滥用）合一表。
因为「失败不扣配额」会让反复调用变零成本，所以必须有限流兜底。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_recognition_usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column(
            "quota_used", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("minute_bucket", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "minute_count", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_ai_recognition_usage_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_recognition_usage")),
    )
    # 同一用户同一天只有一行
    op.create_index(
        "uq_ai_usage_user_date",
        "ai_recognition_usage",
        ["user_id", "usage_date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ai_usage_user_date", table_name="ai_recognition_usage")
    op.drop_table("ai_recognition_usage")
