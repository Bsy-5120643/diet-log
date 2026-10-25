from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.models.enums import FOOD_SOURCES

# 统一注释，避免后来者把 foods 的值当成绝对值用
PER_100G = "每 100g 可食部"


def build_search_text(name: str, aliases: list[str]) -> str:
    """生成用于模糊检索的文本：名称 + 所有别名，统一小写。

    为什么需要这一列：aliases 存的是 JSON，而
    ① SQLAlchemy 默认 json.dumps 会把中文转成 \\uXXXX 转义，
       导致 aliases::text 的 LIKE 匹配不到字面中文；
    ② 即使关掉转义，PostgreSQL（jsonb）与 SQLite（text）的文本输出也未必一致。
    维护一个独立的纯文本列，两个方言行为完全一致，且能直接建 trgm 索引。
    """
    parts = [name, *aliases]
    return " ".join(part.strip() for part in parts if part and part.strip()).lower()


class Food(TimestampMixin, Base):
    """食物库，公共字典表。

    这里只有食物「本身是什么」，没有「谁吃了多少」。
    份量一律放在 food_entries —— 同一个食物，A 用碗记、B 用克记，
    是录入习惯的差异，不该污染公共数据。
    """

    __tablename__ = "foods"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 口语名 / 同义词，例如 番茄 ← 西红柿 / 圣女果 / tomato
    aliases: Mapped[list[str]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        server_default=text("'[]'"),
    )

    # 检索用的去规范化文本 = lower(name + 所有 aliases)。
    # 由 scripts/import_foods.py 维护，业务代码不要直接改它。
    search_text: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )

    energy_kcal: Mapped[Decimal] = mapped_column(
        Numeric(7, 2), nullable=False, comment=PER_100G
    )
    # 三大宏量允许为 NULL：《中国食物成分表》里确有未检测的条目，
    # 此时必须存 NULL 而不是填 0 —— 0 是真实测量值，语义完全不同。
    # 代价：这类食物无法用于计算摄入（food_entries 的快照字段是 NOT NULL），
    # 导入时会在统计里单独列出，供人工补录。
    protein_g: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment=PER_100G
    )
    fat_g: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment=PER_100G
    )
    carb_g: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment=PER_100G
    )
    fiber_g: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment=PER_100G
    )
    sodium_mg: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment=PER_100G
    )

    source: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'seed'")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )

    entries: Mapped[list["FoodEntry"]] = relationship(  # noqa: F821
        back_populates="food", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "energy_kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carb_g >= 0",
            name="values_non_negative",
        ),
        CheckConstraint(
            f"source IN ({', '.join(repr(s) for s in FOOD_SOURCES)})",
            name="source_valid",
        ),
        # 用户自建食物必须记录归属人，公共数据则不应有归属人
        CheckConstraint(
            "(source = 'user' AND created_by IS NOT NULL) OR (source <> 'user')",
            name="user_owned",
        ),
        # B-tree 对 LIKE '%番茄%' 无效（前置通配符），必须用三元组 GIN 索引
        Index(
            "ix_foods_search_text_trgm",
            "search_text",
            postgresql_using="gin",
            postgresql_ops={"search_text": "gin_trgm_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<Food {self.name}>"
