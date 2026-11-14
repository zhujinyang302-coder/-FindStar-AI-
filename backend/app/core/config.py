"""统一配置管理（Pydantic Settings）。

所有密钥/凭据只从环境变量或 .env 读取，禁止硬编码。
生产环境启动时会校验必需配置，缺失则直接失败（fail-fast）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_INSECURE_SECRETS = {
    "dev-insecure-secret-change-me",
    "dev-insecure-secret-change-me-min-32-bytes",
    "please-generate-a-random-secret",
    "please-generate-a-random-secret-at-least-32-bytes",
    "",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_env: Literal["development", "staging", "production"] = "development"
    app_name: str = "寻物星图 FindStar"
    app_version: str = "1.0.0"
    app_secret_key: str = "dev-insecure-secret-change-me-min-32-bytes"
    api_prefix: str = "/api/v1"
    access_token_expire_minutes: int = 720
    log_level: str = "INFO"

    # ---- 数据库 ----
    database_url: str = "sqlite:///./findstar.db"
    db_echo: bool = False

    # ---- 缓存 ----
    redis_url: str | None = None
    cache_enabled: bool = True
    cache_latest_ttl: int = 60
    cache_match_ttl: int = 600

    # ---- CORS ----
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ---- AI（OpenAI 兼容协议）----
    ai_provider: Literal["openai_compatible", "mock"] = "openai_compatible"
    ai_api_base: str | None = None
    ai_api_key: str | None = None
    ai_model_name: str | None = None
    ai_embedding_model: str | None = None
    ai_timeout_seconds: float = 20.0

    # ---- 发布模式、风控与抽检 ----
    auto_approve_listing: bool = True
    auto_match_on_approve: bool = True
    listing_risk_check_enabled: bool = True
    listing_risk_denylist: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    listing_risk_soft_keywords: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    item_create_daily_limit: int = 20
    listing_sample_rate: float = 0.10
    auto_approve_legacy_pending: bool = False

    # ---- 先匹配后发布 ----
    match_first_publish_enabled: bool = True
    draft_ttl_days: int = 7
    draft_retention_days: int = 30
    admin_direct_delist_enabled: bool = True

    # ---- 图片上传 ----
    upload_dir: str = "./uploads"
    max_image_size_bytes: int = 5 * 1024 * 1024
    max_images_per_item: int = 5
    allowed_image_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )
    allowed_image_extensions: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp"]
    )

    # ---- 匹配算法 ----
    match_algorithm_version: str = "v3.0.0"
    match_config_version: str = "v3.0.0"
    match_max_candidates: int = 3
    match_candidate_quota: int = 3
    match_score_threshold: float = 65.0
    match_preview_threshold: float = 50.0
    match_time_window_days: int = 30
    match_recall_top_k: int = 50
    match_candidate_pool_max: int = 2000
    match_total_budget_seconds: float = 8.0
    match_degraded_budget_seconds: float = 5.0
    match_explain_timeout_seconds: float = 4.0
    match_result_ttl_days: int = 7
    match_batch_retention_days: int = 90
    match_job_scan_seconds: int = 2

    # ---- 频控与反滥用 ----
    match_user_daily_limit: int = 20
    match_item_daily_limit: int = 5
    view_user_daily_limit: int = 100
    view_batch_daily_limit: int = 20
    view_candidate_total_limit: int = 20
    contact_daily_limit: int = 10
    contact_fail_threshold: int = 3
    contact_cooldown_hours: int = 24
    security_view_burst: int = 30

    # ---- 预匹配与图片 ----
    prematch_enabled: bool = False
    thumbnail_max_edge: int = 480
    watermark_text: str = "FindStar"
    background_jobs_enabled: bool = True

    # ---- 限流 ----
    ai_rate_limit_per_minute: int = 20
    redis_rate_ttl_seconds: int = 60

    # ---- 演示账号（仅部署环境配置）----
    demo_admin_email: str | None = None
    demo_admin_password: str | None = None

    # ---------- 校验 ----------
    @field_validator(
        "cors_origins",
        "allowed_image_types",
        "allowed_image_extensions",
        "listing_risk_denylist",
        "listing_risk_soft_keywords",
        mode="before",
    )
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """支持 "a,b,c" 与 JSON 数组两种环境变量写法。"""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return json.loads(stripped)
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def _validate_match_settings(self) -> "Settings":
        if not 0.0 <= self.match_score_threshold <= 100.0:
            raise ValueError("MATCH_SCORE_THRESHOLD 必须位于 [0, 100]")
        if not 1 <= self.match_candidate_quota <= 5:
            raise ValueError("MATCH_CANDIDATE_QUOTA 必须位于 [1, 5]")
        if self.match_recall_top_k < 1 or self.match_candidate_pool_max < 1:
            raise ValueError("召回数与候选池上界必须为正整数")
        if self.match_total_budget_seconds <= 0 or self.match_degraded_budget_seconds <= 0:
            raise ValueError("匹配预算必须为正数")
        if self.match_degraded_budget_seconds > self.match_total_budget_seconds:
            raise ValueError("降级预算不得大于总预算")
        if self.match_explain_timeout_seconds > self.match_total_budget_seconds:
            raise ValueError("解释预算不得大于总预算")
        for name in (
            "match_user_daily_limit",
            "match_item_daily_limit",
            "view_user_daily_limit",
            "view_batch_daily_limit",
            "view_candidate_total_limit",
            "contact_daily_limit",
            "security_view_burst",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} 必须为正整数")
        if self.contact_fail_threshold < 1 or self.contact_cooldown_hours < 1:
            raise ValueError("申请失败阈值与冷却时长必须为正数")
        if self.thumbnail_max_edge < 64:
            raise ValueError("缩略图最长边不得小于 64")
        return self

    @model_validator(mode="after")
    def _validate_listing_settings(self) -> "Settings":
        if not 0.0 <= self.listing_sample_rate <= 1.0:
            raise ValueError("LISTING_SAMPLE_RATE 必须位于 [0, 1]")
        if self.item_create_daily_limit < 1:
            raise ValueError("ITEM_CREATE_DAILY_LIMIT 必须为正整数")
        if (
            self.app_env == "production"
            and self.listing_risk_check_enabled
            and not self.listing_risk_denylist
        ):
            raise ValueError(
                "生产环境启用 LISTING_RISK_CHECK_ENABLED 时 "
                "LISTING_RISK_DENYLIST 不得为空"
            )
        return self

    @model_validator(mode="after")
    def _validate_match_first_settings(self) -> "Settings":
        if not 40.0 <= self.match_preview_threshold <= 100.0:
            raise ValueError("MATCH_PREVIEW_THRESHOLD 必须位于 [40, 100]")
        if not 1 <= self.draft_ttl_days <= 30:
            raise ValueError("DRAFT_TTL_DAYS 必须位于 [1, 30]")
        if self.draft_retention_days < self.draft_ttl_days:
            raise ValueError("DRAFT_RETENTION_DAYS 不得小于 DRAFT_TTL_DAYS")
        return self

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        if self.app_env == "production":
            if self.app_secret_key in _INSECURE_SECRETS:
                raise ValueError(
                    "APP_SECRET_KEY 在生产环境必须设置为随机值（当前为示例值）"
                )
            if self.ai_provider == "openai_compatible" and not self.ai_api_key:
                # 生产环境允许显式降级，但必须由 AI_PROVIDER=mock 声明
                raise ValueError(
                    "生产环境使用 openai_compatible 时必须配置 AI_API_KEY，"
                    "或显式设置 AI_PROVIDER=mock 以声明降级状态"
                )
        return self

    # ---------- 派生属性 ----------
    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def resolved_database_url(self) -> str:
        """把 SQLite 相对路径解析为基于 backend 目录的绝对路径，
        确保从任意工作目录执行脚本都使用同一个数据库文件。"""
        url = self.database_url
        prefix = "sqlite:///"
        if url.startswith(prefix):
            raw = url[len(prefix):]
            if raw and not Path(raw).is_absolute():
                backend_dir = Path(__file__).resolve().parents[2]
                return f"{prefix}{(backend_dir / raw).resolve().as_posix()}"
        return url

    @property
    def ai_is_live(self) -> bool:
        """是否具备真实 AI 调用能力（否则为降级状态，需如实标注）。"""
        return (
            self.ai_provider == "openai_compatible"
            and bool(self.ai_api_base)
            and bool(self.ai_api_key)
            and bool(self.ai_model_name)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()