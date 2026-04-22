import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# ── SQLite-compatible UUID type (Postgres UUID won't work in SQLite) ──────────
import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa_types


class _SqliteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return uuid.UUID(value) if value else None


_pg.UUID = _SqliteUUID  # patch before any model import

# ── Import models + service (conftest already patched config / logging) ───────
from app.db.base import Base
from app.models import user as _user_mod      # noqa: F401 — needed for relationships
from app.models import document as _doc_mod   # noqa: F401
from app.models import analysis as _ana_mod   # noqa: F401
from app.models import payment as _pay_mod    # noqa: F401
from app.models.user import User, FREE_UPLOAD_LIMIT

from app.core.exceptions import ValidationError
from app.core.security import verify_password

from app.services.user_service import (
    get_user_by_email,
    get_user_by_id,
    get_user_by_verification_token,
    create_user,
    verify_email_token,
    resend_verification,
    authenticate_user,
    increment_uploads,
    _generate_verification_token,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture()
def db(engine):
    with Session(engine) as session:
        yield session


def _make_user(
    db: Session,
    email: str = "alice@example.com",
    password_hash: str = "fakehash",
    role: str = "user",
    is_verified: bool = True,
    is_active: bool = True,
    uploads_used: int = 0,
    upload_credits: int = 0,
    verification_token: str | None = None,
    verification_token_expires_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        role=role,
        is_verified=is_verified,
        is_active=is_active,
        uploads_used=uploads_used,
        upload_credits=upload_credits,
        verification_token=verification_token,
        verification_token_expires_at=verification_token_expires_at,
    )
    db.add(user)
    db.flush()
    return user


# ===========================================================================
# get_user_by_email
# ===========================================================================

class TestGetUserByEmail:
    def test_returns_user_when_found(self, db):
        _make_user(db, email="alice@example.com")
        result = get_user_by_email(db, "alice@example.com")
        assert result is not None
        assert result.email == "alice@example.com"

    def test_returns_none_when_not_found(self, db):
        result = get_user_by_email(db, "nobody@example.com")
        assert result is None

    def test_normalises_email_to_lowercase(self, db):
        _make_user(db, email="alice@example.com")
        result = get_user_by_email(db, "ALICE@EXAMPLE.COM")
        assert result is not None

    def test_strips_whitespace_from_email(self, db):
        _make_user(db, email="alice@example.com")
        result = get_user_by_email(db, "  alice@example.com  ")
        assert result is not None

    def test_different_email_returns_none(self, db):
        _make_user(db, email="alice@example.com")
        result = get_user_by_email(db, "bob@example.com")
        assert result is None


# ===========================================================================
# get_user_by_id
# ===========================================================================

class TestGetUserById:
    def test_returns_user_when_found(self, db):
        user = _make_user(db)
        result = get_user_by_id(db, user.id)
        assert result is not None
        assert result.id == user.id

    def test_returns_none_for_unknown_id(self, db):
        result = get_user_by_id(db, uuid.uuid4())
        assert result is None


# ===========================================================================
# get_user_by_verification_token
# ===========================================================================

class TestGetUserByVerificationToken:
    def test_returns_user_for_valid_token(self, db):
        user = _make_user(db, verification_token="abc123token")
        result = get_user_by_verification_token(db, "abc123token")
        assert result is not None
        assert result.id == user.id

    def test_returns_none_for_unknown_token(self, db):
        result = get_user_by_verification_token(db, "nonexistent-token")
        assert result is None

    def test_returns_none_when_token_is_null(self, db):
        _make_user(db, verification_token=None)
        result = get_user_by_verification_token(db, "")
        assert result is None


# ===========================================================================
# _generate_verification_token
# ===========================================================================

class TestGenerateVerificationToken:
    def test_returns_string(self, db):
        user = _make_user(db)
        token = _generate_verification_token(db, user)
        assert isinstance(token, str)

    def test_token_is_non_empty(self, db):
        user = _make_user(db)
        token = _generate_verification_token(db, user)
        assert len(token) > 10

    def test_token_assigned_to_user(self, db):
        user = _make_user(db)
        token = _generate_verification_token(db, user)
        assert user.verification_token == token

    def test_expiry_set_on_user(self, db):
        user = _make_user(db)
        _generate_verification_token(db, user)
        assert user.verification_token_expires_at is not None

    def test_expiry_is_in_the_future(self, db):
        user = _make_user(db)
        _generate_verification_token(db, user)
        now = datetime.now(timezone.utc)
        expires = user.verification_token_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires > now

    def test_expiry_matches_settings(self, db):
        user = _make_user(db)
        before = datetime.now(timezone.utc)
        _generate_verification_token(db, user)
        after = datetime.now(timezone.utc)
        expires = user.verification_token_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        expected_min = before + timedelta(hours=24) - timedelta(seconds=5)
        expected_max = after + timedelta(hours=24) + timedelta(seconds=5)
        assert expected_min <= expires <= expected_max

    def test_two_calls_produce_different_tokens(self, db):
        user = _make_user(db)
        t1 = _generate_verification_token(db, user)
        t2 = _generate_verification_token(db, user)
        assert t1 != t2


# ===========================================================================
# create_user
# ===========================================================================

class TestCreateUser:
    def test_returns_user_and_token_tuple(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            result = create_user(db, "new@example.com", "Password1!")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_user_has_correct_email(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "New@Example.COM", "Password1!")
        assert user.email == "new@example.com"  # normalised

    def test_email_is_normalised_to_lowercase(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "UPPER@EXAMPLE.COM", "Password1!")
        assert user.email == "upper@example.com"

    def test_password_is_hashed(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "pw@example.com", "PlainText99!")
        assert user.password_hash != "PlainText99!"
        assert verify_password("PlainText99!", user.password_hash)

    def test_user_role_defaults_to_user(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "role@example.com", "Password1!")
        assert user.role == "user"

    def test_user_is_not_verified_on_creation(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "unverified@example.com", "Password1!")
        assert user.is_verified is False

    def test_verification_token_is_returned(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            _, token = create_user(db, "token@example.com", "Password1!")
        assert isinstance(token, str)
        assert len(token) > 10

    def test_verification_token_stored_on_user(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, token = create_user(db, "stored@example.com", "Password1!")
        assert user.verification_token == token

    def test_full_name_stored_when_provided(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "name@example.com", "Password1!", full_name="Alice Smith")
        assert user.full_name == "Alice Smith"

    def test_full_name_none_when_not_provided(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "noname@example.com", "Password1!")
        assert user.full_name is None

    def test_duplicate_email_raises_validation_error(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            create_user(db, "dup@example.com", "Password1!")
            with pytest.raises(ValidationError, match="already exists"):
                create_user(db, "dup@example.com", "AnotherPass1!")

    def test_duplicate_email_case_insensitive(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            create_user(db, "dup@example.com", "Password1!")
            with pytest.raises(ValidationError):
                create_user(db, "DUP@EXAMPLE.COM", "AnotherPass1!")

    def test_disposable_email_raises_validation_error(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=True):
            with pytest.raises(ValidationError, match="Disposable"):
                create_user(db, "temp@mailinator.com", "Password1!")

    def test_user_is_added_to_db(self, db):
        with patch("app.services.disposable_email_service.is_disposable_email", return_value=False):
            user, _ = create_user(db, "persist@example.com", "Password1!")
        found = get_user_by_email(db, "persist@example.com")
        assert found is not None
        assert found.id == user.id


# ===========================================================================
# verify_email_token
# ===========================================================================

class TestVerifyEmailToken:
    def _future(self, hours: int = 24) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=hours)

    def _past(self, hours: int = 1) -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=hours)

    def test_valid_token_marks_user_verified(self, db):
        user = _make_user(
            db,
            is_verified=False,
            verification_token="valid-token-abc",
            verification_token_expires_at=self._future(),
        )
        verify_email_token(db, "valid-token-abc")
        assert user.is_verified is True

    def test_valid_token_clears_token(self, db):
        user = _make_user(
            db,
            is_verified=False,
            verification_token="clear-me",
            verification_token_expires_at=self._future(),
        )
        verify_email_token(db, "clear-me")
        assert user.verification_token is None

    def test_valid_token_clears_expiry(self, db):
        user = _make_user(
            db,
            is_verified=False,
            verification_token="expire-me",
            verification_token_expires_at=self._future(),
        )
        verify_email_token(db, "expire-me")
        assert user.verification_token_expires_at is None

    def test_valid_token_returns_user(self, db):
        user = _make_user(
            db,
            is_verified=False,
            verification_token="return-me",
            verification_token_expires_at=self._future(),
        )
        result = verify_email_token(db, "return-me")
        assert result.id == user.id

    def test_invalid_token_raises_validation_error(self, db):
        with pytest.raises(ValidationError, match="Invalid verification link"):
            verify_email_token(db, "does-not-exist")

    def test_expired_token_raises_validation_error(self, db):
        _make_user(
            db,
            is_verified=False,
            verification_token="expired-token",
            verification_token_expires_at=self._past(),
        )
        with pytest.raises(ValidationError, match="expired"):
            verify_email_token(db, "expired-token")

    def test_none_expiry_raises_validation_error(self, db):
        """A token with no expiry set should be treated as expired."""
        _make_user(
            db,
            is_verified=False,
            verification_token="no-expiry-token",
            verification_token_expires_at=None,
        )
        with pytest.raises(ValidationError):
            verify_email_token(db, "no-expiry-token")

    def test_already_verified_is_idempotent(self, db):
        """Calling verify on an already-verified user must not raise."""
        user = _make_user(
            db,
            is_verified=True,
            verification_token="already-done",
            verification_token_expires_at=self._future(),
        )
        result = verify_email_token(db, "already-done")
        assert result.is_verified is True

    def test_naive_datetime_handled(self, db):
        """Timezone-naive expiry datetime should be treated as UTC and accepted if future."""
        future_naive = datetime.utcnow() + timedelta(hours=24)  # naive
        user = _make_user(
            db,
            is_verified=False,
            verification_token="naive-dt-token",
            verification_token_expires_at=future_naive,
        )
        result = verify_email_token(db, "naive-dt-token")
        assert result.is_verified is True


# ===========================================================================
# resend_verification
# ===========================================================================

class TestResendVerification:
    def test_returns_user_and_new_token(self, db):
        _make_user(db, email="resend@example.com", is_verified=False)
        user, token = resend_verification(db, "resend@example.com")
        assert isinstance(user, User)
        assert isinstance(token, str)
        assert len(token) > 10

    def test_new_token_stored_on_user(self, db):
        _make_user(db, email="store@example.com", is_verified=False)
        user, token = resend_verification(db, "store@example.com")
        assert user.verification_token == token

    def test_unknown_email_raises_generic_message(self, db):
        with pytest.raises(ValidationError) as exc_info:
            resend_verification(db, "ghost@example.com")
        assert "If that email is registered" in str(exc_info.value)

    def test_already_verified_raises_generic_message(self, db):
        _make_user(db, email="verified@example.com", is_verified=True)
        with pytest.raises(ValidationError) as exc_info:
            resend_verification(db, "verified@example.com")
        assert "If that email is registered" in str(exc_info.value)

    def test_same_message_for_unknown_and_verified(self, db):
        """Anti-enumeration: unknown and already-verified give identical messages."""
        _make_user(db, email="known@example.com", is_verified=True)
        try:
            resend_verification(db, "ghost@example.com")
        except ValidationError as e1:
            msg1 = str(e1)
        try:
            resend_verification(db, "known@example.com")
        except ValidationError as e2:
            msg2 = str(e2)
        assert msg1 == msg2

    def test_new_token_replaces_old_token(self, db):
        user = _make_user(
            db,
            email="replace@example.com",
            is_verified=False,
            verification_token="old-token",
        )
        _, new_token = resend_verification(db, "replace@example.com")
        assert new_token != "old-token"
        assert user.verification_token == new_token


# ===========================================================================
# authenticate_user
# ===========================================================================

class TestAuthenticateUser:
    def _hashed_user(self, db, email: str, password: str, is_active: bool = True) -> User:
        from app.core.security import hash_password
        return _make_user(
            db,
            email=email,
            password_hash=hash_password(password),
            is_active=is_active,
            is_verified=True,
        )

    def test_correct_credentials_returns_user(self, db):
        self._hashed_user(db, "auth@example.com", "Correct1!")
        result = authenticate_user(db, "auth@example.com", "Correct1!")
        assert result.email == "auth@example.com"

    def test_wrong_password_raises_validation_error(self, db):
        self._hashed_user(db, "wp@example.com", "Correct1!")
        with pytest.raises(ValidationError, match="Invalid email or password"):
            authenticate_user(db, "wp@example.com", "WrongPassword!")

    def test_unknown_email_raises_validation_error(self, db):
        with pytest.raises(ValidationError, match="Invalid email or password"):
            authenticate_user(db, "ghost@example.com", "anypassword")

    def test_inactive_account_raises_validation_error(self, db):
        self._hashed_user(db, "inactive@example.com", "Pass1!", is_active=False)
        with pytest.raises(ValidationError, match="disabled"):
            authenticate_user(db, "inactive@example.com", "Pass1!")

    def test_unknown_email_and_wrong_password_same_message(self, db):
        """Prevents user enumeration via different error messages."""
        self._hashed_user(db, "real@example.com", "Pass1!")
        try:
            authenticate_user(db, "ghost@example.com", "any")
        except ValidationError as e1:
            msg1 = str(e1)
        try:
            authenticate_user(db, "real@example.com", "wrong")
        except ValidationError as e2:
            msg2 = str(e2)
        assert msg1 == msg2

    def test_email_normalised_during_auth(self, db):
        self._hashed_user(db, "norm@example.com", "Pass1!")
        result = authenticate_user(db, "NORM@EXAMPLE.COM", "Pass1!")
        assert result is not None


# ===========================================================================
# increment_uploads
# ===========================================================================

class TestIncrementUploads:
    def test_increments_uploads_used_by_one(self, db):
        user = _make_user(db, uploads_used=0)
        increment_uploads(db, user.id)
        db.refresh(user)
        assert user.uploads_used == 1

    def test_increments_from_non_zero(self, db):
        user = _make_user(db, uploads_used=3)
        increment_uploads(db, user.id)
        db.refresh(user)
        assert user.uploads_used == 4

    def test_does_not_affect_other_users(self, db):
        user_a = _make_user(db, email="a@example.com", uploads_used=0)
        user_b = _make_user(db, email="b@example.com", uploads_used=0)
        increment_uploads(db, user_a.id)
        db.refresh(user_b)
        assert user_b.uploads_used == 0


# ===========================================================================
# User model properties  (can_upload, free_uploads_remaining)
# ===========================================================================

class TestUserModelProperties:
    def test_unverified_user_cannot_upload(self, db):
        user = _make_user(db, is_verified=False, uploads_used=0)
        assert user.can_upload is False

    def test_verified_user_with_free_slots_can_upload(self, db):
        user = _make_user(db, is_verified=True, uploads_used=0)
        assert user.can_upload is True

    def test_verified_user_at_limit_cannot_upload_without_credits(self, db):
        user = _make_user(db, is_verified=True, uploads_used=FREE_UPLOAD_LIMIT, upload_credits=0)
        assert user.can_upload is False

    def test_verified_user_at_limit_can_upload_with_credits(self, db):
        user = _make_user(db, is_verified=True, uploads_used=FREE_UPLOAD_LIMIT, upload_credits=1)
        assert user.can_upload is True

    def test_free_uploads_remaining_decreases(self, db):
        user = _make_user(db, uploads_used=0)
        assert user.free_uploads_remaining == FREE_UPLOAD_LIMIT

    def test_free_uploads_remaining_at_limit_is_zero(self, db):
        user = _make_user(db, uploads_used=FREE_UPLOAD_LIMIT)
        assert user.free_uploads_remaining == 0

    def test_free_uploads_remaining_never_negative(self, db):
        user = _make_user(db, uploads_used=FREE_UPLOAD_LIMIT + 5)
        assert user.free_uploads_remaining == 0

    def test_free_uploads_remaining_one_used(self, db):
        user = _make_user(db, uploads_used=1)
        assert user.free_uploads_remaining == FREE_UPLOAD_LIMIT - 1