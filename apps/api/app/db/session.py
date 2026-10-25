from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

# Neon 免费层注意事项：
# - 连接数有上限，且计算实例空闲后会缩容到 0（冷启动约 1~3 秒）
# - pool_pre_ping：取连接前先探活，避免拿到被服务端关掉的死连接
# - pool_recycle：主动回收长时间空闲的连接
# - max_overflow=0：不允许突发扩容，防止打爆免费层连接上限
_pool_kwargs: dict[str, object] = (
    {}
    if _is_sqlite
    else {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_recycle": 300,
        "pool_timeout": 30,
    }
)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=not _is_sqlite,
    future=True,
    **_pool_kwargs,  # type: ignore[arg-type]
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：yield 一个会话，请求结束后关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
