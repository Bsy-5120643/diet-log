from __future__ import annotations

import datetime
import uuid
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin
from app.models.enums import MEAL_TYPES, MealType

_MEAL_TYPE_LIST = ", ".join(repr(m) for m in MEAL_TYPES)


class FoodEntry(TimestampMixin, Base):
    """一条饮食记录。

    本行同时承载三件事：
    1. 份量语义 —— quantity_g 是权威值，serving_* 仅用于还原用户当时的录入方式
    2. 营养快照 —— snapshot_* 固化记录当时食物的每 100g 营养值
    3. 计算结果 —— energy_kcal 等 = snapshot × quantity_g / 100，落库便于汇总与审计

    为什么必须存快照：食物库的营养值可能被修正（比如发现数据录错了），
    若记录实时 JOIN foods 计算，历史记录会跟着变，用户会看到昨天吃的东西
    热量莫名其妙变了。
    """

    __tablename__ = "food_entries"

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
    food_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("foods.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 日期与餐次
    entry_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, comment="用户本地日期，不做时区转换"
    )
    meal_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # 份量：quantity_g 为权威值
    quantity_g: Mapped[Decimal] = mapped_column(
        Numeric(8, 2), nullable=False
    )
    serving_unit: Mapped[str | None] = mapped_column(
        String(16), nullable=True, comment="录入单位：g / 个 / 碗 / 杯 / 份"
    )
    serving_count: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="几份，支持 1.5 碗"
    )
    serving_grams_per_unit: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment="该单位对应克数，冗余便于复现"
    )

    # 快照：记录当时的每 100g 营养值。
    # 三大宏量允许 NULL —— 食物库里存在未检测的条目（见 0006/0007 迁移），
    # 数据缺失不该阻止用户记录。热量列保持 NOT NULL：导入时已跳过无能量的食物，
    # 且总热量是核心指标，不允许算不出来。
    snapshot_energy_kcal: Mapped[Decimal] = mapped_column(Numeric(7, 2), nullable=False)
    snapshot_protein_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    snapshot_fat_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    snapshot_carb_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    snapshot_fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    snapshot_sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    # 计算结果：由 services/nutrition.py 统一写入。可空性与快照列保持一致。
    energy_kcal: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    carb_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    fiber_g: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    sodium_mg: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)

    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: 这条记录来自哪道菜（便于回溯与再次添加）。手动添加时为 NULL。
    recipe_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("recipes.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: 同一次 AI 确认产生的多条记录共用一个 group id，
    #: 用于 UI 分组展示与「整组删除」。
    entry_group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="entries")  # noqa: F821
    food: Mapped["Food"] = relationship(back_populates="entries")  # noqa: F821
    recipe: Mapped["Recipe"] = relationship()  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            f"meal_type IN ({_MEAL_TYPE_LIST})", name="meal_type_valid"
        ),
        CheckConstraint("quantity_g > 0", name="quantity_positive"),
        # 兜底：计算结果必须与「快照 × 克数 / 100」一致，防应用层漏算或算错。
        # ① 必须除以 100.0 而非 100：SQLite 的 NUMERIC 亲和性会把 150.0 存成
        #    整数 150，整数除法会得到 199 而不是 199.5。
        # ② 宏量列可为 NULL，但「快照 NULL ↔ 计算值 NULL」必须成对出现。
        #
        # 注意 SQL 的三值逻辑陷阱：不能写成
        #     (快照 IS NULL AND 值 IS NULL) OR 值 = round(快照 ...)
        # 因为「快照 NULL 但值是数字」时，第二个分支因 NULL 传播得到 NULL，
        # 而 CHECK 在结果为 NULL 时是**通过**的 —— 脏数据就漏过去了。
        # 必须两个分支都显式判断非空。
        CheckConstraint(
            "energy_kcal = round(quantity_g * snapshot_energy_kcal / 100.0, 2)"
            " AND ("
            "   (snapshot_protein_g IS NULL AND protein_g IS NULL)"
            "   OR (snapshot_protein_g IS NOT NULL AND protein_g IS NOT NULL"
            "       AND protein_g = round(quantity_g * snapshot_protein_g / 100.0, 2))"
            " )"
            " AND ("
            "   (snapshot_fat_g IS NULL AND fat_g IS NULL)"
            "   OR (snapshot_fat_g IS NOT NULL AND fat_g IS NOT NULL"
            "       AND fat_g = round(quantity_g * snapshot_fat_g / 100.0, 2))"
            " )"
            " AND ("
            "   (snapshot_carb_g IS NULL AND carb_g IS NULL)"
            "   OR (snapshot_carb_g IS NOT NULL AND carb_g IS NOT NULL"
            "       AND carb_g = round(quantity_g * snapshot_carb_g / 100.0, 2))"
            " )",
            name="computed_consistent",
        ),
        # 最高频查询：某用户某天的全部记录；也是当日汇总聚合的主路径
        Index("ix_food_entries_user_date", "user_id", "entry_date"),
        # 「我最近/最常吃的食物」
        Index("ix_food_entries_user_food", "user_id", "food_id"),
        # PostgreSQL 不会自动为外键建索引，缺了会导致删 foods 时全表扫描
        Index("ix_food_entries_food_id", "food_id"),
        # 外键索引：删菜品时避免全表扫描
        Index("ix_food_entries_recipe_id", "recipe_id"),
        # 按组删除 / 按组查询
        Index("ix_food_entries_group_id", "entry_group_id"),
    )

    @property
    def meal_type_enum(self) -> MealType:
        return MealType(self.meal_type)

    def __repr__(self) -> str:
        return f"<FoodEntry {self.entry_date} {self.meal_type} {self.quantity_g}g>"
