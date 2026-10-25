"""种子食物导入与营养换算测试。

锁定第一阶段验收标准：
    搜索「鸡胸肉」→ 添加 150g 到午餐 → 汇总里热量 +199.5 kcal、蛋白质 +29.1 g
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, or_, select

from app.models.food import Food
from app.services.nutrition import scale, snapshot_of

from scripts.import_foods import load_rows, run_import


@pytest.fixture()
def seeded(db_session):
    """导入一次种子数据，返回会话。"""
    run_import(db_session, load_rows())
    db_session.commit()
    return db_session


def _search(db, keyword: str) -> list[Food]:
    pattern = f"%{keyword.strip().lower()}%"
    return list(db.scalars(select(Food).where(Food.search_text.like(pattern))).all())


def test_seed_rows_are_valid():
    rows = load_rows()
    assert len(rows) == 50
    assert all(row.name for row in rows)


def test_import_is_idempotent(db_session):
    first_created, first_updated = run_import(db_session, load_rows())
    db_session.commit()
    assert first_created == 50
    assert first_updated == 0

    again_created, again_updated = run_import(db_session, load_rows())
    db_session.commit()
    assert again_created == 0
    assert again_updated == 50

    total = db_session.scalar(select(func.count()).select_from(Food))
    assert total == 50


def test_search_chicken_breast_by_name(seeded):
    hits = _search(seeded, "鸡胸肉")
    assert len(hits) == 1
    assert hits[0].name == "鸡胸肉"
    assert hits[0].energy_kcal == Decimal("133.00")


def test_search_tomato_by_alias(seeded):
    """搜「西红柿」必须命中「番茄」—— 这正是 aliases 存在的意义。"""
    hits = _search(seeded, "西红柿")
    names = [f.name for f in hits]
    assert "番茄" in names


def test_search_miss_returns_empty(seeded):
    assert _search(seeded, "不存在的食物xyz") == []


def test_chicken_breast_150g_amounts(seeded):
    food = _search(seeded, "鸡胸肉")[0]
    amount = scale(snapshot_of(food), Decimal("150"))

    assert amount.energy_kcal == Decimal("199.50")
    assert amount.protein_g == Decimal("29.10")
    assert amount.fat_g == Decimal("7.50")
    assert amount.carb_g == Decimal("3.75")


def test_amounts_accumulate(seeded):
    """加两次 150g，总热量应为 399.0 kcal（验证累加而非覆盖）。"""
    food = _search(seeded, "鸡胸肉")[0]
    total = Decimal("0")
    for _ in range(2):
        total += scale(snapshot_of(food), Decimal("150")).energy_kcal
    assert total == Decimal("399.00")
