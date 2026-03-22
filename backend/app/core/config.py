from functools import lru_cache
from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "Rental Document Analyzer"
    app_env: str = "development"
    debug: bool = False
    secret_key: str
    allowed_origins: str = "http://localhost:5173"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str

    # ── Redis / Celery ────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # ── JWT ──────────────────────────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ── AWS S3 ───────────────────────────────────────────────────────────────
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str = "eu-central-1"
    s3_bucket_name: str
    s3_presigned_url_expiry: int = 3600

    # ── OpenAI ───────────────────────────────────────────────────────────────
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.2

    # ── Stripe ───────────────────────────────────────────────────────────────
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # ── File Upload ───────────────────────────────────────────────────────────
    max_upload_size_mb: int = 20
    allowed_extensions: str = "pdf,docx"

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    # ── Resend (email) ────────────────────────────────────────────────────────
    resend_api_key: str = ""
    email_from: str = "noreply@yourdomain.com"
    frontend_url: str = "http://localhost:5173"    # used to build verification links

    # ── Email verification ────────────────────────────────────────────────────
    verification_token_expire_hours: int = 24

    # ── Disposable email blocking ─────────────────────────────────────────────
    block_disposable_emails: bool = True

    # ── GDPR ─────────────────────────────────────────────────────────────────
    delete_files_after_processing: bool = False

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return upper


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()