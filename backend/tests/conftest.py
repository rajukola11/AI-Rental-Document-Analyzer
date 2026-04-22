"""
tests/conftest.py

Patches app.core.config.settings before any app module is imported,
so the test suite never needs real environment variables / .env files.
"""
import sys
import types
import logging as _stdlib_logging
from pathlib import Path

BASE = str(Path(__file__).resolve().parents[1])


def _pkg(name: str, path: str) -> types.ModuleType:
    """Create a stub package module that Python treats as a real package."""
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    return m


sys.modules.setdefault("app",      _pkg("app",      f"{BASE}/app"))
sys.modules.setdefault("app.core", _pkg("app.core", f"{BASE}/app/core"))


class FakeSettings:
    app_name = "Rental Document Analyzer"
    app_env = "test"
    debug = False
    secret_key = "test-secret-key"
    allowed_origins = "http://localhost:5173"

    @property
    def cors_origins(self):
        return ["http://localhost:5173"]

    database_url = "sqlite:///:memory:"
    redis_url = "redis://localhost:6379/0"
    celery_broker_url = "redis://localhost:6379/0"
    celery_result_backend = "redis://localhost:6379/1"

    jwt_secret_key = "test-jwt-secret-key-for-testing-only"
    jwt_algorithm = "HS256"
    jwt_access_token_expire_minutes = 60
    jwt_refresh_token_expire_days = 7

    aws_access_key_id = "test-key-id"
    aws_secret_access_key = "test-secret"
    aws_region = "eu-central-1"
    s3_bucket_name = "test-bucket"
    s3_presigned_url_expiry = 3600

    openai_api_key = "sk-test-fake-key"
    openai_model = "gpt-4o-mini"
    openai_max_tokens = 4096
    openai_temperature = 0.2

    stripe_secret_key = "sk_test_fake"
    stripe_webhook_secret = "whsec_fake"
    stripe_publishable_key = "pk_test_fake"

    max_upload_size_mb = 20
    allowed_extensions = "pdf,docx"

    @property
    def allowed_extensions_list(self):
        return ["pdf", "docx"]

    @property
    def max_upload_size_bytes(self):
        return self.max_upload_size_mb * 1024 * 1024

    resend_api_key = "re_test_fake"
    email_from = "test@example.com"
    frontend_url = "http://localhost:5173"
    verification_token_expire_hours = 24
    block_disposable_emails = True
    delete_files_after_processing = False
    log_level = "DEBUG"


_fake_settings = FakeSettings()

_cfg = types.ModuleType("app.core.config")
_cfg.__package__ = "app.core"
_cfg.settings = _fake_settings
_cfg.get_settings = lambda: _fake_settings
sys.modules["app.core.config"] = _cfg

_log = types.ModuleType("app.core.logging")
_log.__package__ = "app.core"
_log.get_logger = lambda name: _stdlib_logging.getLogger(name)
sys.modules["app.core.logging"] = _log