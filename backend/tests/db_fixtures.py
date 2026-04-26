"""
Shared SQLite engine, session, and get_db override used by all route test files.
conftest.py runs first (pytest loads it automatically), so UUID/JSON types
are already patched when this module is imported by a test file.
"""
import sys
import os

# Ensure the tests/ directory is on sys.path so this file is importable
# regardless of how pytest sets up the path (importmode=importlib vs prepend).
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

# Also ensure the backend root is on sys.path
_backend_dir = os.path.dirname(_tests_dir)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import user, document, analysis, payment  # noqa: F401

SHARED_TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

Base.metadata.create_all(SHARED_TEST_ENGINE)

SHARED_TEST_SESSION = sessionmaker(
    bind=SHARED_TEST_ENGINE,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def shared_override_get_db():
    """FastAPI dependency override used by all route test files."""
    db = SHARED_TEST_SESSION()
    try:
        yield db
    finally:
        db.close()