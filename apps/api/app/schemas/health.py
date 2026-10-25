"""健康指数与排行榜的出入参模型。

**脱敏是硬约束**：排行榜相关的模型里只允许出现
`rank` / `nickname` / `avatar_url` / `avg_score`，
绝不出现体重、热量、宏量等具体数值。
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthScoreOut(BaseModel):
    """某一天的健康指数。"""

    date: str
    score: int
    #: excellent / good / fair / poor，前端据此配色
    level: str
    #: 未设目标时热量与宏量记 0，前端应引导设置目标
    has_goal: bool
    #: {"heat": 40.0, "macro": 30.0, "habit": 22.0}
    breakdown: dict[str, float]
    #: 近 7 天平均分；没有任何已算分数时为 None
    week_avg: float | None = None
    #: 近 7 天里已有分数的天数
    scored_days: int = 0

    meals_logged: int
    streak_days: int


class LeaderboardEntryOut(BaseModel):
    """榜单单行。**只含脱敏后的展示字段**。"""

    rank: int
    nickname: str
    avatar_url: str | None = None
    avg_score: float


class LeaderboardMeOut(BaseModel):
    """当前用户自己的排名。

    `qualified=False` 表示近 7 天记录不足 3 天，未进榜 —— 前端应给出
    「再记录 N 天即可上榜」这类引导，而不是显示空白。
    """

    rank: int | None = None
    avg_score: float | None = None
    qualified: bool
    logged_days: int = 0


class LeaderboardOut(BaseModel):
    goal: str | None = None
    date_from: str
    date_to: str
    items: list[LeaderboardEntryOut]
    me: LeaderboardMeOut
