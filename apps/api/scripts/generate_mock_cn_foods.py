"""生成《中国食物成分表》风格的 100 条模拟数据。

刻意混入真实会遇到的脏数据形态：
- 字段名不统一：energy_kcal / energy / 能量 / 能量(kcal)
- 数值类型混用：数字 / 字符串
- 缺失标记：null / "-" / "—" / "Tr" / "未检出" / "<0.1"
- kJ 单位（第 61~65 条），验证换算
- 重复名称（第 96、97 条），验证去重
- 完全无能量（第 98 条），验证关键字段跳过

用法（cwd = apps/api）：
    python -m scripts.generate_mock_cn_foods --output app/db/seeds/cn_foods_mock_100.json
"""

from __future__ import annotations

import argparse
import json
import random
from decimal import Decimal
from pathlib import Path


def _build_rows() -> list[dict[str, object]]:
    rnd = random.Random(20261025)  # 固定种子，结果可复现

    categories: dict[str, list[tuple[str, float, float, float, float]]] = {
        "谷物": [
            ("米饭", 116, 2.6, 0.3, 25.9), ("馒头", 223, 7.0, 1.1, 47.0),
            ("面条", 110, 2.7, 0.2, 24.3), ("全麦面包", 250, 9.0, 3.2, 45.0),
            ("燕麦片", 377, 15.0, 6.7, 61.6), ("小米", 361, 9.0, 3.1, 75.1),
            ("玉米面", 341, 8.1, 3.3, 69.6), ("荞麦面", 337, 11.3, 2.8, 66.5),
            ("糙米", 348, 7.7, 2.7, 74.3), ("糯米", 350, 7.3, 1.0, 78.3),
            ("薏米", 357, 12.8, 3.3, 71.1), ("高粱米", 351, 10.4, 3.1, 74.7),
        ],
        "薯类": [
            ("红薯", 99, 1.6, 0.2, 23.0), ("马铃薯", 76, 2.0, 0.2, 17.2),
            ("山药", 56, 1.9, 0.2, 12.4), ("芋头", 79, 2.2, 0.2, 18.1),
            ("木薯", 116, 2.1, 0.3, 27.8),
        ],
        "禽肉": [
            ("鸡胸肉", 133, 19.4, 5.0, 2.5), ("鸡腿", 146, 20.0, 7.2, 0.8),
            ("鸡翅", 194, 17.4, 11.8, 4.6), ("鸭肉", 240, 15.5, 19.7, 0.2),
            ("鹅肉", 251, 17.9, 19.9, 0.0), ("火鸡胸肉", 103, 22.4, 0.2, 0.6),
        ],
        "畜肉": [
            ("猪里脊", 155, 20.2, 7.9, 0.7), ("猪五花肉", 568, 7.7, 59.0, 2.4),
            ("牛腱子", 121, 20.2, 4.3, 0.9), ("牛腩", 332, 17.1, 29.3, 0.0),
            ("羊腿肉", 143, 20.5, 6.3, 0.2), ("猪肝", 129, 19.3, 3.5, 5.0),
            ("牛肉干", 550, 45.6, 40.0, 1.9),
        ],
        "水产": [
            ("三文鱼", 139, 17.2, 7.8, 0.0), ("巴沙鱼", 89, 15.0, 3.0, 0.0),
            ("带鱼", 127, 17.7, 4.9, 3.1), ("黄花鱼", 99, 17.9, 3.0, 0.1),
            ("虾仁", 93, 18.6, 1.1, 1.5), ("蟹肉", 103, 17.5, 2.6, 2.3),
            ("蛤蜊", 62, 10.1, 1.1, 2.8), ("海参", 78, 16.5, 0.2, 2.5),
            ("鱿鱼", 84, 17.0, 1.4, 0.0),
        ],
        "蛋奶": [
            ("鸡蛋", 144, 13.3, 8.8, 2.8), ("鸭蛋", 180, 12.6, 13.0, 3.1),
            ("全脂牛奶", 65, 3.3, 3.6, 4.9), ("脱脂牛奶", 35, 3.4, 0.2, 5.0),
            ("酸奶", 72, 2.5, 2.7, 9.3), ("奶酪", 328, 25.7, 23.5, 3.5),
            ("希腊酸奶", 59, 10.3, 0.4, 3.6),
        ],
        "豆类": [
            ("北豆腐", 116, 12.2, 4.8, 4.2), ("南豆腐", 57, 6.2, 2.5, 2.6),
            ("豆浆", 31, 3.0, 1.0, 1.2), ("黄豆", 390, 35.0, 16.0, 34.2),
            ("黑豆", 401, 36.0, 15.9, 33.6), ("腐竹", 459, 44.6, 21.7, 22.3),
            ("豆干", 197, 16.2, 3.6, 11.5),
        ],
        "蔬菜": [
            ("西兰花", 36, 4.1, 0.6, 4.3), ("菠菜", 28, 2.6, 0.3, 4.5),
            ("番茄", 20, 0.9, 0.2, 4.0), ("黄瓜", 16, 0.8, 0.2, 2.9),
            ("生菜", 16, 1.3, 0.3, 2.4), ("胡萝卜", 39, 1.0, 0.2, 8.8),
            ("香菇", 26, 2.2, 0.3, 5.2), ("娃娃菜", 13, 1.3, 0.2, 2.0),
            ("青椒", 22, 1.4, 0.2, 5.4), ("洋葱", 40, 1.1, 0.2, 9.0),
            ("茄子", 21, 1.1, 0.2, 4.9), ("白菜", 17, 1.5, 0.1, 3.2),
            ("韭菜", 26, 2.4, 0.4, 4.6), ("芹菜", 20, 1.2, 0.2, 4.5),
            ("冬瓜", 11, 0.4, 0.2, 2.6), ("南瓜", 22, 0.7, 0.1, 5.3),
            ("苦瓜", 19, 1.0, 0.1, 4.9), ("秋葵", 37, 2.0, 0.1, 7.5),
        ],
        "水果": [
            ("苹果", 53, 0.2, 0.2, 13.5), ("香蕉", 93, 1.4, 0.2, 22.0),
            ("蓝莓", 57, 0.7, 0.3, 14.5), ("橙子", 48, 0.8, 0.2, 11.1),
            ("西瓜", 31, 0.5, 0.1, 7.9), ("牛油果", 171, 2.0, 15.3, 7.4),
            ("草莓", 32, 1.0, 0.2, 7.1), ("葡萄", 45, 0.5, 0.3, 10.3),
            ("梨", 51, 0.3, 0.1, 13.1), ("猕猴桃", 61, 0.8, 0.6, 14.5),
            ("芒果", 60, 0.6, 0.2, 15.0), ("桃子", 48, 0.9, 0.1, 12.0),
        ],
        "坚果": [
            ("核桃仁", 646, 14.9, 58.8, 19.1), ("巴旦木", 579, 21.2, 51.0, 21.7),
            ("花生", 563, 24.8, 44.3, 21.7), ("腰果", 552, 17.3, 36.7, 41.6),
            ("瓜子", 606, 19.1, 53.4, 16.7), ("芝麻", 517, 19.1, 46.1, 24.0),
        ],
        "油脂调味": [
            ("橄榄油", 899, 0.0, 99.9, 0.0), ("花生油", 899, 0.0, 99.9, 0.0),
            ("芝麻酱", 630, 19.2, 52.7, 22.7), ("精制盐", 0, 0.0, 0.0, 0.0),
            ("酱油", 63, 5.6, 0.1, 10.1), ("食醋", 31, 2.1, 0.3, 4.9),
            ("白砂糖", 400, 0.0, 0.0, 99.9), ("蜂蜜", 321, 0.4, 1.9, 75.6),
        ],
        "饮品": [
            ("拿铁", 47, 3.1, 2.4, 3.4), ("美式咖啡", 1, 0.1, 0.0, 0.0),
            ("可乐", 43, 0.0, 0.0, 10.8), ("珍珠奶茶", 70, 0.5, 2.1, 12.0),
            ("绿茶", 1, 0.1, 0.0, 0.0), ("橙汁", 45, 0.7, 0.2, 10.4),
        ],
    }

    rows: list[dict[str, object]] = []
    index = 0

    for category, items in categories.items():
        for name, kcal, protein, fat, carb in items:
            index += 1
            rows.append(
                _make_row(
                    index=index,
                    rnd=rnd,
                    name=name,
                    category=category,
                    kcal=Decimal(str(kcal)),
                    protein=Decimal(str(protein)),
                    fat=Decimal(str(fat)),
                    carb=Decimal(str(carb)),
                )
            )

    # 留 3 个名额给末尾的边界用例（重复项 / 无能量 / 无名称）
    return rows[:97]


def _make_row(
    *,
    index: int,
    rnd: random.Random,
    name: str,
    category: str,
    kcal: Decimal,
    protein: Decimal,
    fat: Decimal,
    carb: Decimal,
) -> dict[str, object]:
    """按序号注入不同的脏数据形态，保证每次生成都能覆盖全部边界情况。"""

    # 61~65 号：能量改用 kJ 字段，验证单位换算
    if 61 <= index <= 65:
        energy_field = "energy_kj"
        energy_value = (kcal * Decimal("4.184")).quantize(Decimal("0.1"))
    elif index % 7 == 0:
        energy_field = "energy"          # 无单位后缀的字段名
        energy_value = kcal
    elif index % 5 == 0:
        energy_field = "能量(kcal)"       # 中文带括号单位
        energy_value = kcal
    else:
        energy_field = "energy_kcal"
        energy_value = kcal

    row: dict[str, object] = {
        "food_name": name,
        "category": category,
        energy_field: _maybe_string(index, energy_value, rnd),
    }

    # 纤维：约 1/5 缺失
    if index % 5 == 0:
        row["fiber_g"] = rnd.choice(["—", "-", "未检出", None])
    else:
        row["fiber_g"] = _maybe_string(index, _fiber_of(category, carb), rnd)

    # 蛋白质：约 1/9 缺失（验证宏量可空）
    if index % 9 == 0:
        row["protein_g"] = rnd.choice(["Tr", None])
    else:
        row["protein_g"] = _maybe_string(index, protein, rnd)

    row["fat_g"] = _maybe_string(index, fat, rnd)
    row["carb_g"] = _maybe_string(index, carb, rnd)

    # 钠：约 1/6 缺失或用检测限写法
    if index % 6 == 0:
        row["sodium_mg"] = rnd.choice([None, "<0.1"])
    else:
        row["sodium_mg"] = _maybe_string(index, _sodium_of(category, rnd), rnd)

    # 部分条目带别名，验证别名解析
    if index % 4 == 0:
        row["aliases"] = [name, name + "（" + category + "）"]

    return row


def _maybe_string(index: int, value: Decimal, rnd: random.Random) -> object:
    """约 1/3 的条目把数值写成字符串，模拟真实文件里的类型混乱。"""
    if index % 3 == 0:
        return str(value)
    return float(value)


def _fiber_of(category: str, carb: Decimal) -> Decimal:
    if category in ("蔬菜", "豆类", "坚果", "谷物"):
        return (carb * Decimal("0.15")).quantize(Decimal("0.1"))
    return Decimal("0.0")


def _sodium_of(category: str, rnd: random.Random) -> Decimal:
    base = {
        "油脂调味": Decimal("4000"),
        "水产": Decimal("150"),
        "畜肉": Decimal("60"),
        "禽肉": Decimal("60"),
        "蔬菜": Decimal("30"),
        "水果": Decimal("2"),
        "谷物": Decimal("5"),
        "饮品": Decimal("15"),
    }.get(category, Decimal("20"))
    jitter = Decimal(str(rnd.randint(0, 30)))
    return (base + jitter).quantize(Decimal("0.1"))


def _duplicates_and_edge_cases(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """在末尾追加重复项与极端项，验证去重与关键字段跳过。"""
    # 重复：与第 1 条同名
    rows.append(
        {
            "food_name": rows[0]["food_name"],
            "energy_kcal": 999,
            "protein_g": 1.0,
            "fat_g": 1.0,
            "carb_g": 1.0,
            "fiber_g": 0,
            "sodium_mg": 1,
        }
    )
    # 无能量：应被判为关键字段缺失而跳过
    rows.append(
        {
            "food_name": "未知能量测试品",
            "energy_kcal": "Tr",
            "protein_g": 1.0,
            "fat_g": 1.0,
            "carb_g": 1.0,
            "fiber_g": "—",
            "sodium_mg": 1,
        }
    )
    # 缺少名称：应被跳过
    rows.append({"energy_kcal": 100, "protein_g": 1.0})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="生成模拟的中国食物成分表数据")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("app/db/seeds/cn_foods_mock_100.json"),
    )
    args = parser.parse_args()

    rows = _build_rows()
    rows = _duplicates_and_edge_cases(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("已生成 " + str(len(rows)) + " 条 -> " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
