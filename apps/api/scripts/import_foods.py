"""把 app/db/seeds/foods.json 导入 foods 表。

设计要点：
- 幂等：按 (name, COALESCE(brand,'')) 做 upsert，重复执行不会产生脏数据，
  也不会覆盖已有记录的 source / created_by。
- 校验先行：先把 50 条全部校验完再写库，避免写一半失败留半成品。

用法（cwd = apps/api）：
    python -m scripts.import_foods               # 导入
    python -m scripts.import_foods --dry-run     # 只校验不写库
    python -m scripts.import_foods --path ../xx.json

Render 上无需单独执行：0004 号 Alembic 迁移会自动调用 run_import()。
"""

from __future__ import annotations  # noqa: INP001

import argparse
import json
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal  # noqa: E402
from app.models.enums import FoodSource  # noqa: E402
from app.models.food import Food, build_search_text  # noqa: E402

DEFAULT_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "app" / "db" / "seeds" / "foods.json"
)

#: 每 100g 的营养列，用于统一校验与写入
NUTRIENT_FIELDS: tuple[str, ...] = (
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carb_g",
    "fiber_g",
    "sodium_mg",
)
REQUIRED_FIELDS: tuple[str, ...] = (
    "name",
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carb_g",
)


class SeedValidationError(Exception):
    """种子数据不合法。"""


@dataclass(frozen=True, slots=True)
class SeedFood:
    name: str
    brand: str | None
    energy_kcal: Decimal
    protein_g: Decimal
    fat_g: Decimal
    carb_g: Decimal
    fiber_g: Decimal
    sodium_mg: Decimal
    aliases: tuple[str, ...]
    search_text: str


def _as_decimal(value: object, *, field: str, index: int) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SeedValidationError(
            f"第 {index} 条的 {field} 不是有效数字: {value!r}"
        ) from exc


def _as_text(value: object, *, field: str, index: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_rows(raw: list[dict]) -> list[SeedFood]:
    """把 JSON 原始对象解析并校验成 SeedFood。"""
    parsed: list[SeedFood] = []
    seen: set[tuple[str, str]] = set()

    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise SeedValidationError(f"第 {index} 条不是对象")

        name = _as_text(item.get("name"), field="name", index=index)
        if not name:
            raise SeedValidationError(f"第 {index} 条缺少 name")
        if len(name) > 200:
            raise SeedValidationError(f"第 {index} 条的 name 超过 200 字")

        values: dict[str, Decimal] = {}
        for field in NUTRIENT_FIELDS:
            raw_value = item.get(field)
            if raw_value is None:
                if field in REQUIRED_FIELDS:
                    raise SeedValidationError(f"第 {index} 条缺少必填字段 {field}")
                values[field] = Decimal("0")
                continue
            number = _as_decimal(raw_value, field=field, index=index)
            if number < 0:
                raise SeedValidationError(f"第 {index} 条的 {field} 不能为负")
            values[field] = number

        brand = _as_text(item.get("brand"), field="brand", index=index)
        key = (name, brand or "")
        if key in seen:
            raise SeedValidationError(f"第 {index} 条与前面的记录重复: {key}")
        seen.add(key)

        aliases: list[str] = []
        for alias in item.get("aliases") or []:
            cleaned = _as_text(alias, field="aliases", index=index)
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)

        parsed.append(
            SeedFood(
                name=name,
                brand=brand,
                aliases=tuple(aliases),
                search_text=build_search_text(name, aliases),
                **values,
            )
        )

    return parsed


def load_rows(path: Path = DEFAULT_SEED_PATH) -> list[SeedFood]:
    if not path.exists():
        raise SeedValidationError(f"找不到种子文件: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SeedValidationError("种子文件顶层必须是数组")
    return parse_rows(raw)


def run_import(db: Session, rows: list[SeedFood]) -> tuple[int, int]:
    """执行 upsert，返回 (新增条数, 更新条数)。"""
    created = 0
    updated = 0

    for row in rows:
        stmt = select(Food).where(
            Food.name == row.name,
            func.coalesce(Food.brand, "") == (row.brand or ""),
        )
        food = db.scalar(stmt)

        if food is None:
            food = Food(name=row.name, brand=row.brand)
            db.add(food)
            created += 1
        else:
            updated += 1

        food.energy_kcal = row.energy_kcal
        food.protein_g = row.protein_g
        food.fat_g = row.fat_g
        food.carb_g = row.carb_g
        food.fiber_g = row.fiber_g
        food.sodium_mg = row.sodium_mg
        food.aliases = list(row.aliases)
        food.search_text = row.search_text
        food.source = FoodSource.SEED.value
        food.is_public = True
        food.is_active = True

    return created, updated


def import_foods(
    db: Session,
    path: Path = DEFAULT_SEED_PATH,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """完整流程：读文件 → 校验 → 写入。"""
    rows = load_rows(path)
    if dry_run:
        return 0, 0
    created, updated = run_import(db, rows)
    db.commit()
    return created, updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入种子食物数据")
    parser.add_argument("--path", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        created, updated = import_foods(db, path=args.path, dry_run=args.dry_run)
    except SeedValidationError as exc:
        db.rollback()
        print(f"校验失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if args.dry_run:
        print("校验通过，未写入数据库（--dry-run）")
    else:
        print(f"导入完成：新增 {created} 条，更新 {updated} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
