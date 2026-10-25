"""《中国食物成分表》导入脚本测试。

重点锁定一条语义：**0 是真实测量值，「未知」是 None，两者绝不混淆。**
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.food import Food
from app.models.food_entry import FoodEntry

from scripts.import_cn_foods import (
    DEDUPE_MERGE,
    DEDUPE_OVERWRITE,
    DEDUPE_SKIP,
    CleanFood,
    apply_per_100g,
    clean_record,
    dedupe_in_file,
    load_json,
    parse_number,
    to_per_100g,
)


# ---------------------------------------------------------------------------
# 数值解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_value, expect_missing",
    [
        (None, None, True),
        ("", None, True),
        ("-", None, True),
        ("—", None, True),
        ("Tr", None, True),
        ("tr", None, True),
        ("痕量", None, True),
        ("未检出", None, True),
        ("N/A", None, True),
        ("abc", None, True),
        (0, Decimal("0"), False),          # 真实 0，必须保留
        ("0", Decimal("0"), False),
        (133, Decimal("133"), False),
        ("12.1", Decimal("12.1"), False),  # 字符串数字
        ("19.4g", Decimal("19.4"), False),  # 带单位
        ("1,234", Decimal("1234"), False),  # 千分位
        ("<0.1", Decimal("0.1"), False),   # 检测限取上限
        ("10~20", Decimal("10"), False),   # 范围取下限
    ],
)
def test_parse_number(raw, expected_value, expect_missing):
    value, _warning = parse_number(raw)
    if expect_missing:
        assert value is None, f"{raw!r} 应视为未知"
    else:
        assert value == expected_value


def test_parse_number_rejects_bool():
    """bool 是 int 子类，必须拦掉，否则 True 会变成 1。"""
    value, warning = parse_number(True)
    assert value is None
    assert warning


def test_zero_and_unknown_are_distinct():
    """0 与 None 语义不同 —— 这是本脚本最重要的约定。"""
    zero, _ = parse_number(0)
    unknown, _ = parse_number("—")

    assert zero is not None
    assert zero == 0
    assert unknown is None


# ---------------------------------------------------------------------------
# 字段名清洗
# ---------------------------------------------------------------------------


def test_field_name_variants():
    """energy / energy_kcal / 能量 / 能量(kcal) 都应映射到同一个字段。"""
    variants = [
        {"food_name": "A", "energy_kcal": 100},
        {"food_name": "A", "energy": 100},
        {"名称": "A", "能量": 100},
        {"food_name": "A", "能量(kcal)": 100},
        {"food_name": "A", "Energy_Kcal": 100},
    ]
    for raw in variants:
        food = clean_record(raw)
        assert food.energy_kcal == Decimal("100"), f"未识别: {raw}"


def test_string_numbers_are_parsed():
    food = clean_record(
        {
            "food_name": "干木耳",
            "energy": 265,
            "protein_g": "12.1",
            "fat_g": "1.5",
            "carb_g": "65.6",
            "fiber_g": "29.9",
            "sodium_mg": "48.5",
        }
    )
    assert food.energy_kcal == Decimal("265")
    assert food.protein_g == Decimal("12.1")
    assert food.fiber_g == Decimal("29.9")


def test_kj_is_converted_to_kcal():
    """kJ 必须除以 4.184，否则热量会差 4 倍。"""
    food = clean_record({"food_name": "X", "energy_kj": Decimal("418.4")})
    assert food.energy_kcal == Decimal("100.00")


def test_missing_markers_become_none_not_zero():
    food = clean_record(
        {
            "food_name": "精制盐",
            "energy_kcal": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carb_g": 0,
            "fiber_g": "—",
            "sodium_mg": 39311,
        }
    )
    assert food.energy_kcal == Decimal("0")  # 真实 0
    assert food.fiber_g is None              # 未知 -> None，不是 0


def test_aliases_from_string_or_list():
    assert clean_record({"food_name": "A", "aliases": "番茄/西红柿"}).aliases == [
        "番茄",
        "西红柿",
    ]
    assert clean_record({"food_name": "A", "aliases": ["a", "b"]}).aliases == ["a", "b"]


# ---------------------------------------------------------------------------
# 每 100g 归一
# ---------------------------------------------------------------------------


def test_to_per_100g_from_serving():
    assert to_per_100g(Decimal("50"), serving_size_g=Decimal("200")) == Decimal("25.00")


def test_to_per_100g_from_market_weight():
    assert to_per_100g(Decimal("50"), edible_pct=Decimal("50")) == Decimal("100.00")


def test_to_per_100g_keeps_none():
    assert to_per_100g(None, serving_size_g=Decimal("200")) is None


def test_apply_per_100g_scales_all_fields():
    food = CleanFood(
        name="A",
        brand=None,
        energy_kcal=Decimal("50"),
        protein_g=Decimal("10"),
        fat_g=Decimal("5"),
        carb_g=Decimal("20"),
        fiber_g=None,
        sodium_mg=Decimal("100"),
    )
    apply_per_100g(food, serving_size_g=Decimal("200"))
    assert food.energy_kcal == Decimal("25.00")
    assert food.protein_g == Decimal("5.00")
    assert food.fiber_g is None


# ---------------------------------------------------------------------------
# 去重
# ---------------------------------------------------------------------------


def _dup_rows() -> list[CleanFood]:
    def make(name: str, energy: str | None, protein: str | None) -> CleanFood:
        return CleanFood(
            name=name,
            brand=None,
            energy_kcal=Decimal(energy) if energy else None,
            protein_g=Decimal(protein) if protein else None,
            fat_g=None,
            carb_g=None,
            fiber_g=None,
            sodium_mg=None,
        )

    return [
        make("鸡胸肉", "133", None),   # 缺蛋白
        make("鸡胸肉", "120", "24.6"),  # 完整
    ]


def test_dedupe_skip_keeps_first():
    kept, duplicates = dedupe_in_file(_dup_rows(), DEDUPE_SKIP)
    assert duplicates == 1
    assert len(kept) == 1
    assert kept[0].energy_kcal == Decimal("133")


def test_dedupe_overwrite_keeps_last():
    kept, _ = dedupe_in_file(_dup_rows(), DEDUPE_OVERWRITE)
    assert kept[0].energy_kcal == Decimal("120")


def test_dedupe_merge_fills_nulls():
    """merge 用后来的补上前面的 null，已有值不动。"""
    kept, _ = dedupe_in_file(_dup_rows(), DEDUPE_MERGE)
    assert kept[0].energy_kcal == Decimal("133")   # 已有值保留
    assert kept[0].protein_g == Decimal("24.6")    # null 被补上


def test_dedupe_key_ignores_whitespace_and_case():
    a = CleanFood(name="鸡 胸肉 ", brand=None, energy_kcal=None, protein_g=None,
                  fat_g=None, carb_g=None, fiber_g=None, sodium_mg=None)
    b = CleanFood(name="鸡胸肉", brand=None, energy_kcal=None, protein_g=None,
                  fat_g=None, carb_g=None, fiber_g=None, sodium_mg=None)
    assert a.dedupe_key() == b.dedupe_key()


# ---------------------------------------------------------------------------
# 文件读取
# ---------------------------------------------------------------------------


def test_load_json_array(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps([{"food_name": "A"}]), encoding="utf-8")
    assert len(load_json(path)) == 1


def test_load_json_wrapped(tmp_path):
    path = tmp_path / "b.json"
    path.write_text(json.dumps({"data": [{"food_name": "A"}]}), encoding="utf-8")
    assert len(load_json(path)) == 1


def test_load_json_missing_file():
    from pathlib import Path

    with pytest.raises(FileNotFoundError):
        load_json(Path("nope.json"))


# ---------------------------------------------------------------------------
# 入库
# ---------------------------------------------------------------------------


def test_run_import_preserves_nulls(db_session):
    """缺失值写库后仍是 NULL，绝不能变成 0。"""
    from scripts.import_cn_foods import run_import

    rows = [
        clean_record(
            {
                "food_name": "缺纤维食物",
                "energy_kcal": 100,
                "protein_g": 5,
                "fat_g": 1,
                "carb_g": 10,
                "fiber_g": "—",
                "sodium_mg": 20,
            }
        )
    ]
    stats, inserted_ids = run_import(db_session, rows)

    assert stats.inserted == 1
    assert len(inserted_ids) == 1

    food = db_session.get(Food, uuid.UUID(inserted_ids[0]))
    assert food.fiber_g is None
    assert db_session.scalar(
        select(func.count()).select_from(Food).where(Food.fiber_g.is_(None))
    ) == 1


def test_run_import_skips_missing_energy(db_session):
    """能量是 null 的条目必须跳过，不写库。"""
    from scripts.import_cn_foods import run_import

    rows = [clean_record({"food_name": "无能量", "energy_kcal": "Tr"})]
    stats, inserted_ids = run_import(db_session, rows)

    assert stats.inserted == 0
    assert stats.skipped_missing_required == 1
    assert inserted_ids == []


def test_run_import_is_idempotent(db_session):
    """重复导入同一批数据不应产生重复行。"""
    from scripts.import_cn_foods import run_import

    rows = [clean_record({"food_name": "重复测试", "energy_kcal": 100})]
    run_import(db_session, rows)
    stats, _ = run_import(db_session, rows)

    assert stats.inserted == 0
    assert stats.skipped_duplicate_in_db == 1
    assert db_session.scalar(select(func.count()).select_from(Food)) == 1


def test_rollback_soft_deletes_when_referenced(db_session, tmp_path):
    """有饮食记录引用时，回滚必须软删除，不能破坏历史。"""
    from decimal import Decimal

    from scripts.import_cn_foods import rollback, run_import

    rows = [clean_record({"food_name": "被引用食物", "energy_kcal": 100,
                          "protein_g": 5, "fat_g": 1, "carb_g": 10})]
    _stats, inserted_ids = run_import(db_session, rows)
    food_id = uuid.UUID(inserted_ids[0])

    db_session.add(
        FoodEntry(
            user_id=uuid.uuid4(),
            food_id=food_id,
            entry_date=__import__("datetime").date.today(),
            meal_type="lunch",
            quantity_g=Decimal("100"),
            snapshot_energy_kcal=Decimal("100"),
            snapshot_protein_g=Decimal("5"),
            snapshot_fat_g=Decimal("1"),
            snapshot_carb_g=Decimal("10"),
            energy_kcal=Decimal("100"),
            protein_g=Decimal("5"),
            fat_g=Decimal("1"),
            carb_g=Decimal("10"),
        )
    )
    db_session.commit()

    report = tmp_path / "report.json"
    report.write_text(json.dumps({"inserted_ids": inserted_ids}), encoding="utf-8")

    rollback(db_session, report)

    food = db_session.get(Food, food_id)
    assert food is not None          # 没被物理删
    assert food.is_active is False   # 软删除
    assert db_session.scalar(select(func.count()).select_from(FoodEntry)) == 1
