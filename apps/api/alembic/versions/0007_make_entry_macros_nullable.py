"""allow NULL macros in food_entries

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25

背景：
0006 已允许 foods 的 protein_g / fat_g / carb_g 为 NULL（《中国食物成分表》
确有未检测条目）。但 food_entries 的对应列仍是 NOT NULL，导致用户一旦吃了
这类食物就**无法记录**——这是把数据缺失的代价转嫁给用户，不合理。

原则：数据缺失不应该阻止用户记录。缺失项记 NULL，汇总时按 0 计入总热量，
UI 显示为「-」而不是 0，避免误导用户以为「确实是 0」。

为什么不放宽 snapshot_energy_kcal：
导入脚本把「能量缺失」视为关键字段缺失并跳过，能入库的食物一定有能量。
热量是核心指标，不允许出现算不出来的记录。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 需要放宽的宏量列（快照 + 计算值）
MACRO_COLUMNS: tuple[tuple[str, str, int, int], ...] = (
    # (列名, numeric 精度, scale)
    ("snapshot_protein_g", 6, 2),
    ("snapshot_fat_g", 6, 2),
    ("snapshot_carb_g", 6, 2),
    ("protein_g", 7, 2),
    ("fat_g", 7, 2),
    ("carb_g", 7, 2),
)


def upgrade() -> None:
    for column, precision, scale in MACRO_COLUMNS:
        op.alter_column(
            "food_entries",
            column,
            existing_type=sa.Numeric(precision=precision, scale=scale),
            nullable=True,
        )

    # 一致性约束必须同步放宽：
    # 快照为 NULL 时，计算值也必须是 NULL（不能一边 NULL 一边是数字）
    op.execute(
        "ALTER TABLE food_entries DROP CONSTRAINT IF EXISTS ck_food_entries_computed_consistent"
    )
    # 注意 SQL 三值逻辑：不能写成 (快照 IS NULL AND 值 IS NULL) OR 值 = round(...)
    # 因为「快照 NULL 但值是数字」时第二个分支得到 NULL，而 CHECK 在 NULL 时通过。
    # 两个分支都必须显式判断非空。
    op.execute(
        "ALTER TABLE food_entries ADD CONSTRAINT ck_food_entries_computed_consistent "
        "CHECK ("
        "  energy_kcal = round(quantity_g * snapshot_energy_kcal / 100.0, 2)"
        "  AND ((snapshot_protein_g IS NULL AND protein_g IS NULL)"
        "       OR (snapshot_protein_g IS NOT NULL AND protein_g IS NOT NULL"
        "           AND protein_g = round(quantity_g * snapshot_protein_g / 100.0, 2)))"
        "  AND ((snapshot_fat_g IS NULL AND fat_g IS NULL)"
        "       OR (snapshot_fat_g IS NOT NULL AND fat_g IS NOT NULL"
        "           AND fat_g = round(quantity_g * snapshot_fat_g / 100.0, 2)))"
        "  AND ((snapshot_carb_g IS NULL AND carb_g IS NULL)"
        "       OR (snapshot_carb_g IS NOT NULL AND carb_g IS NOT NULL"
        "           AND carb_g = round(quantity_g * snapshot_carb_g / 100.0, 2)))"
        ")"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE food_entries DROP CONSTRAINT IF EXISTS ck_food_entries_computed_consistent"
    )
    op.execute(
        "ALTER TABLE food_entries ADD CONSTRAINT ck_food_entries_computed_consistent "
        "CHECK ("
        "  energy_kcal = round(quantity_g * snapshot_energy_kcal / 100.0, 2)"
        "  AND protein_g = round(quantity_g * snapshot_protein_g / 100.0, 2)"
        "  AND fat_g = round(quantity_g * snapshot_fat_g / 100.0, 2)"
        "  AND carb_g = round(quantity_g * snapshot_carb_g / 100.0, 2)"
        ")"
    )

    # 回滚前先把 NULL 补成 0，否则违反 NOT NULL
    for column, _precision, _scale in MACRO_COLUMNS:
        op.execute(
            "UPDATE food_entries SET " + column + " = 0 WHERE " + column + " IS NULL"
        )
        precision, scale = _precision, _scale
        op.alter_column(
            "food_entries",
            column,
            existing_type=sa.Numeric(precision=precision, scale=scale),
            nullable=False,
        )
