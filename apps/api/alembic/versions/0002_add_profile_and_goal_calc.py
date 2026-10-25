"""add user profile, goal calculation fields and refresh_tokens

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25

改动：
- users 增加身体档案（sex / age / height_cm / weight_kg）
- goals 增加目标类型、活动水平、输入快照与计算结果
- 新增 refresh_tokens 表
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
GOAL_TYPES = ("cut", "maintain", "gain")
SEXES = ("male", "female")

_activity_list = ", ".join(repr(a) for a in ACTIVITY_LEVELS)
_goal_type_list = ", ".join(repr(g) for g in GOAL_TYPES)
_sex_list = ", ".join(repr(s) for s in SEXES)


def upgrade() -> None:
    # ---- users：身体档案 ----
    op.add_column("users", sa.Column("sex", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("age", sa.SmallInteger(), nullable=True))
    op.add_column(
        "users", sa.Column("height_cm", sa.Numeric(precision=5, scale=1), nullable=True)
    )
    op.add_column(
        "users", sa.Column("weight_kg", sa.Numeric(precision=5, scale=1), nullable=True)
    )
    op.create_check_constraint(
        "ck_users_sex_valid", "users", f"sex IS NULL OR sex IN ({_sex_list})"
    )
    op.create_check_constraint(
        "ck_users_profile_plausible",
        "users",
        "(age IS NULL AND height_cm IS NULL AND weight_kg IS NULL)"
        " OR (age BETWEEN 14 AND 100 AND height_cm BETWEEN 50 AND 250"
        " AND weight_kg BETWEEN 20 AND 400)",
    )

    # ---- goals：目标类型 + 计算依据 ----
    op.add_column("goals", sa.Column("goal_type", sa.String(length=16), nullable=True))
    op.add_column("goals", sa.Column("activity_level", sa.String(length=16), nullable=True))
    op.add_column("goals", sa.Column("age", sa.SmallInteger(), nullable=True))
    op.add_column("goals", sa.Column("sex", sa.String(length=16), nullable=True))
    op.add_column(
        "goals", sa.Column("height_cm", sa.Numeric(precision=5, scale=1), nullable=True)
    )
    op.add_column(
        "goals", sa.Column("weight_kg", sa.Numeric(precision=5, scale=1), nullable=True)
    )
    op.add_column("goals", sa.Column("bmr_kcal", sa.Numeric(precision=7, scale=1), nullable=True))
    op.add_column("goals", sa.Column("tdee_kcal", sa.Numeric(precision=7, scale=1), nullable=True))
    op.add_column("goals", sa.Column("deficit_pct", sa.Numeric(precision=4, scale=3), nullable=True))

    op.create_check_constraint(
        "ck_goals_goal_type_valid", "goals", f"goal_type IS NULL OR goal_type IN ({_goal_type_list})"
    )
    op.create_check_constraint(
        "ck_goals_activity_level_valid",
        "goals",
        f"activity_level IS NULL OR activity_level IN ({_activity_list})",
    )
    op.create_check_constraint(
        "ck_goals_sex_valid", "goals", f"sex IS NULL OR sex IN ({_sex_list})"
    )
    op.create_check_constraint(
        "ck_goals_calculated_goal_complete",
        "goals",
        "source <> 'calculated'"
        " OR (goal_type IS NOT NULL AND activity_level IS NOT NULL"
        " AND age IS NOT NULL AND sex IS NOT NULL"
        " AND height_cm IS NOT NULL AND weight_kg IS NOT NULL"
        " AND bmr_kcal IS NOT NULL AND tdee_kcal IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_goals_deficit_within_cap", "goals", "deficit_pct IS NULL OR deficit_pct <= 0.20"
    )

    # ---- refresh_tokens ----
    op.create_table(
        "refresh_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_tokens")),
    )
    op.create_index(
        "ix_refresh_tokens_token_hash",
        "refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_constraint("ck_goals_deficit_within_cap", "goals", type_="check")
    op.drop_constraint("ck_goals_calculated_goal_complete", "goals", type_="check")
    op.drop_constraint("ck_goals_sex_valid", "goals", type_="check")
    op.drop_constraint("ck_goals_activity_level_valid", "goals", type_="check")
    op.drop_constraint("ck_goals_goal_type_valid", "goals", type_="check")
    op.drop_column("goals", "deficit_pct")
    op.drop_column("goals", "tdee_kcal")
    op.drop_column("goals", "bmr_kcal")
    op.drop_column("goals", "weight_kg")
    op.drop_column("goals", "height_cm")
    op.drop_column("goals", "sex")
    op.drop_column("goals", "age")
    op.drop_column("goals", "activity_level")
    op.drop_column("goals", "goal_type")

    op.drop_constraint("ck_users_profile_plausible", "users", type_="check")
    op.drop_constraint("ck_users_sex_valid", "users", type_="check")
    op.drop_column("users", "weight_kg")
    op.drop_column("users", "height_cm")
    op.drop_column("users", "age")
    op.drop_column("users", "sex")
