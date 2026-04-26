"""
Patches app.core.config.settings and app.core.logging before any app module
is imported, so the test suite never needs real environment variables / .env files.

Also provides a shared SQLite engine used by all route test files to prevent
cross-file interference when pytest collects them in the same session.
"""
import sys
import types
import uuid as _uuid
import logging as _stdlib_logging

# ── Adjust BASE to match your machine ────────────────────────────────────────
BASE = "/home/raju/Downloads/AI-Rental-Document-Analyzer-master/backend"


def _pkg(name: str, path: str) -> types.ModuleType:
    """Create a stub package module that Python treats as a real package."""
    m = types.ModuleType(name)
    m.__path__ = [path]
    m.__package__ = name
    return m


# Register all app sub-packages so imports like `from app.db.base import Base`
# resolve through the filesystem instead of failing with ModuleNotFoundError.
for _name, _rel in [
    ("app",              "app"),
    ("app.core",         "app/core"),
    ("app.db",           "app/db"),
    ("app.models",       "app/models"),
    ("app.services",     "app/services"),
    ("app.api",          "app/api"),
    ("app.api.routes",   "app/api/routes"),
    ("app.schemas",      "app/schemas"),
    ("app.workers",      "app/workers"),
]:
    mod = _pkg(_name, f"{BASE}/{_rel}")
    sys.modules.setdefault(_name, mod)
    # Also wire as attribute of parent so monkeypatch.setattr traversal works
    # e.g. "app.workers.tasks" → app.workers must be attr of app module
    if "." in _name:
        parent_name, child_attr = _name.rsplit(".", 1)
        parent_mod = sys.modules.get(parent_name)
        if parent_mod is not None and not hasattr(parent_mod, child_attr):
            setattr(parent_mod, child_attr, sys.modules[_name])


# ── FakeSettings ─────────────────────────────────────────────────────────────

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

# ── Config stub ───────────────────────────────────────────────────────────────
_cfg = types.ModuleType("app.core.config")
_cfg.__package__ = "app.core"
_cfg.settings = _fake_settings
_cfg.get_settings = lambda: _fake_settings
sys.modules["app.core.config"] = _cfg

# ── Logging stub ──────────────────────────────────────────────────────────────
_log = types.ModuleType("app.core.logging")
_log.__package__ = "app.core"
_log.get_logger = lambda name: _stdlib_logging.getLogger(name)
_log.setup_logging = lambda: None          # required by app.main
sys.modules["app.core.logging"] = _log


# ── SQLite-compatible type overrides ──────────────────────────────────────────
# Must happen BEFORE any SQLAlchemy model is imported.

import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa_types


class _SqliteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return _uuid.UUID(value) if value else None


class _SqliteJSON(_sa_types.TypeDecorator):
    impl = _sa_types.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        import json
        return json.dumps(value) if value is not None else None

    def process_result_value(self, value, dialect):
        import json
        return json.loads(value) if value else None


_pg.UUID = _SqliteUUID
_pg.JSON = _SqliteJSON