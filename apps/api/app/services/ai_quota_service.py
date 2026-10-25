"""AI 识别的配额与限流。

职责分离（SPEC §5）：
- **配额管成本** —— 只统计成功调用；失败不扣
- **限流管滥用** —— 任何发起都计数，包括失败

时序（SPEC §5.4）：
    检查（锁定 → 限流 → 配额）**全部发生在调用模型之前**，
    因为只有这样才能真正挡住花钱。扣减则发生在拿到有效结果之后。
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import current_local_date
from app.models.ai_usage import AiRecognitionUsage
from app.models.user import User


class QuotaExceeded(Exception):
    """当日配额已用尽 —— 429 quota_exceeded。"""


class RateLimited(Exception):
    """分钟级限流 —— 429 rate_limited。"""


class TemporarilyLocked(Exception):
    """连续失败过多，功能被锁定 —— 429 temporarily_locked。"""

    def __init__(self, locked_until: datetime.datetime) -> None:
        super().__init__("识别功能暂时被锁定")
        self.locked_until = locked_until


def _get_or_create(db: Session, user: User, today: datetime.date) -> AiRecognitionUsage:
    usage = db.scalar(
        select(AiRecognitionUsage).where(
            AiRecognitionUsage.user_id == user.id,
            AiRecognitionUsage.usage_date == today,
        )
    )
    if usage is None:
        usage = AiRecognitionUsage(
            user_id=user.id,
            usage_date=today,
            quota_used=0,
            minute_count=0,
            consecutive_failures=0,
        )
        db.add(usage)
        db.flush()
    return usage


def _naive_utc(value: datetime.datetime) -> datetime.datetime:
    """统一成不带时区的 UTC。

    SQLite 读回 timestamptz 会丢掉 tzinfo（变成 naive），Postgres 则返回 aware。
    两边都归一化成 naive UTC，比较才不会永远不等。
    """
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc)
        return value.replace(tzinfo=None)
    return value


def _minute_bucket(now: datetime.datetime) -> datetime.datetime:
    return _naive_utc(now).replace(second=0, microsecond=0)


def ensure_allowed(db: Session, user: User) -> None:
    """调用模型**之前**检查是否放行。

    不放行就抛异常，调用方一个请求都别发。
    """
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    today = current_local_date(user.timezone)
    usage = _get_or_create(db, user, today)

    # 1. 锁定
    if usage.locked_until is not None:
        locked_until = _naive_utc(usage.locked_until)
        if locked_until > _naive_utc(now):
            raise TemporarilyLocked(usage.locked_until)

    # 2. 分钟级限流
    bucket = _minute_bucket(now)
    if usage.minute_bucket is not None and _naive_utc(usage.minute_bucket) == bucket:
        if usage.minute_count >= settings.ai_rate_limit_per_minute:
            raise RateLimited()
    else:
        usage.minute_bucket = bucket
        usage.minute_count = 0

    # 3. 配额
    if usage.quota_used >= settings.ai_free_daily_quota:
        raise QuotaExceeded()

    # 记录本次「发起」，无论后面成功与否都算一次
    usage.minute_count += 1
    db.commit()


def record_success(db: Session, user: User) -> None:
    """识别成功（含部分成功）→ 扣 1 次配额，连续失败清零。"""
    today = current_local_date(user.timezone)
    usage = _get_or_create(db, user, today)
    usage.quota_used += 1
    usage.consecutive_failures = 0
    db.commit()


def record_empty(db: Session, user: User) -> None:
    """完全没认出 → 不扣配额，但计入连续失败；达到阈值则锁定。"""
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    today = current_local_date(user.timezone)
    usage = _get_or_create(db, user, today)
    usage.consecutive_failures += 1
    if usage.consecutive_failures >= settings.ai_consecutive_failures_before_lock:
        usage.locked_until = now + datetime.timedelta(minutes=settings.ai_lock_minutes)
        usage.consecutive_failures = 0
    db.commit()


def get_quota(db: Session, user: User) -> dict[str, object]:
    """当前配额状态，供前端展示「剩余 N 次」。"""
    today = current_local_date(user.timezone)
    usage = _get_or_create(db, user, today)
    limit = settings.ai_free_daily_quota
    remaining = max(0, limit - usage.quota_used)

    locked_until = usage.locked_until
    if locked_until is not None:
        locked_until = _naive_utc(locked_until)
        now_naive = _naive_utc(datetime.datetime.now(tz=datetime.timezone.utc))
        if locked_until <= now_naive:
            locked_until = None   # 已过期，不展示给前端

    return {
        "used": usage.quota_used,
        "limit": limit,
        "remaining": remaining,
        "resets_at": _next_day_reset(user.timezone, today),
        "locked_until": locked_until.isoformat() if locked_until else None,
    }


def _next_day_reset(timezone_name: str, today: datetime.date) -> str:
    """自然日重置时刻：用户时区的次日 0 点。"""
    from zoneinfo import ZoneInfo

    tomorrow = today + datetime.timedelta(days=1)
    zone = ZoneInfo(timezone_name)
    reset = datetime.datetime(
        tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0, tzinfo=zone
    )
    return reset.isoformat()
