"""AI 识别适配层测试。

用 FakeRecognizer 跑通全链路，不需要真实 API Key：
    图片 → 适配器 → 解析 → 归一化 → 匹配 foods → 营养计算
"""

from __future__ import annotations

import asyncio
import base64
import json
from decimal import Decimal

import pytest

from app.services.ai_recognizer import (
    AIConfigurationError,
    AIServiceUnavailableError,
    UnsupportedImageError,
    extract_json_object,
    image_bytes,
    parse_recognition_payload,
    sniff_mime,
    to_data_url,
)
from app.services.fake_recognizer import FakeRecognizer
from app.services.nutrition import scale, snapshot_of
from app.services.recipe_name import normalize_dish_name


# ---------------------------------------------------------------------------
# 图片编码
# ---------------------------------------------------------------------------

JPEG_MAGIC = b"\xff\xd8\xff\xe0"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_sniff_mime_jpeg():
    assert sniff_mime(JPEG_MAGIC + b"xxx") == "image/jpeg"


def test_sniff_mime_png():
    assert sniff_mime(PNG_MAGIC + b"xxx") == "image/png"


def test_sniff_mime_unknown_raises():
    with pytest.raises(UnsupportedImageError):
        sniff_mime(b"not an image")


def test_to_data_url_from_bytes():
    url = to_data_url(JPEG_MAGIC + b"payload")
    assert url.startswith("data:image/jpeg;base64,")


def test_to_data_url_passthrough_data_url():
    original = "data:image/png;base64,AAAA"
    assert to_data_url(original) == original


def test_to_data_url_from_bare_base64():
    assert to_data_url("AAAA") == "data:image/jpeg;base64,AAAA"


def test_to_data_url_empty_raises():
    with pytest.raises(UnsupportedImageError):
        to_data_url(b"")


def test_image_bytes_roundtrip():
    raw = JPEG_MAGIC + b"payload"
    encoded = base64.b64encode(raw).decode()
    assert image_bytes("data:image/jpeg;base64," + encoded) == raw
    assert image_bytes(encoded) == raw


# ---------------------------------------------------------------------------
# 模型输出解析
# ---------------------------------------------------------------------------


def test_extract_json_plain():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_in_markdown_fence():
    text = '好的：\n```json\n{"dish_name": "宫保鸡丁"}\n```\n希望有帮助'
    assert extract_json_object(text) == {"dish_name": "宫保鸡丁"}


def test_extract_json_with_surrounding_text():
    assert extract_json_object('这是结果 {"dish_name": "x"} 结束') == {"dish_name": "x"}


def test_extract_json_invalid_returns_none():
    assert extract_json_object("完全不是 JSON") is None
    assert extract_json_object("") is None


def test_parse_recognition_payload_full():
    payload = {
        "dish_name": "宫保鸡丁盖饭",
        "confidence": 0.85,
        "ingredients": [
            {"name": "鸡胸肉", "quantity_g": 120, "confidence": 0.9},
            {"name": "花生米", "quantity_g": 20, "confidence": 0.7},
        ],
    }
    result = parse_recognition_payload(payload)
    assert result.dish_name == "宫保鸡丁盖饭"
    assert result.confidence == 0.85
    assert len(result.ingredients) == 2
    assert result.ingredients[0].name == "鸡胸肉"
    assert result.ingredients[0].quantity_g == Decimal("120")
    assert not result.is_empty


def test_parse_recognition_payload_empty():
    result = parse_recognition_payload({"dish_name": "", "confidence": 0, "ingredients": []})
    assert result.is_empty


def test_parse_recognition_payload_skips_bad_items():
    """缺名字或克数非正的食材应被跳过，而不是让整条崩掉。"""
    payload = {
        "dish_name": "X",
        "confidence": 0.5,
        "ingredients": [
            {"name": "鸡胸肉", "quantity_g": 100},
            {"name": "", "quantity_g": 50},        # 没名字
            {"name": "花生", "quantity_g": 0},      # 克数为 0
            {"name": "米饭", "quantity_g": "abc"},  # 无法解析
        ],
    }
    result = parse_recognition_payload(payload)
    assert len(result.ingredients) == 1
    assert result.ingredients[0].name == "鸡胸肉"


def test_parse_recognition_payload_clamps_confidence():
    result = parse_recognition_payload({"dish_name": "X", "confidence": 5})
    assert result.confidence == 1.0
    result = parse_recognition_payload({"dish_name": "X", "confidence": -1})
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# FakeRecognizer 全链路
# ---------------------------------------------------------------------------


def test_fake_recognizer_returns_structured_result():
    recognizer = FakeRecognizer.with_gongbao()
    result = asyncio.run(recognizer.recognize(JPEG_MAGIC + b"img"))

    assert result.dish_name == "宫保鸡丁盖饭"
    assert len(result.ingredients) == 4
    assert normalize_dish_name(result.dish_name) == "宫保鸡丁"
    # 图片确实被传进来了
    assert recognizer.last_image is not None


def test_fake_recognizer_empty_is_treated_as_no_food():
    recognizer = FakeRecognizer.empty()
    result = asyncio.run(recognizer.recognize(b"x"))
    assert result.is_empty


def test_fake_recognizer_timeout_raises():
    recognizer = FakeRecognizer.timeout()
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(recognizer.recognize(b"x"))


def test_fake_recognizer_bad_image_raises():
    recognizer = FakeRecognizer.bad_image()
    with pytest.raises(UnsupportedImageError):
        asyncio.run(recognizer.recognize(b"x"))


def test_full_chain_normalize_then_compute(db_session):
    """全链路：识别 → 归一化 → 匹配 foods → 计算营养。"""
    from app.models.food import Food

    # 准备食物库
    foods = {
        "鸡胸肉": Decimal("133.00"),
        "花生米": Decimal("589.00"),
        "米饭": Decimal("116.00"),
        "食用油": Decimal("899.00"),
    }
    for name, kcal in foods.items():
        db_session.add(
            Food(
                name=name,
                energy_kcal=kcal,
                protein_g=Decimal("10.00"),
                fat_g=Decimal("5.00"),
                carb_g=Decimal("10.00"),
                fiber_g=Decimal("0.00"),
                sodium_mg=Decimal("10.00"),
                aliases=[],
                search_text=name.lower(),
                source="seed",
                is_public=True,
            )
        )
    db_session.commit()

    result = asyncio.run(FakeRecognizer.with_gongbao().recognize(b"img"))

    # 归一化
    normalized = normalize_dish_name(result.dish_name)
    assert normalized == "宫保鸡丁"

    # 匹配 + 计算
    total = Decimal("0")
    for ingredient in result.ingredients:
        food = db_session.scalar(
            __import__("sqlalchemy").select(Food).where(Food.name == ingredient.name)
        )
        assert food is not None, f"食材未匹配: {ingredient.name}"
        amounts = scale(snapshot_of(food), ingredient.quantity_g)
        total += amounts.energy_kcal

    # 鸡胸肉120g=159.6 + 花生米20g=117.8 + 米饭200g=232 + 食用油10g=89.9
    assert total == Decimal("599.30")


def test_unknown_ingredient_is_not_matched(db_session):
    """食物库里没有的食材应匹配失败，对应 SPEC 的「未匹配」分支。"""
    from sqlalchemy import select

    from app.models.food import Food

    db_session.add(
        Food(
            name="鸡胸肉",
            energy_kcal=Decimal("133.00"),
            protein_g=Decimal("19.40"),
            fat_g=Decimal("5.00"),
            carb_g=Decimal("2.50"),
            fiber_g=Decimal("0.00"),
            sodium_mg=Decimal("34.40"),
            aliases=[],
            search_text="鸡胸肉",
            source="seed",
            is_public=True,
        )
    )
    db_session.commit()

    result = asyncio.run(FakeRecognizer.with_unknown_ingredient().recognize(b"img"))

    matched = []
    unmatched = []
    for ingredient in result.ingredients:
        food = db_session.scalar(select(Food).where(Food.name == ingredient.name))
        (matched if food else unmatched).append(ingredient.name)

    assert matched == ["鸡胸肉"]
    assert unmatched == ["松茸"]
