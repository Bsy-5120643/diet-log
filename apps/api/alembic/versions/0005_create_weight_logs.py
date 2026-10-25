"""create weight_logs table and widen food_entries.meal_type check

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25

改动：
- 新建 weight_logs 表（看板体重折线的数据源），含 (user_id, logged_on) 唯一索引
- 放宽 food_entries 的 meal_type 检查，新增第 5 档 late_night（夜宵）
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "late_night")

_meal_list = ", ".join(repr(m) for m in MEAL_TYPES)


def upgrade() -> None:
    op.create_table(
        "weight_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Numeric(precision=5, scale=1), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
            name=op.f("fk_weight_logs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weight_logs")),
        sa.CheckConstraint("weight_kg BETWEEN 20 AND 400", name=op.f("ck_weight_logs_weight_plausible")),
    )
    op.create_index(
        "ix_weight_logs_user_date", "weight_logs", ["user_id", "logged_on"], unique=False
    )
    op.create_index(
        "uq_weight_logs_user_logged_on",
        "weight_logs",
        ["user_id", "logged_on"],
        unique=True,
    )

    # 0001 建立的 meal_type 检查只有 4 档，这里换成含夜宵的 5 档
    op.execute(
        "ALTER TABLE food_entries DROP CONSTRAINT IF EXISTS ck_food_entries_meal_type_valid"
    )
    op.execute(
        "ALTER TABLE food_entries ADD CONSTRAINT ck_food_entries_meal_type_valid "
        f"CHECK (meal_type IN ({_meal_list}))"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE food_entries DROP CONSTRAINT IF EXISTS ck_food_entries_meal_type_valid"
    )
    op.execute(
        "ALTER TABLE food_entries ADD CONSTRAINT ck_food_entries_meal_type_valid "
        "CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')"
    )

    op.drop_index("uq_weight_logs_user_logged_on", table_name="weight_logs")
    op.drop_index("ix_weight_logs_user_date", table_name="weight_logs")
    op.drop_table("weight_logs")
