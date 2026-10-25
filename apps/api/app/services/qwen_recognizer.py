"""阿里云通义千问 VL 适配器。

几个刻意的选择：

1. **走 OpenAI 兼容模式 HTTP 接口**，而不是 dashscope SDK。
   理由：少一个重依赖；且超时、重试、错误处理完全可控。
   端点：https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions

2. **图片走 base64 Data URL**，不落盘、不传公网 URL。
   SPEC 约定照片用完即弃，所以我们没有任何可访问的 URL 能提供。

3. **超时严格按配置（默认 15s）**。模型卡住时若不超时，
   请求会一直占着连接，免费层实例很容易被打满。

4. **API Key 只从 settings 读**，代码里不存在任何字面量密钥。
"""

from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.ai_recognizer import (
    AIConfigurationError,
    AIServiceUnavailableError,
    RawRecognition,
    UnsupportedImageError,
    extract_json_object,
    parse_recognition_payload,
    to_data_url,
)

#: 通义千问 OpenAI 兼容模式端点
QWEN_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

SYSTEM_PROMPT = (
    "你是专业的中式菜品营养分析师。用户会给你一张食物照片，"
    "你需要识别出菜品名称，并把它拆解成常见食材及各自的估算重量。"
)

USER_PROMPT = """请分析这张图片中的食物，严格按以下 JSON 格式输出，不要输出任何其它内容：

{
  "dish_name": "菜品名称，如：宫保鸡丁盖饭",
  "confidence": 0.0到1.0之间的数字，表示你对菜品判断的把握程度,
  "ingredients": [
    {"name": "食材名称", "quantity_g": 估算克数, "confidence": 0.0到1.0}
  ]
}

要求：
1. 只输出 JSON，不要 markdown 代码块，不要解释。
2. 食材名用**通用的中文食材名**（如「鸡胸肉」「花生米」「米饭」「食用油」），
   不要用品牌名、不要用「适量」「少许」这类词。
3. 克数按图片里的实际份量估算，是整数或一位小数。
4. 拆解要覆盖主要食材，包括烹饪用的油和明显的调料，但不要列得太碎。
5. 如果图片里没有食物，返回 {"dish_name": "", "confidence": 0, "ingredients": []}。
"""


class QwenVLRecognizer:
    """通义千问 VL 识别器。"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        endpoint: str = QWEN_ENDPOINT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.dashscope_api_key
        self._model = model or settings.ai_vision_model
        self._timeout = timeout_seconds or settings.ai_vision_timeout_seconds
        self._endpoint = endpoint
        self._client = client

    @property
    def provider_name(self) -> str:
        return "qwen-vl"

    async def recognize(self, image: bytes | str) -> RawRecognition:
        if not self._api_key:
            raise AIConfigurationError("未配置 DASHSCOPE_API_KEY，AI 识别功能不可用")

        data_url = to_data_url(image)

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "temperature": 0.2,
        }

        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }

        response_text = await self._post(payload, headers)
        parsed = extract_json_object(response_text)
        if parsed is None:
            # 模型输出无法解析 —— 按「完全没认出」处理，不抛异常
            return RawRecognition(
                dish_name="",
                confidence=0.0,
                ingredients=[],
                raw_response=response_text,
            )

        return parse_recognition_payload(parsed, raw_response=response_text)

    async def _post(self, payload: dict, headers: dict) -> str:
        """发起请求并取出模型文本。所有网络异常统一收敛成领域错误。"""
        timeout = httpx.Timeout(self._timeout, connect=10.0)

        try:
            if self._client is not None:
                response = await self._client.post(
                    self._endpoint, json=payload, headers=headers, timeout=timeout
                )
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        self._endpoint, json=payload, headers=headers
                    )
        except httpx.TimeoutException as exc:
            raise AIServiceUnavailableError("识别服务超时") from exc
        except httpx.HTTPError as exc:
            raise AIServiceUnavailableError("识别服务不可用") from exc

        if response.status_code == 400:
            raise UnsupportedImageError("模型拒绝了该图片，请换一张重试")
        if response.status_code in (401, 403):
            raise AIConfigurationError("DASHSCOPE_API_KEY 无效或没有该模型的权限")
        if response.status_code >= 500:
            raise AIServiceUnavailableError("识别服务暂时不可用")
        if response.status_code >= 400:
            raise AIServiceUnavailableError("识别请求被拒绝")

        try:
            body = response.json()
        except ValueError as exc:
            raise AIServiceUnavailableError("识别服务返回了无法解析的内容") from exc

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceUnavailableError("识别服务返回了异常结构") from exc
