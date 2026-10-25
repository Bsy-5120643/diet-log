from __future__ import annotations

import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """创建/更新时间。

    注意 updated_at 的 onupdate 是 SQLAlchemy 在 Python 侧触发的，
    绕过 ORM 的批量 UPDATE 不会刷新它。若需要强一致，改用数据库触发器。
    """

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
