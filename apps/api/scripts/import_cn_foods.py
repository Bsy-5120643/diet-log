"""把《中国食物成分表》整理后的 JSON 导入 foods 表。

核心原则：**0 与「未知」是两回事，绝不互相转换。**
- 精制盐 energy_kcal=0 是真实测量值
- 生菜 fiber_g=null、精制盐 fiber_g="—" 是「未检测」
- 混为一谈会让汇总失真

用法（cwd = apps/api）：
    # 先看清洗结果，不写库
    python -m scripts.import_cn_foods --file data/cn_foods.json --dry-run

    # 正式导入
    python -m scripts.import_cn_foods --file data/cn_foods.json

    # 回滚某次导入
    python -m scripts.import_cn_foods --rollback import_report_20261025_113000.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

KCAL_PER_KJ_DIVISOR = Decimal("4.184")

#: 表示「未检测 / 未知」的标记（统一小写后比对）
MISSING_TOKENS: frozenset[str] = frozenset(
    {
        "",
        "-",
        "—",
        "–",
        "tr",
        "trace",
        "痕量",
        "未检出",
        "未检测",
        "n/a",
        "na",
        "null",
        "none",
    }
)

#: 数值里可能夹带的单位后缀
_UNIT_RE = re.compile(
    r"(kcal|kj|千卡|千焦|大卡|卡|g|克|mg|毫克|μg|微克|%)",
    re.IGNORECASE,
)

_LEADING_LT_RE = re.compile(r"^[<≤]\s*")

#: 规范字段名 -> 原始 JSON 里可能出现的所有写法
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": (
        "food_name", "foodname", "name", "名称", "食物名称", "食物名", "食品名称",
    ),
    "brand": ("brand", "brand_name", "品牌", "生产厂家"),
    "energy_kcal": (
        "energy_kcal", "kcal", "energy", "能量", "热量", "千卡", "大卡",
    ),
    "energy_kj": ("energy_kj", "kj", "千焦"),
    "protein_g": ("protein_g", "protein", "蛋白质", "蛋白"),
    "fat_g": ("fat_g", "fat", "脂肪"),
    "carb_g": ("carb_g", "carb", "carbohydrate", "碳水化合物", "碳水"),
    "fiber_g": ("fiber_g", "fiber", "dietary_fiber", "膳食纤维", "纤维", "不溶性膳食纤维"),
    "sodium_mg": ("sodium_mg", "sodium", "钠"),
    "aliases": ("aliases", "别名", "常用名"),
}

#: 关键字段：缺失则跳过该条
REQUIRED_FIELDS: tuple[str, ...] = ("name", "energy_kcal")

#: 宏量营养素：缺失时存 null（需 schema 允许）
MACRO_FIELDS: tuple[str, ...] = ("protein_g", "fat_g", "carb_g")

#: 可选字段
OPTIONAL_FIELDS: tuple[str, ...] = ("fiber_g", "sodium_mg")

#: 需要参与「每 100g 归一」的数值字段
NUMERIC_FIELDS: tuple[str, ...] = (
    "energy_kcal",
    "protein_g",
    "fat_g",
    "carb_g",
    "fiber_g",
    "sodium_mg",
)


def _normalize_key(raw: str) -> str:
    """把各种写法的字段名压成规范形式。

    处理全角括号、大小写、分隔符、后缀单位。
    例：「能量(kcal)」「 Energy_Kcal 」「energy_kcal」→ energy_kcal
    """
    key = str(raw).strip().lower()
    key = key.translate(str.maketrans("（）", "()"))
    key = re.sub(r"\(.*?\)", "", key)   # 去掉括号及内部单位
    key = re.sub(r"[\s\-/.]+", "_", key)  # 分隔符统一成 _
    key = re.sub(r"_+", "_", key).strip("_")
    return key


_ALIAS_LOOKUP: dict[str, str] = {
    _normalize_key(alias): canonical
    for canonical, aliases in FIELD_ALIASES.items()
    for alias in aliases
}


def normalize_text(value: object) -> str:
    """去掉全部空白，用于名称比对去重。"""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value)).strip()


def parse_number(value: object) -> tuple[Decimal | None, str | None]:
    """把原始值解析成 Decimal，返回 (值, 警告)。

    语义约定：
    - None / 空串 / "-" / "—" / "未检出" / "N/A" → (None, None)，表示「未知」
    - 0 与 "0" → (Decimal("0"), None)，这是真实测量值
    - "<0.1" → (0.1, 提示)，检测限的上限是已知信息，比填 0 更接近真相
    - "19.4g" → 剥离单位后解析
    - "10~20" → 取下限并提示
    - 其它无法解析 → (None, "无法解析")
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        # bool 是 int 子类，必须先排除，否则 True 会变成 Decimal("1")
        return None, f"布尔值不能作为营养值: {value!r}"
    if isinstance(value, Decimal):
        return value, None
    if isinstance(value, (int, float)):
        return Decimal(str(value)), None

    text = str(value).strip()
    if text.lower() in MISSING_TOKENS:
        return None, None

    warning: str | None = None

    if _LEADING_LT_RE.match(text):
        text = _LEADING_LT_RE.sub("", text)
        warning = "低于检测限，按上限记录"

    # 范围值取下限
    if "~" in text or "～" in text:
        text = re.split(r"[~～]", text)[0]
        warning = (warning + "；" if warning else "") + "范围值，按下限记录"

    cleaned = _UNIT_RE.sub("", text).replace(",", "").strip()
    if not cleaned:
        return None, warning or "空值"

    try:
        return Decimal(cleaned), warning
    except InvalidOperation:
        return None, warning or "无法解析为数字"


# ---------------------------------------------------------------------------
# 记录清洗
# ---------------------------------------------------------------------------


@dataclass
class CleanFood:
    """清洗后的一条食物。None 一律表示「未知」，不要和 0 混淆。"""

    name: str
    brand: str | None
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carb_g: Decimal | None
    fiber_g: Decimal | None
    sodium_mg: Decimal | None
    aliases: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def dedupe_key(self) -> tuple[str, str]:
        return (normalize_text(self.name).lower(), normalize_text(self.brand).lower())


def clean_record(raw: dict[str, Any]) -> CleanFood:
    """把一条原始记录清洗成规范结构。"""
    if not isinstance(raw, dict):
        raise ValueError("记录不是对象")

    resolved: dict[str, Any] = {}
    warnings: list[str] = []

    for key, value in raw.items():
        canonical = _ALIAS_LOOKUP.get(_normalize_key(str(key)))
        if canonical is None:
            continue
        if canonical in ("name", "brand"):
            if value is not None:
                resolved[canonical] = str(value).strip()
        elif canonical == "aliases":
            resolved[canonical] = _parse_aliases(value)
        else:
            number, warning = parse_number(value)
            resolved[canonical] = number
            if warning:
                warnings.append(str(key) + "=" + repr(value) + ": " + warning)

    kcal = resolved.get("energy_kcal")
    kj = resolved.get("energy_kj")
    if kcal is None and kj is not None:
        kcal = (kj / KCAL_PER_KJ_DIVISOR).quantize(Decimal("0.01"))
        warnings.append("能量由 kJ 换算: " + str(kj) + " kJ -> " + str(kcal) + " kcal")

    name = str(resolved.get("name") or "").strip()
    brand_raw = resolved.get("brand") or ""
    brand = str(brand_raw).strip() if brand_raw else None

    return CleanFood(
        name=name,
        brand=brand,
        energy_kcal=kcal,
        protein_g=resolved.get("protein_g"),
        fat_g=resolved.get("fat_g"),
        carb_g=resolved.get("carb_g"),
        fiber_g=resolved.get("fiber_g"),
        sodium_mg=resolved.get("sodium_mg"),
        aliases=resolved.get("aliases") or [],
        warnings=warnings,
    )


def _parse_aliases(value: object) -> list[str]:
    """别名可能是数组，也可能是用 / 、 , 分隔的字符串。"""
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        items = re.split(r"[/、,，;；|]", text)

    seen: list[str] = []
    for item in items:
        cleaned = str(item).strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def to_per_100g(
    value: Decimal | None,
    *,
    serving_size_g: Decimal | None = None,
    edible_pct: Decimal | None = None,
) -> Decimal | None:
    """把数值统一折算到「每 100g 可食部」。

    支持三种原始口径（按优先级）：
    1. serving_size_g：按份计 → value * 100 / 份量克数
    2. edible_pct：按市品计 → value * 100 / 食部百分比
    3. 都不传：默认已经是每 100g
    """
    if value is None:
        return None
    if serving_size_g and serving_size_g > 0:
        return (value * Decimal("100") / serving_size_g).quantize(Decimal("0.01"))
    if edible_pct and edible_pct > 0:
        return (value * Decimal("100") / edible_pct).quantize(Decimal("0.01"))
    return value


def apply_per_100g(
    food: CleanFood,
    *,
    serving_size_g: Decimal | None = None,
    edible_pct: Decimal | None = None,
) -> CleanFood:
    """对一条记录的所有数值字段统一折算。"""
    for name in NUMERIC_FIELDS:
        current = getattr(food, name)
        setattr(
            food,
            name,
            to_per_100g(current, serving_size_g=serving_size_g, edible_pct=edible_pct),
        )
    return food


def load_json(path: Path) -> list[dict[str, Any]]:
    """读 JSON 文件。顶层可以是数组，也可以是 {data: [...]} / {foods: [...]}。"""
    if not path.exists():
        raise FileNotFoundError("找不到文件: " + str(path))

    payload = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("data", "foods", "items", "list", "食物列表", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        raise ValueError(
            "JSON 顶层是对象但没找到数组字段，可用键: data / foods / items / list / results"
        )

    raise ValueError("JSON 顶层必须是数组或对象，当前: " + type(payload).__name__)


# ---------------------------------------------------------------------------
# 去重
# ---------------------------------------------------------------------------

#: 去重策略
DEDUPE_SKIP = "skip"
DEDUPE_OVERWRITE = "overwrite"
DEDUPE_MERGE = "merge"
DEDUPE_STRATEGIES = (DEDUPE_SKIP, DEDUPE_OVERWRITE, DEDUPE_MERGE)


def merge_food(base: CleanFood, incoming: CleanFood) -> CleanFood:
    """用 incoming 补上 base 里为 None 的字段，已有值不动。"""
    for name in NUMERIC_FIELDS:
        if getattr(base, name) is None and getattr(incoming, name) is not None:
            setattr(base, name, getattr(incoming, name))
    for alias in incoming.aliases:
        if alias not in base.aliases:
            base.aliases.append(alias)
    return base


def dedupe_in_file(
    rows: list[CleanFood],
    strategy: str = DEDUPE_SKIP,
) -> tuple[list[CleanFood], int]:
    """文件内去重，返回 (保留的记录, 重复条数)。

    - skip      : 保留先出现的一条（种子数据幂等，我建议用这个）
    - overwrite : 后出现的覆盖先出现的
    - merge     : 用后来的补上前面为 null 的字段
    """
    kept: dict[tuple[str, str], CleanFood] = {}
    duplicates = 0

    for row in rows:
        key = row.dedupe_key()
        if key not in kept:
            kept[key] = row
            continue
        duplicates += 1
        if strategy == DEDUPE_OVERWRITE:
            kept[key] = row
        elif strategy == DEDUPE_MERGE:
            kept[key] = merge_food(kept[key], row)
        # DEDUPE_SKIP: 保留先出现的，什么都不做

    return list(kept.values()), duplicates


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


@dataclass
class ImportStats:
    total: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_missing_required: int = 0
    skipped_duplicate_in_file: int = 0
    skipped_duplicate_in_db: int = 0
    missing_by_field: Counter = field(default_factory=Counter)
    warnings: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "",
            "=============== 导入统计 ===============",
            "读取总数           : " + str(self.total),
            "成功写入           : " + str(self.inserted),
            "覆盖更新           : " + str(self.updated),
            "文件内重复跳过     : " + str(self.skipped_duplicate_in_file),
            "数据库中已存在跳过 : " + str(self.skipped_duplicate_in_db),
            "缺失关键字段跳过   : " + str(self.skipped_missing_required),
            "",
            "各字段缺失条数（存为 null，非 0）:",
        ]
        for name in NUMERIC_FIELDS:
            lines.append("  " + name + ": " + str(self.missing_by_field.get(name, 0)))
        lines.append("========================================")
        return "\n".join(lines)

def _assign(food, row: CleanFood, search_text: str) -> None:
    food.name = row.name
    food.brand = row.brand
    food.energy_kcal = row.energy_kcal
    food.protein_g = row.protein_g
    food.fat_g = row.fat_g
    food.carb_g = row.carb_g
    food.fiber_g = row.fiber_g
    food.sodium_mg = row.sodium_mg
    food.aliases = list(row.aliases)
    food.search_text = search_text
    food.is_public = True
    food.is_active = True


def run_import(
    db: Session,
    rows: list[CleanFood],
    *,
    strategy: str = DEDUPE_SKIP,
    source: str = "seed",
    batch_size: int = 100,
) -> tuple[ImportStats, list[str]]:
    """批量写入 foods 表，返回 (统计, 本次新增的 id 列表)。"""
    from app.models.food import Food, build_search_text

    stats = ImportStats(total=len(rows))
    inserted_ids: list[str] = []

    # 一次性加载已有的 (name, brand) 索引，避免逐条查询
    existing: dict[tuple[str, str], object] = {}
    for food in db.scalars(select(Food)):
        key = (normalize_text(food.name).lower(), normalize_text(food.brand).lower())
        existing[key] = food

    for row in rows:
        # 关键字段缺失 -> 跳过（不写库、不填 0）
        if not row.name:
            stats.skipped_missing_required += 1
            continue
        if row.energy_kcal is None:
            stats.skipped_missing_required += 1
            stats.missing_by_field["energy_kcal"] += 1
            continue

        for name in NUMERIC_FIELDS:
            if getattr(row, name) is None:
                stats.missing_by_field[name] += 1
        for warning in row.warnings:
            stats.warnings.append((row.name, warning))

        key = row.dedupe_key()
        current = existing.get(key)

        if current is not None:
            if strategy == DEDUPE_SKIP:
                stats.skipped_duplicate_in_db += 1
                continue

            if strategy == DEDUPE_MERGE:
                changed = False
                for name in NUMERIC_FIELDS:
                    if getattr(current, name) is None and getattr(row, name) is not None:
                        setattr(current, name, getattr(row, name))
                        changed = True
                for alias in row.aliases:
                    if alias not in (current.aliases or []):
                        current.aliases = list(current.aliases or []) + [alias]
                        changed = True
                if changed:
                    current.search_text = build_search_text(
                        current.name, list(current.aliases or [])
                    )
                    stats.updated += 1
                else:
                    stats.skipped_duplicate_in_db += 1
                continue

            _assign(current, row, build_search_text(row.name, row.aliases))
            current.source = source
            stats.updated += 1
            continue

        food = Food(id=uuid.uuid4(), source=source)
        _assign(food, row, build_search_text(row.name, row.aliases))
        db.add(food)
        existing[key] = food
        inserted_ids.append(str(food.id))
        stats.inserted += 1

        if len(inserted_ids) % batch_size == 0:
            db.flush()

    db.commit()
    return stats, inserted_ids


def write_report(path: Path, inserted_ids: list[str], source: str) -> None:
    """写回滚报告 —— 回滚全靠这个文件里的 id 清单。"""
    report = {
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "source": source,
        "inserted_count": len(inserted_ids),
        "inserted_ids": inserted_ids,
    }
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------------------------------------------------------------------------
# 回滚
# ---------------------------------------------------------------------------


def rollback(db: Session, report_path: Path, *, force: bool = False) -> int:
    """按报告回滚一次导入。

    策略（关键）：
    - 这批食物还没有任何 food_entries 引用 -> 物理删除，最干净
    - 已经有人基于它们记录了饮食 -> 只能软删除（is_active=false）
      因为 food_entries.food_id 是 ON DELETE RESTRICT，物理删会破坏历史记录

    force=True 时先删掉关联的 food_entries 再删 foods —— 会丢失用户记录，谨慎。
    """
    import uuid as _uuid

    from app.models.food import Food
    from app.models.food_entry import FoodEntry

    report = json.loads(report_path.read_text(encoding="utf-8"))
    raw_ids = report.get("inserted_ids") or []
    ids = [_uuid.UUID(value) for value in raw_ids]

    if not ids:
        print("报告里没有可回滚的 id")
        return 0

    referenced = db.scalar(
        select(func.count())
        .select_from(FoodEntry)
        .where(FoodEntry.food_id.in_(ids))
    ) or 0

    if referenced and not force:
        # 已被引用 -> 软删除，保留历史记录可追溯
        result = db.execute(
            Food.__table__.update()
            .where(Food.__table__.c.id.in_(ids))
            .values(is_active=False)
        )
        db.commit()
        print(
            "检测到 "
            + str(referenced)
            + " 条饮食记录引用了这批食物，已执行**软删除**（is_active=false）"
        )
        print("软删除条数: " + str(result.rowcount))
        print("历史记录不受影响。若确需物理删除，加 --force（会连带删除这些记录）")
        return result.rowcount or 0

    if referenced and force:
        deleted_entries = db.execute(
            FoodEntry.__table__.delete().where(FoodEntry.__table__.c.food_id.in_(ids))
        )
        db.commit()
        print("警告：已删除 " + str(deleted_entries.rowcount) + " 条饮食记录")

    result = db.execute(Food.__table__.delete().where(Food.__table__.c.id.in_(ids)))
    db.commit()
    print("物理删除 foods 条数: " + str(result.rowcount))
    return result.rowcount or 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="导入《中国食物成分表》JSON")
    parser.add_argument("--file", type=Path, help="JSON 文件路径")
    parser.add_argument("--rollback", type=Path, help="回滚报告文件路径")
    parser.add_argument(
        "--dedupe",
        choices=list(DEDUPE_STRATEGIES),
        default=DEDUPE_SKIP,
        help="去重策略，默认 skip（保留先出现的一条）",
    )
    parser.add_argument("--source", default="seed", help="写入 foods.source 的值")
    parser.add_argument("--dry-run", action="store_true", help="只清洗不写库")
    parser.add_argument("--report", type=Path, help="回滚报告输出路径")
    parser.add_argument("--force", action="store_true", help="回滚时允许物理删除")
    parser.add_argument("--serving-size-g", type=Decimal, help="若原始值按份计，填份量克数")
    parser.add_argument("--edible-pct", type=Decimal, help="若原始值按市品计，填食部百分比")
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        if args.rollback:
            rollback(db, args.rollback, force=args.force)
            return 0

        if args.file is None:
            parser.error("需要 --file 或 --rollback")

        raw_rows = load_json(args.file)
        cleaned = [clean_record(row) for row in raw_rows]
        cleaned = [
            apply_per_100g(
                row,
                serving_size_g=args.serving_size_g,
                edible_pct=args.edible_pct,
            )
            for row in cleaned
        ]

        kept, duplicates = dedupe_in_file(cleaned, args.dedupe)

        if args.dry_run:
            stats = ImportStats(total=len(raw_rows))
            stats.skipped_duplicate_in_file = duplicates
            for row in kept:
                if not row.name or row.energy_kcal is None:
                    stats.skipped_missing_required += 1
                    continue
                for name in NUMERIC_FIELDS:
                    if getattr(row, name) is None:
                        stats.missing_by_field[name] += 1
                for warning in row.warnings:
                    stats.warnings.append((row.name, warning))
            print(stats.summary())
            print()
            print("---- 清洗预览（前 5 条）----")
            for row in kept[:5]:
                print(json.dumps(_preview(row), ensure_ascii=False, indent=2))
            return 0

        stats, inserted_ids = run_import(
            db, kept, strategy=args.dedupe, source=args.source
        )
        stats.skipped_duplicate_in_file = duplicates
        print(stats.summary())

        report_path = args.report or Path(
            "import_report_"
            + datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
        write_report(report_path, inserted_ids, args.source)
        print()
        print("回滚报告: " + str(report_path))
        print("回滚命令: python -m scripts.import_cn_foods --rollback " + str(report_path))
        return 0
    finally:
        db.close()


def _preview(row: CleanFood) -> dict[str, Any]:
    return {
        "name": row.name,
        "brand": row.brand,
        "energy_kcal": None if row.energy_kcal is None else float(row.energy_kcal),
        "protein_g": None if row.protein_g is None else float(row.protein_g),
        "fat_g": None if row.fat_g is None else float(row.fat_g),
        "carb_g": None if row.carb_g is None else float(row.carb_g),
        "fiber_g": None if row.fiber_g is None else float(row.fiber_g),
        "sodium_mg": None if row.sodium_mg is None else float(row.sodium_mg),
        "aliases": row.aliases,
        "warnings": row.warnings,
    }


if __name__ == "__main__":
    raise SystemExit(main())
