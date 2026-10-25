"""菜品名归一化测试。

重点在**反例**——防止以后有人往剥离表里加词时把菜名剥坏。
每组反例都对应一种真实的误伤场景。
"""

from __future__ import annotations

import pytest

from app.services.recipe_name import (
    PREFIX_STRIP,
    SUFFIX_STRIP,
    clean_dish_name,
    name_variants,
    normalize_dish_name,
    resolve_recipe_name,
)


# ---------------------------------------------------------------------------
# 基础清洗
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("宫保鸡丁", "宫保鸡丁"),
        ("宫保鸡丁（微辣）", "宫保鸡丁"),
        ("宫保鸡丁(小份)", "宫保鸡丁"),
        ("宫保鸡丁 【招牌】", "宫保鸡丁"),
        (" 宫保鸡丁 盖饭 ", "宫保鸡丁盖饭"),   # 空白被去掉
        ("宫保鸡丁,盖饭", "宫保鸡丁盖饭"),     # 标点被去掉
        ("Kung Pao Chicken", "KungPaoChicken"),
        ("", ""),
    ],
)
def test_clean_dish_name(raw, expected):
    assert clean_dish_name(raw) == expected


def test_clean_handles_none_like_empty():
    assert clean_dish_name("") == ""
    assert normalize_dish_name("") == ""


# ---------------------------------------------------------------------------
# 正例：修饰词应该被剥掉
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("宫保鸡丁盖饭", "宫保鸡丁"),
        ("宫保鸡丁盖浇饭", "宫保鸡丁"),
        ("宫保鸡丁盖码饭", "宫保鸡丁"),
        ("宫保鸡丁套餐", "宫保鸡丁"),
        ("宫保鸡丁外卖", "宫保鸡丁"),
        ("宫保鸡丁便当", "宫保鸡丁"),
        ("自制宫保鸡丁", "宫保鸡丁"),
        ("家常宫保鸡丁", "宫保鸡丁"),
        ("招牌宫保鸡丁", "宫保鸡丁"),
        ("四川宫保鸡丁", "宫保鸡丁"),
        ("自制宫保鸡丁盖饭", "宫保鸡丁"),   # 前后都剥
        ("台湾卤肉饭", "卤肉饭"),           # 只剥前缀，饭留住
        ("牛肉面大份", "牛肉面"),
        ("蛋炒饭一份", "蛋炒饭"),
    ],
)
def test_normalize_strips_modifiers(raw, expected):
    assert normalize_dish_name(raw) == expected


def test_gongbao_variants_all_converge():
    """同一个菜的多种叫法必须归一到同一个键，否则复用失效。"""
    names = [
        "宫保鸡丁",
        "宫保鸡丁盖饭",
        "宫保鸡丁盖浇饭",
        "自制宫保鸡丁",
        "家常宫保鸡丁盖饭",
        "四川宫保鸡丁（微辣）",
        "招牌宫保鸡丁套餐",
    ]
    results = {normalize_dish_name(n) for n in names}
    assert results == {"宫保鸡丁"}


# ---------------------------------------------------------------------------
# 反例：菜名本体绝不能被剥掉
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "蛋炒饭",       # 剥「炒饭」会得到「蛋」
        "扬州炒饭",     # 同上
        "葱油拌面",     # 剥「拌面」会得到「葱油」
        "卤肉饭",       # 剥「饭」会得到「卤肉」
        "兰州牛肉面",   # 剥「面」会得到「兰州牛肉」
        "酸辣粉",       # 剥「粉」会得到「酸辣」
        "西红柿鸡蛋汤", # 剥「汤」会得到「西红柿鸡蛋」
        "麻辣烫",
        "小笼包",
        "煎饼果子",
    ],
)
def test_normalize_keeps_dish_body(raw):
    """反例：这些名字必须原样保留，一个字都不许少。"""
    assert normalize_dish_name(raw) == raw


def test_suffix_table_has_no_single_char_food_words():
    """元测试：剥离表里绝不能出现「饭/面/粉/汤」这类单字。

    这是防止后人误加规则的护栏——如果哪天有人往 SUFFIX_STRIP 里加了「饭」，
    这条测试会立刻失败。
    """
    forbidden = {"饭", "面", "粉", "汤", "锅", "饼"}
    for word in SUFFIX_STRIP:
        assert word not in forbidden, f"剥离表不应包含单字本体词: {word}"


def test_suffix_table_are_all_multi_char():
    """剥离表必须全部是多字词。"""
    for word in SUFFIX_STRIP:
        assert len(word) >= 2, f"剥离词过短，容易误伤: {word}"
    for word in PREFIX_STRIP:
        assert len(word) >= 2, f"剥离词过短，容易误伤: {word}"


def test_strip_would_leave_nothing_is_avoided():
    """剥离后不能变成空字符串。"""
    assert normalize_dish_name("盖饭") == "盖饭"
    assert normalize_dish_name("套餐") == "套餐"
    assert normalize_dish_name("自制") == "自制"


# ---------------------------------------------------------------------------
# 候选名与匹配
# ---------------------------------------------------------------------------


def test_name_variants_orders_cleaned_first():
    variants = name_variants("宫保鸡丁盖饭")
    assert variants[0] == "宫保鸡丁盖饭"
    assert "宫保鸡丁" in variants


def test_name_variants_deduplicates():
    variants = name_variants("自制宫保鸡丁")
    assert len(variants) == len(set(variants))


def test_resolve_hits_existing_by_stripped_name():
    existing = ["宫保鸡丁", "蛋炒饭"]
    assert resolve_recipe_name("宫保鸡丁盖饭", existing) == "宫保鸡丁"
    assert resolve_recipe_name("自制宫保鸡丁", existing) == "宫保鸡丁"
    assert resolve_recipe_name("蛋炒饭一份", existing) == "蛋炒饭"


def test_resolve_returns_none_when_no_match():
    assert resolve_recipe_name("佛跳墙", ["宫保鸡丁", "蛋炒饭"]) is None


def test_resolve_prefers_exact_match():
    """完全匹配优先于剥离后匹配。"""
    existing = ["宫保鸡丁", "宫保鸡丁盖饭"]   # 两条同时存在时
    assert resolve_recipe_name("宫保鸡丁盖饭", existing) == "宫保鸡丁盖饭"


def test_resolve_empty_returns_none():
    assert resolve_recipe_name("宫保鸡丁", []) is None
    assert resolve_recipe_name("", ["宫保鸡丁"]) is None
