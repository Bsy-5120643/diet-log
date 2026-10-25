"""make foods.protein_g / fat_g / carb_g nullable

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-25

原因：
《中国食物成分表》里存在未检测宏量营养素的条目（例如部分调味品、茶饮）。
导入时要求「缺失存 null，不填 0」—— 0 是真实测量值，与「未检测」语义不同。
原 schema 这三列是 NOT NULL，导致这类数据无法入库。

影响：这类食物无法参与摄入计算（food_entries 的快照列是 NOT NULL），
导入脚本会把它们计入「缺失字段」统计，供人工补录。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "foods",
        "protein_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=True,
    )
    op.alter_column(
        "foods",
        "fat_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=True,
    )
    op.alter_column(
        "foods",
        "carb_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=True,
    )


def downgrade() -> None:
    # 回滚前必须先把 NULL 填成 0，否则违反 NOT NULL
    op.execute(
        "UPDATE foods SET protein_g = 0 WHERE protein_g IS NULL;"
        "UPDATE foods SET fat_g = 0 WHERE fat_g IS NULL;"
        "UPDATE foods SET carb_g = 0 WHERE carb_g IS NULL"
    )
    op.alter_column(
        "foods",
        "protein_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=False,
    )
    op.alter_column(
        "foods",
        "fat_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=False,
    )
    op.alter_column(
        "foods",
        "carb_g",
        existing_type=sa.Numeric(precision=6, scale=2),
        nullable=False,
    )
