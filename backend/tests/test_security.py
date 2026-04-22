"""
tests/test_security.py

Pytest test suite for app/core/security.py

Covers:
- hash_password / verify_password
- create_access_token / create_refresh_token
- decode_token (happy path, expiry, wrong secret, wrong algo, bad token)

Settings are stubbed via tests/conftest.py — no real .env needed.
"""

import pytest
from datetime import datetime, timezone
from jose import jwt, JWTError

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

FAKE_SECRET = "test-jwt-secret-key-for-testing-only"
FAKE_ALGORITHM = "HS256"


# ===========================================================================
# Password hashing
# ===========================================================================

class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("mysecretpassword")
        assert isinstance(result, str)

    def test_result_is_not_plaintext(self):
        pw = "mysecretpassword"
        assert hash_password(pw) != pw

    def test_different_calls_produce_different_hashes(self):
        """bcrypt salts are random — two hashes of the same password differ."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2

    def test_hash_looks_like_bcrypt(self):
        h = hash_password("password123")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_empty_string_is_hashable(self):
        """Edge case: empty password should not raise."""
        result = hash_password("")
        assert isinstance(result, str)


class TestVerifyPassword:
    def test_correct_password_returns_true(self):
        pw = "correct_horse_battery_staple"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_wrong_password_returns_false(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_password_against_its_hash(self):
        hashed = hash_password("")
        assert verify_password("", hashed) is True

    def test_empty_password_against_real_hash_returns_false(self):
        hashed = hash_password("not_empty")
        assert verify_password("", hashed) is False

    def test_case_sensitive(self):
        hashed = hash_password("Password123")
        assert verify_password("password123", hashed) is False

    def test_roundtrip_unicode(self):
        pw = "pässwörd_ünïcödé"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True


# ===========================================================================
# JWT — access token
# ===========================================================================

class TestCreateAccessToken:
    def test_returns_string(self):
        token = create_access_token("user-id-123", "user")
        assert isinstance(token, str)

    def test_token_is_decodable(self):
        token = create_access_token("user-id-123", "user")
        payload = decode_token(token)
        assert payload["sub"] == "user-id-123"

    def test_token_contains_role(self):
        token = create_access_token("user-id-123", "admin")
        payload = decode_token(token)
        assert payload["role"] == "admin"

    def test_token_type_is_access(self):
        token = create_access_token("user-id-123", "user")
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_token_has_iat_and_exp(self):
        token = create_access_token("user-id-123", "user")
        payload = decode_token(token)
        assert "iat" in payload
        assert "exp" in payload

    def test_exp_is_in_the_future(self):
        token = create_access_token("user-id-123", "user")
        payload = decode_token(token)
        now = datetime.now(timezone.utc).timestamp()
        assert payload["exp"] > now

    def test_exp_is_roughly_60_minutes_from_now(self):
        token = create_access_token("user-id-123", "user")
        payload = decode_token(token)
        delta = payload["exp"] - payload["iat"]
        # Allow ±20 seconds tolerance around 3600 seconds
        assert 3580 <= delta <= 3620

    def test_different_subjects_produce_different_tokens(self):
        t1 = create_access_token("user-1", "user")
        t2 = create_access_token("user-2", "user")
        assert t1 != t2

    def test_different_roles_produce_different_tokens(self):
        t1 = create_access_token("user-1", "user")
        t2 = create_access_token("user-1", "admin")
        assert t1 != t2


# ===========================================================================
# JWT — refresh token
# ===========================================================================

class TestCreateRefreshToken:
    def test_returns_string(self):
        token = create_refresh_token("user-id-456")
        assert isinstance(token, str)

    def test_token_type_is_refresh(self):
        token = create_refresh_token("user-id-456")
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_token_contains_subject(self):
        token = create_refresh_token("user-id-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-id-456"

    def test_refresh_token_has_no_role_field(self):
        token = create_refresh_token("user-id-456")
        payload = decode_token(token)
        assert "role" not in payload

    def test_exp_is_roughly_7_days(self):
        token = create_refresh_token("user-id-456")
        payload = decode_token(token)
        delta = payload["exp"] - payload["iat"]
        seven_days = 7 * 24 * 3600
        assert abs(delta - seven_days) < 60  # within 60 seconds

    def test_refresh_exp_longer_than_access_exp(self):
        access = create_access_token("u", "user")
        refresh = create_refresh_token("u")
        access_exp = decode_token(access)["exp"]
        refresh_exp = decode_token(refresh)["exp"]
        assert refresh_exp > access_exp


# ===========================================================================
# JWT — decode_token
# ===========================================================================

class TestDecodeToken:
    def test_valid_access_token_returns_payload(self):
        token = create_access_token("abc", "user")
        payload = decode_token(token)
        assert payload["sub"] == "abc"

    def test_valid_refresh_token_returns_payload(self):
        token = create_refresh_token("xyz")
        payload = decode_token(token)
        assert payload["sub"] == "xyz"

    def test_wrong_secret_raises(self):
        bad_token = jwt.encode(
            {
                "sub": "x",
                "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
            },
            "wrong-secret",
            algorithm=FAKE_ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_token(bad_token)

    def test_expired_token_raises(self):
        now = int(datetime.now(timezone.utc).timestamp())
        expired = jwt.encode(
            {"sub": "x", "iat": now - 7200, "exp": now - 3600},
            FAKE_SECRET,
            algorithm=FAKE_ALGORITHM,
        )
        with pytest.raises(JWTError):
            decode_token(expired)

    def test_malformed_token_raises(self):
        with pytest.raises(JWTError):
            decode_token("this.is.not.a.jwt")

    def test_empty_string_raises(self):
        with pytest.raises(JWTError):
            decode_token("")

    def test_wrong_algorithm_raises(self):
        """Token signed with HS512 should fail our HS256-only decoder."""
        bad_algo_token = jwt.encode(
            {
                "sub": "x",
                "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
            },
            FAKE_SECRET,
            algorithm="HS512",
        )
        with pytest.raises(JWTError):
            decode_token(bad_algo_token)

    def test_none_algorithm_attack_is_rejected(self):
        """The 'none' algorithm attack must not succeed."""
        header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
        payload_b64 = "eyJzdWIiOiJoYWNrZXIifQ"          # {"sub":"hacker"}
        none_token = f"{header}.{payload_b64}."
        with pytest.raises(JWTError):
            decode_token(none_token)

    def test_token_without_sub_still_decodable(self):
        """decode_token should not enforce presence of 'sub' — that's the caller's job."""
        token = jwt.encode(
            {
                "custom": "value",
                "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
            },
            FAKE_SECRET,
            algorithm=FAKE_ALGORITHM,
        )
        payload = decode_token(token)
        assert payload["custom"] == "value"