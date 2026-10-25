"""应用配置：全部从环境变量读取，密钥不进版本库。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "Diet Log API"
    app_env: str = "development"

    # Neon pooled 连接串，务必带 -pooler 主机名与 sslmode=require
    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # 前端域名白名单
    cors_origins: list[str] = ["http://localhost:3000"]

    # ---- AI 拍照识别 ----
    # 阿里云通义千问的 API Key。只从环境变量读取，绝不写进代码或版本库。
    # 为空时识别接口不可用（返回 500 配置错误），不影响其它功能。
    dashscope_api_key: str = ""
    #: 通义千问 VL 模型名
    ai_vision_model: str = "qwen-vl-max-latest"
    #: 调用模型的超时秒数。SPEC §10 定为 15s，防止模型卡死拖垮服务。
    ai_vision_timeout_seconds: float = 15.0
    #: 单次上传图片的体积上限（字节），超了直接 400，不送去模型
    ai_vision_max_image_bytes: int = 8 * 1024 * 1024

    # ---- 配额与限流（SPEC §5）----
    #: 非会员每天免费识别次数
    ai_free_daily_quota: int = 5
    #: 同一用户每分钟最多发起的识别次数（含失败）
    ai_rate_limit_per_minute: int = 2
    #: 同一 IP 每分钟最多发起次数（多账号兜底）
    ai_rate_limit_per_minute_per_ip: int = 10
    #: 连续「完全没认出」多少次后锁定
    ai_consecutive_failures_before_lock: int = 5
    #: 锁定时长（分钟）
    ai_lock_minutes: int = 60
    #: 临时菜品（未确认）保留时长，超时由清理任务删除
    ai_temp_recipe_ttl_hours: int = 24

    # ---- 健康指数与排行榜 ----
    #: 排行榜请求时最多为多少个用户补算缺失分数。
    #: 防止用户量上来后，单次请求要算几千个人的分数把服务拖垮。
    #: 超出的部分依赖定时任务（scripts/compute_daily_scores.py）预计算。
    leaderboard_max_compute_users: int = 200
    #: 进榜门槛：近 7 天至少有多少天记录
    leaderboard_min_logged_days: int = 3


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
