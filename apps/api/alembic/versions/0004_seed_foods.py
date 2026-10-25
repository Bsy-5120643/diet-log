"""seed foods table with 50 common foods

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25

说明：
- 从 app/db/seeds/foods.json 读数据，按 (name, brand) 幂等 upsert
- 因此本迁移可安全重复执行；调整 JSON 后再跑一次即可刷新数据
- 回滚只删除 source='seed' 的记录，不动用户自建食物
- 数据仅用于打通闭环，非权威营养数据，上线前需替换为正式食物库
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from app.models.food import Food

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from scripts.import_foods import load_rows, run_import

    session = Session(bind=op.get_bind())
    try:
        rows = load_rows()
        created, updated = run_import(session, rows)
        session.commit()
        print(f"seeded foods: created={created} updated={updated}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    from scripts.import_foods import load_rows

    session = Session(bind=op.get_bind())
    table = Food.__table__
    try:
        for row in load_rows():
            session.execute(
                sa.delete(table).where(
                    table.c.name == row.name,
                    sa.func.coalesce(table.c.brand, "") == (row.brand or ""),
                    table.c.source == "seed",
                )
            )
        session.commit()
    finally:
        session.close()
