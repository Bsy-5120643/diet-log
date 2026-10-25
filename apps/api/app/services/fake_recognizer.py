"""测试用的假识别器。

不需要真实 API Key 就能跑通全链路：
适配器 → 解析 → 归一化 → 匹配 foods → 计算营养。

除了正常返回，它还能模拟各类异常，用于验证错误处理分支。
"""

from __future__ import annotations

from decimal import Decimal

from app.services.ai_recognizer import (
    AIServiceUnavailableError,
    RawIngredient,
    RawRecognition,
    UnsupportedImageError,
)


class FakeRecognizer:
    """可控的假识别器。

    用法：
        recognizer = FakeRecognizer.with_gongbao()
        recognizer = FakeRecognizer.empty()          # 模拟完全没认出
        recognizer = FakeRecognizer.timeout()        # 模拟超时
    """

    def __init__(
        self,
        *,
        dish_name: str = "测试菜品",
        confidence: float = 0.9,
        ingredients: list[tuple[str, str]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self._dish_name = dish_name
        self._confidence = confidence
        self._ingredients = ingredients or []
        self._error = error
        #: 记录最后一次收到的图片，便于断言「确实传进来过」
        self.last_image: bytes | str | None = None

    @property
    def provider_name(self) -> str:
        return "fake"

    async def recognize(self, image: bytes | str) -> RawRecognition:
        self.last_image = image
        if self._error is not None:
            raise self._error

        return RawRecognition(
            dish_name=self._dish_name,
            confidence=self._confidence,
            ingredients=[
                RawIngredient(name=name, quantity_g=Decimal(grams), confidence=0.9)
                for name, grams in self._ingredients
            ],
            raw_response='{"dish_name": "' + self._dish_name + '"}',
        )

    # ---- 预设场景 ----

    @classmethod
    def with_gongbao(cls) -> "FakeRecognizer":
        """宫保鸡丁盖饭，四个食材。"""
        return cls(
            dish_name="宫保鸡丁盖饭",
            confidence=0.85,
            ingredients=[
                ("鸡胸肉", "120"),
                ("花生米", "20"),
                ("米饭", "200"),
                ("食用油", "10"),
            ],
        )

    @classmethod
    def with_unknown_ingredient(cls) -> "FakeRecognizer":
        """含一个食物库里不存在的食材，用于验证「未匹配」分支。"""
        return cls(
            dish_name="松茸炖鸡",
            confidence=0.7,
            ingredients=[
                ("鸡胸肉", "100"),
                ("松茸", "30"),
            ],
        )

    @classmethod
    def empty(cls) -> "FakeRecognizer":
        """完全没认出。"""
        return cls(dish_name="", confidence=0.0, ingredients=[])

    @classmethod
    def timeout(cls) -> "FakeRecognizer":
        return cls(error=AIServiceUnavailableError("识别服务超时"))

    @classmethod
    def bad_image(cls) -> "FakeRecognizer":
        return cls(error=UnsupportedImageError("不支持的图片格式"))
