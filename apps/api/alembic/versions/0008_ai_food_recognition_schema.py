"""AI 拍照识别功能的表结构

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25

对应 SPEC-ai-food-recognition.md §3：
- 新增 recipes（菜品）
- 新增 recipe_ingredients（菜品食材明细）
- users 增加 has_agreed_ai_privacy（隐私条款同意标记）
- food_entries 增加 recipe_id / entry_group_id

设计要点：
- 菜品表**不存营养数据**，只存食材组成；营养永远从 foods 读
- 唯一索引建在 (user_id, normalized_name)，这是「同名直接复用」的基础
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users: 隐私条款同意标记 ----
    op.add_column(
        "users",
        sa.Column(
            "has_agreed_ai_privacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # ---- food_entries: 关联菜品 + 分组 ----
    op.add_column(
        "food_entries",
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "food_entries",
        sa.Column("entry_group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ---- recipes ----
    op.create_table(
        "recipes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("total_energy_kcal", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column(
            "source",
            sa.String(length=16),
            server_default=sa.text("'ai'"),
            nullable=False,
        ),
        sa.Column(
            "is_temporary", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column(
            "origin",
            sa.String(length=16),
            server_default=sa.text("'user'"),
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
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recipes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.CheckConstraint(
            "source IN ('ai', 'manual', 'seed')",
            name=op.f("ck_recipes_recipe_source_valid"),
        ),
        sa.CheckConstraint(
            "origin IN ('user', 'public')",
            name=op.f("ck_recipes_recipe_origin_valid"),
        ),
    )
    op.create_index(
        "uq_recipes_user_normalized_name",
        "recipes",
        ["user_id", "normalized_name"],
        unique=True,
    )
    op.create_index(
        "ix_recipes_normalized_name", "recipes", ["normalized_name"], unique=False
    )

    # ---- recipe_ingredients ----
    op.create_table(
        "recipe_ingredients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("recipe_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("food_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_g", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column(
            "display_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
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
            ["food_id"],
            ["foods.id"],
            name=op.f("fk_recipe_ingredients_food_id_foods"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_ingredients_recipe_id_recipes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipe_ingredients")),
        sa.CheckConstraint(
            "quantity_g > 0",
            name=op.f("ck_recipe_ingredients_recipe_ingredient_quantity_positive"),
        ),
    )
    op.create_index(
        "ix_recipe_ingredients_recipe",
        "recipe_ingredients",
        ["recipe_id"],
        unique=False,
    )

    # ---- food_entries 的外键与索引（recipes 建好后才能加）----
    op.create_foreign_key(
        op.f("fk_food_entries_recipe_id_recipes"),
        "food_entries",
        "recipes",
        ["recipe_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_food_entries_recipe_id", "food_entries", ["recipe_id"], unique=False
    )
    op.create_index(
        "ix_food_entries_group_id", "food_entries", ["entry_group_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_food_entries_group_id", table_name="food_entries")
    op.drop_index("ix_food_entries_recipe_id", table_name="food_entries")
    op.drop_constraint(
        op.f("fk_food_entries_recipe_id_recipes"), "food_entries", type_="foreignkey"
    )

    op.drop_index("ix_recipe_ingredients_recipe", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")

    op.drop_index("ix_recipes_normalized_name", table_name="recipes")
    op.drop_index("uq_recipes_user_normalized_name", table_name="recipes")
    op.drop_table("recipes")

    op.drop_column("food_entries", "entry_group_id")
    op.drop_column("food_entries", "recipe_id")
    op.drop_column("users", "has_agreed_ai_privacy")
