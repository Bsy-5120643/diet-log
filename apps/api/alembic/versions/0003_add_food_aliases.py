"""add foods.aliases / foods.search_text and a unique key for idempotent seeding

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-25

改动：
- foods 增加 aliases（jsonb）：口语名 / 同义词，供 API 与 UI 展示
- foods 增加 search_text（text）：去规范化的检索文本 = lower(name + aliases)
      —— 避免在 jsonb::text 上做 LIKE，规避中文被 \\uXXXX 转义后匹配失败
- 增加 (name, COALESCE(brand,'')) 唯一索引，作为种子导入的 upsert 依据
- 增加 search_text 的 pg_trgm GIN 索引，支撑 LIKE '%关键词%'
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "foods",
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "foods",
        sa.Column(
            "search_text",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )

    # brand 允许为 NULL，而 Postgres 唯一约束里 NULL 互不相等，
    # 会导致 (name, NULL) 被插入多次 —— 必须先 COALESCE 归一化。
    op.execute(
        "CREATE UNIQUE INDEX uq_foods_name_brand "
        "ON foods (name, COALESCE(brand, ''))"
    )

    # 0001 建的 name 三元组索引已被 search_text 覆盖（后者含名称），删掉避免重复维护
    op.execute("DROP INDEX IF EXISTS ix_foods_name_trgm")

    # 前置通配符的 LIKE 无法走 B-tree，靠 pg_trgm 的三元组索引
    op.execute(
        "CREATE INDEX ix_foods_search_text_trgm "
        "ON foods USING gin (search_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_foods_search_text_trgm")
    op.execute("DROP INDEX IF EXISTS uq_foods_name_brand")
    op.execute(
        "CREATE INDEX ix_foods_name_trgm "
        "ON foods USING gin (name gin_trgm_ops)"
    )
    op.drop_column("foods", "search_text")
    op.drop_column("foods", "aliases")
