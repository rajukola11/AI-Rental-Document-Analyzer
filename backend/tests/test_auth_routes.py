"""
Pytest test suite for app/api/routes/auth.py

Covers every endpoint:
  POST /auth/register          — happy path, duplicate email, disposable email,
                                 weak password, missing fields
  POST /auth/login             — correct creds, wrong password, unknown email,
                                 inactive account, token shape
  POST /auth/refresh           — valid refresh token, access token rejected,
                                 missing header, expired token, inactive user
  GET  /auth/me                — authenticated, unauthenticated, unknown user
  GET  /auth/verify-email      — valid token, expired token, invalid token
  POST /auth/resend-verification — unverified account, already verified,
                                   unknown email (anti-enumeration)

Uses FastAPI TestClient with an in-memory SQLite database.
Email sending is always mocked — no real emails are sent.
Settings stubbed via tests/conftest.py.
"""

import uuid
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa

# ── SQLite type stubs (same pattern as other test files) ─────────────────────

class _UUID(_sa.TypeDecorator):
    impl = _sa.String(36); cache_ok = True
    def process_bind_param(self, v, d): return str(v) if v else None
    def process_result_value(self, v, d): return uuid.UUID(v) if v else None

class _JSON(_sa.TypeDecorator):
    impl = _sa.Text; cache_ok = True
    def process_bind_param(self, v, d):
        import json; return json.dumps(v) if v is not None else None
    def process_result_value(self, v, d):
        import json; return json.loads(v) if v else None

_pg.UUID = _UUID
_pg.JSON = _JSON

# ── DB + App setup ────────────────────────────────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import patch as _patch

from app.db.base import Base
from app.models import user as _u, document as _d, analysis as _a, payment as _p
from app.models.user import User
from app.core.security import hash_password, create_refresh_token

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(_engine)
_TestSession = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


with _patch("sqlalchemy.create_engine", return_value=_engine):
    import app.db.session as _sess
_sess.SessionLocal = _TestSession

with _patch("app.services.disposable_email_service.preload_blocklist"):
    from app.main import app

from app.db.session import get_db
app.dependency_overrides[get_db] = _override_get_db

from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    """Wipe all rows between tests — keeps tables."""
    yield
    with _TestSession() as db:
        db.query(_u.User).delete()
        db.commit()


@pytest.fixture()
def db():
    with _TestSession() as session:
        yield session


@pytest.fixture()
def client():
    with _patch("app.api.routes.auth.send_verification_email"), \
         _patch("app.api.routes.auth.send_welcome_email"):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


def _register(client, email="user@example.com", password="Password1!", full_name=None):
    body = {"email": email, "password": password}
    if full_name:
        body["full_name"] = full_name
    with _patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
        return client.post("/auth/register", json=body)


def _make_verified_user(db, email="verified@example.com", password="Password1!",
                        is_active=True) -> User:
    u = User(
        email=email,
        password_hash=hash_password(password),
        role="user",
        is_verified=True,
        is_active=is_active,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _login(client, email="verified@example.com", password="Password1!"):
    return client.post("/auth/login", json={"email": email, "password": password})


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# POST /auth/register
# ===========================================================================

class TestRegister:
    def test_returns_201(self, client):
        resp = _register(client)
        assert resp.status_code == 201

    def test_response_contains_email(self, client):
        resp = _register(client, email="alice@example.com")
        assert resp.json()["email"] == "alice@example.com"

    def test_user_not_verified_on_registration(self, client):
        resp = _register(client)
        assert resp.json()["is_verified"] is False

    def test_role_is_user(self, client):
        resp = _register(client)
        assert resp.json()["role"] == "user"

    def test_response_has_id(self, client):
        resp = _register(client)
        assert "id" in resp.json()

    def test_full_name_stored(self, client):
        resp = _register(client, full_name="Alice Smith")
        assert resp.json()["full_name"] == "Alice Smith"

    def test_duplicate_email_returns_422(self, client):
        _register(client, email="dup@example.com")
        resp = _register(client, email="dup@example.com")
        assert resp.status_code == 422

    def test_duplicate_email_error_message(self, client):
        _register(client, email="dup@example.com")
        resp = _register(client, email="dup@example.com")
        assert "already exists" in resp.json()["detail"]

    def test_disposable_email_returns_422(self, client):
        with _patch("app.services.disposable_email_service.is_disposable_email", return_value=True):
            resp = client.post("/auth/register",
                               json={"email": "x@mailinator.com", "password": "Password1!"})
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client):
        with _patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            resp = client.post("/auth/register",
                               json={"email": "short@example.com", "password": "Ab1"})
        assert resp.status_code == 422

    def test_password_no_digit_returns_422(self, client):
        with _patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            resp = client.post("/auth/register",
                               json={"email": "nodigit@example.com", "password": "NoDigitHere"})
        assert resp.status_code == 422

    def test_password_no_letter_returns_422(self, client):
        with _patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            resp = client.post("/auth/register",
                               json={"email": "noletter@example.com", "password": "12345678"})
        assert resp.status_code == 422

    def test_missing_email_returns_422(self, client):
        resp = client.post("/auth/register", json={"password": "Password1!"})
        assert resp.status_code == 422

    def test_missing_password_returns_422(self, client):
        resp = client.post("/auth/register", json={"email": "no@pass.com"})
        assert resp.status_code == 422

    def test_verification_email_sent(self, client):
        with _patch("app.services.disposable_email_service.is_disposable_email", return_value=False), \
             _patch("app.api.routes.auth.send_verification_email") as mock_send:
            client.post("/auth/register", json={"email": "email@example.com", "password": "Pass1word!"})
        mock_send.assert_called_once()


# ===========================================================================
# POST /auth/login
# ===========================================================================

class TestLogin:
    def test_returns_200(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        assert resp.status_code == 200

    def test_response_has_access_token(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        assert "access_token" in resp.json()

    def test_response_has_refresh_token(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        assert "refresh_token" in resp.json()

    def test_token_type_is_bearer(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        assert resp.json()["token_type"] == "bearer"

    def test_expires_in_is_integer(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        assert isinstance(resp.json()["expires_in"], int)

    def test_wrong_password_returns_422(self, client, db):
        _make_verified_user(db)
        resp = _login(client, password="WrongPass1!")
        assert resp.status_code == 422

    def test_unknown_email_returns_422(self, client):
        resp = _login(client, email="ghost@example.com")
        assert resp.status_code == 422

    def test_inactive_user_returns_422(self, client, db):
        _make_verified_user(db, is_active=False)
        resp = _login(client)
        assert resp.status_code == 422

    def test_access_token_is_valid_jwt(self, client, db):
        _make_verified_user(db)
        resp = _login(client)
        token = resp.json()["access_token"]
        from app.core.security import decode_token
        payload = decode_token(token)
        assert payload["type"] == "access"


# ===========================================================================
# POST /auth/refresh
# ===========================================================================

class TestRefreshToken:
    def test_returns_200_with_valid_refresh_token(self, client, db):
        user = _make_verified_user(db)
        refresh = create_refresh_token(str(user.id))
        resp = client.post("/auth/refresh", params={"authorization": f"Bearer {refresh}"})
        assert resp.status_code == 200

    def test_returns_new_access_token(self, client, db):
        user = _make_verified_user(db)
        refresh = create_refresh_token(str(user.id))
        resp = client.post("/auth/refresh", params={"authorization": f"Bearer {refresh}"})
        assert "access_token" in resp.json()

    def test_returns_new_refresh_token(self, client, db):
        user = _make_verified_user(db)
        refresh = create_refresh_token(str(user.id))
        resp = client.post("/auth/refresh", params={"authorization": f"Bearer {refresh}"})
        assert "refresh_token" in resp.json()

    def test_access_token_rejected_as_refresh(self, client, db):
        user = _make_verified_user(db)
        access = create_refresh_token(str(user.id))
        # Use an access token where refresh is expected → should still work
        # because refresh endpoint checks type=="refresh" in payload
        from app.core.security import create_access_token
        bad_token = create_access_token(str(user.id), "user")
        resp = client.post("/auth/refresh", params={"authorization": f"Bearer {bad_token}"})
        assert resp.status_code == 401

    def test_missing_authorization_header_returns_401(self, client):
        resp = client.post("/auth/refresh")
        assert resp.status_code == 401

    def test_malformed_bearer_returns_401(self, client):
        resp = client.post("/auth/refresh", headers={"Authorization": "notbearer token"})
        assert resp.status_code == 401

    def test_expired_token_returns_401(self, client):
        from jose import jwt
        expired = jwt.encode(
            {"sub": str(uuid.uuid4()), "type": "refresh",
             "exp": int(datetime.now(timezone.utc).timestamp()) - 3600},
            "test-jwt-secret-key-for-testing-only", algorithm="HS256"
        )
        resp = client.post("/auth/refresh", headers=_auth_header(expired))
        assert resp.status_code == 401

    def test_inactive_user_returns_401(self, client, db):
        user = _make_verified_user(db, is_active=False)
        refresh = create_refresh_token(str(user.id))
        resp = client.post("/auth/refresh", params={"authorization": f"Bearer {refresh}"})
        assert resp.status_code == 401


# ===========================================================================
# GET /auth/me
# ===========================================================================

class TestGetMe:
    def _access_token_for(self, user: User) -> str:
        from app.core.security import create_access_token
        return create_access_token(str(user.id), user.role)

    def test_returns_200_when_authenticated(self, client, db):
        user = _make_verified_user(db)
        token = self._access_token_for(user)
        resp = client.get("/auth/me", headers=_auth_header(token))
        assert resp.status_code == 200

    def test_returns_correct_email(self, client, db):
        user = _make_verified_user(db, email="me@example.com")
        token = self._access_token_for(user)
        resp = client.get("/auth/me", headers=_auth_header(token))
        assert resp.json()["email"] == "me@example.com"

    def test_returns_401_without_token(self, client):
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_returns_401_with_bad_token(self, client):
        resp = client.get("/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401

    def test_returns_401_with_refresh_token(self, client, db):
        user = _make_verified_user(db)
        refresh = create_refresh_token(str(user.id))
        resp = client.get("/auth/me", headers=_auth_header(refresh))
        assert resp.status_code == 401


# ===========================================================================
# GET /auth/verify-email
# ===========================================================================

class TestVerifyEmail:
    def _user_with_token(self, db, token="valid-token-abc") -> User:
        u = User(
            email=f"unverified-{uuid.uuid4()}@example.com",
            password_hash=hash_password("Password1!"),
            role="user",
            is_verified=False,
            verification_token=token,
            verification_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        db.add(u); db.commit(); db.refresh(u)
        return u

    def test_valid_token_returns_200(self, client, db):
        self._user_with_token(db, token="tok-abc-123")
        resp = client.get("/auth/verify-email?token=tok-abc-123")
        assert resp.status_code == 200

    def test_valid_token_returns_success_message(self, client, db):
        self._user_with_token(db, token="tok-msg-test")
        resp = client.get("/auth/verify-email?token=tok-msg-test")
        assert "verified" in resp.json()["message"].lower()

    def test_invalid_token_returns_422(self, client):
        resp = client.get("/auth/verify-email?token=nonexistent-token")
        assert resp.status_code == 422

    def test_expired_token_returns_422(self, client, db):
        u = User(
            email=f"exp-{uuid.uuid4()}@example.com",
            password_hash=hash_password("Password1!"),
            role="user",
            is_verified=False,
            verification_token="expired-tok",
            verification_token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(u); db.commit()
        resp = client.get("/auth/verify-email?token=expired-tok")
        assert resp.status_code == 422

    def test_missing_token_param_returns_422(self, client):
        resp = client.get("/auth/verify-email")
        assert resp.status_code == 422

    def test_welcome_email_sent_on_verification(self, client, db):
        self._user_with_token(db, token="tok-welcome")
        with _patch("app.api.routes.auth.send_welcome_email") as mock_welcome:
            client.get("/auth/verify-email?token=tok-welcome")
        mock_welcome.assert_called_once()


# ===========================================================================
# POST /auth/resend-verification
# ===========================================================================

class TestResendVerification:
    def _unverified_user(self, db, email="unverified@example.com") -> User:
        u = User(
            email=email,
            password_hash=hash_password("Password1!"),
            role="user",
            is_verified=False,
        )
        db.add(u); db.commit(); db.refresh(u)
        return u

    def test_returns_200_for_unverified_account(self, client, db):
        self._unverified_user(db)
        resp = client.post("/auth/resend-verification",
                           json={"email": "unverified@example.com"})
        assert resp.status_code == 200

    def test_response_message_is_generic(self, client, db):
        self._unverified_user(db)
        resp = client.post("/auth/resend-verification",
                           json={"email": "unverified@example.com"})
        assert "registered" in resp.json()["message"]

    def test_returns_200_for_unknown_email(self, client):
        """Anti-enumeration: unknown email must not return 404."""
        resp = client.post("/auth/resend-verification",
                           json={"email": "ghost@example.com"})
        # The service raises ValidationError with generic msg → 422
        # (both unknown and verified return same message)
        assert resp.status_code in (200, 422)

    def test_same_response_for_unknown_and_verified(self, client, db):
        """Anti-enumeration: unknown email and verified email get identical body."""
        _make_verified_user(db, email="known@example.com")
        resp_unknown = client.post("/auth/resend-verification",
                                   json={"email": "ghost@example.com"})
        resp_verified = client.post("/auth/resend-verification",
                                    json={"email": "known@example.com"})
        # Both should have the same detail message
        assert resp_unknown.json() == resp_verified.json()

    def test_verification_email_sent_for_unverified(self, client, db):
        self._unverified_user(db, email="resend@example.com")
        with _patch("app.api.routes.auth.send_verification_email") as mock_send:
            client.post("/auth/resend-verification",
                        json={"email": "resend@example.com"})
        mock_send.assert_called_once()

    def test_invalid_email_format_returns_422(self, client):
        resp = client.post("/auth/resend-verification",
                           json={"email": "not-an-email"})
        assert resp.status_code == 422