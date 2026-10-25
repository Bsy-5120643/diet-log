"""菜品与菜品食材明细。

设计要点（依据 SPEC-ai-food-recognition.md §3）：

1. **菜品表本身不存任何营养数据**，只存「由哪些食材、各多少克组成」。
   营养值永远从 `foods` 表读。这样食物成分表修正后，所有菜品的热量自动跟着更新，
   不存在两份数据打架。

2. `normalized_name` 是「同名直接复用」的匹配键。
   「宫保鸡丁盖饭」「自制宫保鸡丁」归一化后都指向「宫保鸡丁」，
   唯一索引建在这个字段上（而非原始名），否则复用逻辑失效。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class Recipe(TimestampMixin, Base):
    """菜品。MVP 阶段全部归用户私有。"""

    __tablename__ = "recipes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 展示用菜品名，用户可在确认页改名
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: 归一化名，用于去重匹配。生成规则见 SPEC §3.2
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: 冗余总热量 = Σ(食材每100g热量 × 克数 / 100)。可被重算覆盖。
    total_energy_kcal: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ai'")
    )
    #: AI 生成的临时菜品；用户保存后置 false
    is_temporary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    #: user = 用户私有；public = 公共库（本期不启用，为后续预留）
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'user'")
    )

    user: Mapped["User"] = relationship(back_populates="recipes")  # noqa: F821
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        back_populates="recipe",
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.display_order",
    )

    __table_args__ = (
        # 「同名直接复用」的实现基础：同一用户对同一道菜只有一条
        Index("uq_recipes_user_normalized_name", "user_id", "normalized_name", unique=True),
        # 后续公共菜品检索用
        Index("ix_recipes_normalized_name", "normalized_name"),
        CheckConstraint(
            "source IN ('ai', 'manual', 'seed')", name="recipe_source_valid"
        ),
        CheckConstraint(
            "origin IN ('user', 'public')", name="recipe_origin_valid"
        ),
    )

    def __repr__(self) -> str:
        return f"<Recipe {self.name}>"


class RecipeIngredient(TimestampMixin, Base):
    """菜品包含哪些食材、各多少克。"""

    __tablename__ = "recipe_ingredients"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: 指向现有食材库，营养值永远从 foods 读
    food_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("foods.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_g: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    food: Mapped["Food"] = relationship()  # noqa: F821

    __table_args__ = (
        # 按菜品查明细的主路径
        Index("ix_recipe_ingredients_recipe", "recipe_id"),
        CheckConstraint("quantity_g > 0", name="recipe_ingredient_quantity_positive"),
    )

    def __repr__(self) -> str:
        return f"<RecipeIngredient {self.recipe_id} {self.quantity_g}g>"
