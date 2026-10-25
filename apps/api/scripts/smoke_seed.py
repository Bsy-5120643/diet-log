"""步骤 A 冒烟检查：建表 → 导入 → 搜索 → 换算。

验证数据库链路是否打通，不依赖外部 API、不依赖 Neon。

用法（cwd = apps/api）：
    DATABASE_URL=sqlite:// JWT_SECRET=x python -m scripts.smoke_seed
"""

from __future__ import annotations  # noqa: INP001

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401,E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.models.food import Food  # noqa: E402
from app.services.nutrition import scale, snapshot_of  # noqa: E402

from scripts.import_foods import load_rows, run_import  # noqa: E402


def search(db: Session, keyword: str) -> list[Food]:
    """按名称或别名模糊匹配（后续会搬到 food_service）。"""
    pattern = f"%{keyword}%"
    return list(
        db.scalars(
            select(Food).where(
                Food.search_text.like(pattern)
            )
        ).all()
    )


def main() -> int:
    Base.metadata.create_all(engine)
    db = Session(bind=engine, expire_on_commit=False)

    failures: list[str] = []

    try:
        rows = load_rows()
        created, updated = run_import(db, rows)
        db.commit()
        print(f"导入结果: 新增={created} 更新={updated}")

        total = db.scalar(select(func.count()).select_from(Food))
        print(f"foods 表总行数: {total}")
        if total != 50:
            failures.append(f"期望 50 条，实际 {total} 条")

        # 幂等性：重复执行不应新增
        before = total
        run_import(db, load_rows())
        db.commit()
        after = db.scalar(select(func.count()).select_from(Food))
        print(f"重复导入后行数: {after}")
        if before != after:
            failures.append(f"重复导入不幂等: {before} -> {after}")

        print("\n--- 搜索：鸡胸肉 ---")
        hits = search(db, "鸡胸肉")
        if not hits:
            failures.append("搜索『鸡胸肉』无结果")
        for f in hits:
            print(
                f"  {f.name}  {f.energy_kcal} kcal/100g  "
                f"P{f.protein_g} F{f.fat_g} C{f.carb_g}  别名={f.aliases}"
            )

        print("\n--- 别名搜索：西红柿（应命中番茄）---")
        alias_hits = search(db, "西红柿")
        if not alias_hits:
            failures.append("别名搜索『西红柿』无结果")
        for f in alias_hits:
            print(f"  命中: {f.name}  别名={f.aliases}")

        print("\n--- 150g 摄入换算 ---")
        if hits:
            food = hits[0]
            amount = scale(snapshot_of(food), Decimal("150"))
            print(f"  热量: {amount.energy_kcal} kcal  (预期 199.50)")
            print(f"  蛋白: {amount.protein_g} g      (预期 29.10)")
            print(f"  脂肪: {amount.fat_g} g      (预期 7.50)")
            print(f"  碳水: {amount.carb_g} g      (预期 3.75)")
            if amount.energy_kcal != Decimal("199.50"):
                failures.append(f"热量不符: {amount.energy_kcal}")
            if amount.protein_g != Decimal("29.10"):
                failures.append(f"蛋白不符: {amount.protein_g}")
    finally:
        db.close()

    print()
    if failures:
        print("冒烟结论: 未通过")
        for f in failures:
            print("  -", f)
        return 1
    print("冒烟结论: 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
