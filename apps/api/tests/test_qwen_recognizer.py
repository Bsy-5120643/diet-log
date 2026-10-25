"""通义千问 VL 适配器测试。

用 httpx.MockTransport 拦截 HTTP，**不需要真实 API Key** 也能验证：
请求体构造、响应解析、各类 HTTP 错误的收敛。
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import httpx
import pytest

from app.services.ai_recognizer import (
    AIConfigurationError,
    AIServiceUnavailableError,
    UnsupportedImageError,
)
from app.services.qwen_recognizer import QwenVLRecognizer

JPEG = b"\xff\xd8\xff\xe0" + b"payload"

VALID_PAYLOAD = {
    "dish_name": "宫保鸡丁盖饭",
    "confidence": 0.85,
    "ingredients": [
        {"name": "鸡胸肉", "quantity_g": 120, "confidence": 0.9},
        {"name": "花生米", "quantity_g": 20, "confidence": 0.7},
    ],
}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok(content: str, capture: list[httpx.Request] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    return handler


# ---------------------------------------------------------------------------
# 配置与请求构造
# ---------------------------------------------------------------------------


def test_missing_api_key_raises_configuration_error():
    """没有 Key 时直接报配置错误，而不是去发一个注定失败的请求。"""
    recognizer = QwenVLRecognizer(api_key="", client=_client(_ok("{}")))
    with pytest.raises(AIConfigurationError):
        asyncio.run(recognizer.recognize(JPEG))


def test_request_carries_base64_image_and_auth_header():
    """图片必须以 base64 Data URL 形式发出（不落盘，所以没有 URL 可用）。"""
    captured: list[httpx.Request] = []
    recognizer = QwenVLRecognizer(
        api_key="test-key",
        model="qwen-vl-max-latest",
        client=_client(_ok(json.dumps(VALID_PAYLOAD, ensure_ascii=False), captured)),
    )
    asyncio.run(recognizer.recognize(JPEG))

    assert len(captured) == 1
    request = captured[0]
    assert request.headers["Authorization"] == "Bearer test-key"

    body = json.loads(request.content)
    assert body["model"] == "qwen-vl-max-latest"

    user_content = body["messages"][1]["content"]
    image_part = user_content[0]
    assert image_part["type"] == "image_url"
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


# ---------------------------------------------------------------------------
# 响应解析
# ---------------------------------------------------------------------------


def test_parses_valid_response():
    recognizer = QwenVLRecognizer(
        api_key="k", client=_client(_ok(json.dumps(VALID_PAYLOAD, ensure_ascii=False)))
    )
    result = asyncio.run(recognizer.recognize(JPEG))

    assert result.dish_name == "宫保鸡丁盖饭"
    assert result.confidence == 0.85
    assert len(result.ingredients) == 2
    assert result.ingredients[0].name == "鸡胸肉"
    assert result.ingredients[0].quantity_g == Decimal("120")


def test_parses_markdown_fenced_response():
    """模型经常包一层 ```json，必须能容错。"""
    content = "好的\n```json\n" + json.dumps(VALID_PAYLOAD, ensure_ascii=False) + "\n```"
    recognizer = QwenVLRecognizer(api_key="k", client=_client(_ok(content)))
    result = asyncio.run(recognizer.recognize(JPEG))
    assert result.dish_name == "宫保鸡丁盖饭"


def test_unparseable_response_becomes_empty_not_error():
    """输出无法解析 → 按「完全没认出」处理，不抛异常（符合 SPEC 不用 4xx 阻断）。"""
    recognizer = QwenVLRecognizer(api_key="k", client=_client(_ok("我不是 JSON")))
    result = asyncio.run(recognizer.recognize(JPEG))
    assert result.is_empty
    assert result.confidence == 0.0


def test_malformed_structure_raises_service_error():
    def handler(request):
        return httpx.Response(200, json={"unexpected": True})

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(recognizer.recognize(JPEG))


# ---------------------------------------------------------------------------
# HTTP 错误收敛
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_raises_configuration_error(status):
    def handler(request):
        return httpx.Response(status, json={"error": "no permission"})

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(AIConfigurationError):
        asyncio.run(recognizer.recognize(JPEG))


def test_400_raises_unsupported_image():
    def handler(request):
        return httpx.Response(400, json={"error": "bad image"})

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(UnsupportedImageError):
        asyncio.run(recognizer.recognize(JPEG))


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_error_raises_service_unavailable(status):
    def handler(request):
        return httpx.Response(status, json={"error": "boom"})

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(recognizer.recognize(JPEG))


def test_timeout_raises_service_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("timeout")

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(recognizer.recognize(JPEG))


def test_transport_error_raises_service_unavailable():
    def handler(request):
        raise httpx.ConnectError("conn refused")

    recognizer = QwenVLRecognizer(api_key="k", client=_client(handler))
    with pytest.raises(AIServiceUnavailableError):
        asyncio.run(recognizer.recognize(JPEG))


# ---------------------------------------------------------------------------
# 超时设置
# ---------------------------------------------------------------------------


def test_default_timeout_comes_from_settings():
    """默认必须走配置里的 15s，防止有人硬编码。"""
    from app.core.config import settings

    recognizer = QwenVLRecognizer(api_key="k", client=_client(_ok("{}")))
    assert recognizer._timeout == settings.ai_vision_timeout_seconds
    assert settings.ai_vision_timeout_seconds == 15.0


def test_timeout_is_overridable_for_tests():
    recognizer = QwenVLRecognizer(
        api_key="k", timeout_seconds=1.0, client=_client(_ok("{}"))
    )
    assert recognizer._timeout == 1.0
