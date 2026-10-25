"""日期/时区工具。

这是本项目的头号坑，规则只有一条：
    **禁止用 now()/utcnow() 判定「用户的今天」**

Vercel / Render / Neon 默认都是 UTC，东八区用户在早上 8 点前记录，
用 UTC 判定会被算到前一天。所有「今天」必须按用户自己的时区算。
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "Asia/Shanghai"


def user_zone(timezone_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except Exception:
        # 时区名非法时退回默认，不能让一个脏字段搞挂整个请求
        return ZoneInfo(DEFAULT_TIMEZONE)


def current_local_date(timezone_name: str | None) -> datetime.date:
    """返回指定时区下的「今天」日期（不带时间）。"""
    return datetime.datetime.now(tz=user_zone(timezone_name)).date()


def parse_iso_date(value: str) -> datetime.date:
    """解析 YYYY-MM-DD，失败抛 ValueError。"""
    return datetime.date.fromisoformat(value)
