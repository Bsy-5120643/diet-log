"""init schema: users, goals, foods, food_entries

Revision ID: 0001
Revises:
Create Date: 2026-10-25

说明：本迁移为手写（非 autogenerate 生成），因为 autogenerate 检测不到
      CHECK 约束、部分索引、GIN trgm 索引的函数式表达式与扩展依赖。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
FOOD_SOURCES = ("seed", "usda", "user")
GOAL_SOURCES = ("manual", "calculated")

_meal_list = ", ".join(repr(m) for m in MEAL_TYPES)
_food_source_list = ", ".join(repr(s) for s in FOOD_SOURCES)
_goal_source_list = ", ".join(repr(s) for s in GOAL_SOURCES)


def upgrade() -> None:
    # 中文模糊搜索 LIKE '%关键词%' 必须依赖 pg_trgm
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Asia/Shanghai'"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
    )

    op.create_table(
        "goals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("energy_kcal", sa.Numeric(precision=7, scale=1), nullable=False),
        sa.Column("protein_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("fat_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("carb_g", sa.Numeric(precision=6, scale=1), nullable=False),
        sa.Column("fiber_g", sa.Numeric(precision=6, scale=1), nullable=True),
        sa.Column("sodium_mg", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column(
            "source",
            sa.String(length=16),
            server_default=sa.text("'manual'"),
            nullable=False,
        ),
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
            ["user_id"], ["users.id"], name=op.f("fk_goals_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goals")),
        sa.UniqueConstraint(
            "user_id", "effective_from", name=op.f("uq_goals_user_effective_from")
        ),
        sa.CheckConstraint("energy_kcal > 0", name=op.f("ck_goals_energy_positive")),
        sa.CheckConstraint(
            "protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0",
            name=op.f("ck_goals_macros_non_negative"),
        ),
        sa.CheckConstraint(
            f"source IN ({_goal_source_list})", name=op.f("ck_goals_source_valid")
        ),
    )

    op.create_table(
        "foods",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("barcode", sa.String(length=32), nullable=True),
        sa.Column("energy_kcal", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("protein_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("fat_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("carb_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("fiber_g", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("sodium_mg", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "source",
            sa.String(length=16),
            server_default=sa.text("'seed'"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_public", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
            ["created_by"], ["users.id"], name=op.f("fk_foods_created_by_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_foods")),
        sa.CheckConstraint(
            "energy_kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0",
            name=op.f("ck_foods_values_non_negative"),
        ),
        sa.CheckConstraint(
            f"source IN ({_food_source_list})", name=op.f("ck_foods_source_valid")
        ),
        sa.CheckConstraint(
            "(source = 'user' AND created_by IS NOT NULL) OR (source <> 'user')",
            name=op.f("ck_foods_user_owned"),
        ),
    )
    op.create_index(
        "ix_foods_name_trgm",
        "foods",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_foods_public_active",
        "foods",
        ["is_public", "is_active"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "uq_foods_barcode",
        "foods",
        ["barcode"],
        unique=True,
        postgresql_where=sa.text("barcode IS NOT NULL"),
    )

    op.create_table(
        "food_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("food_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("meal_type", sa.String(length=16), nullable=False),
        sa.Column("quantity_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("serving_unit", sa.String(length=16), nullable=True),
        sa.Column("serving_count", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column(
            "serving_grams_per_unit", sa.Numeric(precision=8, scale=2), nullable=True
        ),
        sa.Column("snapshot_energy_kcal", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("snapshot_protein_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("snapshot_fat_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("snapshot_carb_g", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("snapshot_fiber_g", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("snapshot_sodium_mg", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("energy_kcal", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("protein_g", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("fat_g", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("carb_g", sa.Numeric(precision=7, scale=2), nullable=False),
        sa.Column("fiber_g", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("sodium_mg", sa.Numeric(precision=9, scale=2), nullable=True),
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
            ["food_id"], ["foods.id"], name=op.f("fk_food_entries_food_id_foods"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_food_entries_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_food_entries")),
        sa.CheckConstraint(
            f"meal_type IN ({_meal_list})", name=op.f("ck_food_entries_meal_type_valid")
        ),
        sa.CheckConstraint(
            "quantity_g > 0", name=op.f("ck_food_entries_quantity_positive")
        ),
        sa.CheckConstraint(
            "energy_kcal = round(quantity_g * snapshot_energy_kcal / 100, 2)"
            " AND protein_g = round(quantity_g * snapshot_protein_g / 100, 2)"
            " AND fat_g     = round(quantity_g * snapshot_fat_g / 100, 2)"
            " AND carb_g    = round(quantity_g * snapshot_carb_g / 100, 2)",
            name=op.f("ck_food_entries_computed_consistent"),
        ),
    )
    op.create_index(
        "ix_food_entries_user_date", "food_entries", ["user_id", "entry_date"], unique=False
    )
    op.create_index(
        "ix_food_entries_user_food", "food_entries", ["user_id", "food_id"], unique=False
    )
    op.create_index("ix_food_entries_food_id", "food_entries", ["food_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_food_entries_food_id", table_name="food_entries")
    op.drop_index("ix_food_entries_user_food", table_name="food_entries")
    op.drop_index("ix_food_entries_user_date", table_name="food_entries")
    op.drop_table("food_entries")

    op.drop_index("uq_foods_barcode", table_name="foods")
    op.drop_index("ix_foods_public_active", table_name="foods")
    op.drop_index("ix_foods_name_trgm", table_name="foods")
    op.drop_table("foods")

    op.drop_table("goals")
    op.drop_table("users")
