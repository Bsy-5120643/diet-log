"""AI 识别抽象层：数据结构、错误类型、图片编码。

这一层**只负责把图片变成「识别出什么菜、由哪些食材组成」**，
不做以下事情（属于上层服务）：

- 菜品名归一化 —— 见 `recipe_name.py`
- 食材匹配到 foods 表 —— 上层做
- 营养计算 —— 上层用 `nutrition.scale()`
- 缓存 / 配额 —— 上层做

这样厂商差异被完全隔离在本层之下，换模型不用动业务代码。
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------


class AIRecognitionError(Exception):
    """识别相关错误的基类。"""


class UnsupportedImageError(AIRecognitionError):
    """图片格式不支持或内容损坏 —— 对应 400 invalid_image。"""


class AIServiceUnavailableError(AIRecognitionError):
    """模型服务不可用 / 超时 / 非 2xx —— 对应 502 / 504。"""


class AIConfigurationError(AIRecognitionError):
    """缺少 API Key 等配置问题 —— 对应 500，属于部署错误。"""


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawIngredient:
    """模型识别出的一个食材（尚未匹配到 foods 表）。"""

    #: 食材名，模型给的原始名称
    name: str
    #: 估算克数
    quantity_g: Decimal
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class RawRecognition:
    """一次识别的原始结果。

    `ingredients` 为空表示「完全没认出」，上层据此走空态引导。
    """

    dish_name: str
    confidence: float
    ingredients: list[RawIngredient] = field(default_factory=list)
    #: 模型原始输出，便于排障；不返回给前端
    raw_response: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.ingredients


class AIRecognizer(Protocol):
    """识别器协议。任何厂商的适配器只要实现这个方法即可替换。"""

    @property
    def provider_name(self) -> str: ...

    async def recognize(self, image: bytes | str) -> RawRecognition:
        """识别图片。

        :param image: 原始字节（jpg/png/...）或 base64 字符串 / data URL
        :raises UnsupportedImageError: 图片格式不支持
        :raises AIServiceUnavailableError: 服务不可用或超时
        """
        ...


# ---------------------------------------------------------------------------
# 图片编码
# ---------------------------------------------------------------------------

#: 支持的图片魔数
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_mime(data: bytes) -> str:
    """按魔数判断图片类型，不信任文件扩展名。"""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    # WEBP: RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise UnsupportedImageError("不支持的图片格式，请上传 jpg / png / gif / webp")


def to_data_url(image: bytes | str) -> str:
    """统一转成 Data URL（base64），供模型接口使用。

    因为 SPEC 约定**图片不落盘**，所以不能用「传公网 URL」的方式，
    只能走 base64。
    """
    if isinstance(image, str):
        stripped = image.strip()
        # 已经是 data URL
        if stripped.startswith("data:"):
            return stripped
        # 纯 base64
        return "data:image/jpeg;base64," + stripped

    if not image:
        raise UnsupportedImageError("图片内容为空")

    mime = sniff_mime(image)
    encoded = base64.b64encode(image).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def strip_prefix_for_base64(image: str) -> str:
    """去掉 `data:image/xxx;base64,` 前缀，只留 base64 本体。"""
    if "," in image and image.startswith("data:"):
        return image.split(",", 1)[1]
    return image


def image_bytes(image: bytes | str) -> bytes:
    """把各种输入统一还原成字节，用于体积校验等。"""
    if isinstance(image, bytes):
        return image
    return base64.b64decode(strip_prefix_for_base64(image), validate=False)


# ---------------------------------------------------------------------------
# 模型输出解析
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json_object(text: str) -> dict | None:
    """从模型输出里提取 JSON 对象。

    模型经常在 JSON 外面包一层 ```json 或加前后废话，这里做容错：
    1. 优先取代码块内容
    2. 否则取第一个 `{` 到最后一个 `}` 之间
    """
    if not text:
        return None

    candidates: list[str] = []
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1))
    candidates.append(text)

    for candidate in candidates:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end <= start:
            continue
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _to_decimal(value: object, default: Decimal) -> Decimal:
    try:
        if value is None:
            return default
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def parse_recognition_payload(payload: dict, raw_response: str | None = None) -> RawRecognition:
    """把模型返回的 JSON 解析成 `RawRecognition`。

    解析失败（字段缺失 / 类型不对）不抛异常，而是返回空结果，
    由上层按「完全没认出」处理 —— 符合 SPEC「不用 4xx 阻断」的原则。
    """
    dish_name = str(payload.get("dish_name") or payload.get("name") or "").strip()

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    ingredients: list[RawIngredient] = []
    raw_items = payload.get("ingredients")
    if isinstance(raw_items, list):
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            quantity_g = _to_decimal(item.get("quantity_g"), Decimal("0"))
            if quantity_g <= 0:
                continue

            item_confidence: float | None = None
            raw_conf = item.get("confidence")
            if raw_conf is not None:
                try:
                    item_confidence = max(0.0, min(1.0, float(raw_conf)))
                except (TypeError, ValueError):
                    item_confidence = None

            ingredients.append(
                RawIngredient(
                    name=name,
                    quantity_g=quantity_g,
                    confidence=item_confidence,
                )
            )

    return RawRecognition(
        dish_name=dish_name,
        confidence=confidence,
        ingredients=ingredients,
        raw_response=raw_response,
    )
