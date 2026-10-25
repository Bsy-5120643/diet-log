"""导出食物库中「营养字段缺失」的清单，供人工补录。

导入时要求「缺失存 null 不填 0」，这些 NULL 条目如果不追踪就会永远沉在库里。
本脚本把它们捞出来，按「缺得越多越靠前」排序，直接给到运营/营养师去补。

用法（cwd = apps/api）：
    # 控制台表格
    python -m scripts.export_missing_fields

    # 导出 CSV（Excel 可直接打开）
    python -m scripts.export_missing_fields --format csv --output missing.csv

    # 只看影响计算的宏量缺失（蛋白/脂肪/碳水）
    python -m scripts.export_missing_fields --only-macros

    # 只看已被用户记录过的（优先补这些）
    python -m scripts.export_missing_fields --only-used
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.food import Food
from app.models.food_entry import FoodEntry

#: 会参与计算的字段（缺失会导致摄入算不出来）
MACRO_FIELDS: tuple[str, ...] = ("protein_g", "fat_g", "carb_g")

#: 仅作展示的参考字段
OPTIONAL_FIELDS: tuple[str, ...] = ("fiber_g", "sodium_mg")

ALL_FIELDS: tuple[str, ...] = MACRO_FIELDS + OPTIONAL_FIELDS

FIELD_LABELS: dict[str, str] = {
    "protein_g": "蛋白质",
    "fat_g": "脂肪",
    "carb_g": "碳水",
    "fiber_g": "膳食纤维",
    "sodium_mg": "钠",
}


def collect(
    db: Session,
    *,
    only_macros: bool = False,
    only_used: bool = False,
) -> list[dict[str, object]]:
    """捞出有缺失字段的食物。"""
    fields = MACRO_FIELDS if only_macros else ALL_FIELDS

    query = select(Food).where(Food.is_active.is_(True))
    foods = list(db.scalars(query))

    # 统计每个食物被记录了多少次（用于 only_used 过滤 + 优先级排序）
    usage: dict[object, int] = dict(
        db.execute(
            select(FoodEntry.food_id, func.count(FoodEntry.id)).group_by(
                FoodEntry.food_id
            )
        ).all()
    )

    rows: list[dict[str, object]] = []
    for food in foods:
        missing = [field for field in fields if getattr(food, field) is None]
        if not missing:
            continue

        used_count = int(usage.get(food.id, 0))
        if only_used and used_count == 0:
            continue

        rows.append(
            {
                "id": str(food.id),
                "name": food.name,
                "brand": food.brand or "",
                "source": food.source,
                "missing_fields": missing,
                # 中文标签，方便非技术同学看
                "missing_labels": [FIELD_LABELS.get(f, f) for f in missing],
                "missing_count": len(missing),
                # 缺宏量会直接影响计算，权重更高
                "blocks_calculation": any(f in MACRO_FIELDS for f in missing),
                "used_count": used_count,
                "energy_kcal": float(food.energy_kcal) if food.energy_kcal else None,
            }
        )

    # 排序：先看是否阻断计算，再看被记录次数，最后看缺失数量
    rows.sort(
        key=lambda r: (
            not bool(r["blocks_calculation"]),
            -int(r["used_count"]),
            -int(r["missing_count"]),
            str(r["name"]),
        )
    )
    return rows


def render_table(rows: list[dict[str, object]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["食物", "品牌", "缺字段", "缺数量", "阻断计算", "被记录次数", "热量(kcal/100g)"]
    )
    for row in rows:
        writer.writerow(
            [
                row["name"],
                row["brand"],
                "/".join(str(x) for x in row["missing_labels"]),
                row["missing_count"],
                "是" if row["blocks_calculation"] else "否",
                row["used_count"],
                row["energy_kcal"],
            ]
        )
    return buf.getvalue()


def render_csv(rows: list[dict[str, object]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "食物", "品牌", "来源", "缺失字段", "缺失数量", "阻断计算", "被记录次数", "热量"]
    )
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["name"],
                row["brand"],
                row["source"],
                "/".join(str(x) for x in row["missing_fields"]),
                row["missing_count"],
                "是" if row["blocks_calculation"] else "否",
                row["used_count"],
                row["energy_kcal"],
            ]
        )
    return buf.getvalue()


def summary_text(rows: list[dict[str, object]]) -> str:
    total = len(rows)
    blocking = sum(1 for r in rows if r["blocks_calculation"])
    by_field: dict[str, int] = {}
    for row in rows:
        for field in row["missing_fields"]:  # type: ignore[union-attr]
            by_field[str(field)] = by_field.get(str(field), 0) + 1

    lines = [
        "",
        "=========== 缺失字段清单 ===========",
        "有缺失的食物数 : " + str(total),
        "其中阻断计算   : " + str(blocking) + "（缺蛋白/脂肪/碳水，无法算摄入）",
        "",
        "各字段缺失数:",
    ]
    for field in ALL_FIELDS:
        label = FIELD_LABELS.get(field, field)
        lines.append("  " + label + " (" + field + "): " + str(by_field.get(field, 0)))
    lines.append("====================================")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导出营养字段缺失清单")
    parser.add_argument(
        "--format", choices=("table", "csv", "json"), default="table"
    )
    parser.add_argument("--output", type=Path, help="输出到文件，省略则打印到控制台")
    parser.add_argument("--only-macros", action="store_true", help="只看宏量缺失")
    parser.add_argument("--only-used", action="store_true", help="只看被记录过的")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = collect(
            db, only_macros=args.only_macros, only_used=args.only_used
        )
    finally:
        db.close()

    if args.format == "json":
        payload = json.dumps(rows, ensure_ascii=False, indent=2)
    elif args.format == "csv":
        payload = render_csv(rows)
    else:
        payload = render_table(rows)

    report = summary_text(rows) + "\n\n" + payload

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print("已写入 " + str(args.output))
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
