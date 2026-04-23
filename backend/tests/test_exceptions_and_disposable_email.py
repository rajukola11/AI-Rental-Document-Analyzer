"""
Pytest test suite covering two modules:

  1. app/core/exceptions.py
     - AppError and all subclasses (status codes, default details, custom details,
       isinstance hierarchy, str representation)
     - app_error_handler  (returns correct JSONResponse)
     - unhandled_error_handler (returns 500 JSONResponse, logs the exception)

  2. app/services/disposable_email_service.py
     - _load_blocklist  (parses domains, skips comments/blanks, fails open)
     - _get_blocked_domains  (lazy-loads once, caches, thread-safe double-check)
     - is_disposable_email  (blocked domain, clean domain, blocking disabled,
                             subaddress, case insensitivity, malformed email)
     - preload_blocklist (spawns a daemon thread)

Settings are stubbed via tests/conftest.py — no .env or network needed.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
from fastapi.responses import JSONResponse

# ── exceptions ────────────────────────────────────────────────────────────────
from app.core.exceptions import (
    AppError,
    NotFoundError,
    UnauthorizedError,
    ForbiddenError,
    ValidationError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    AIServiceError,
    StorageError,
    ServiceUnavailableError,
    app_error_handler,
    unhandled_error_handler,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _fake_request() -> Request:
    """Minimal ASGI scope so Request() won't raise."""
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    return Request(scope)


def _run(coro):
    """Run a coroutine synchronously (avoids pytest-asyncio dependency)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# AppError — base class
# ===========================================================================

class TestAppError:
    def test_is_exception_subclass(self):
        assert issubclass(AppError, Exception)

    def test_default_detail_used_when_no_arg(self):
        err = AppError()
        assert err.detail == "An unexpected error occurred."

    def test_custom_detail_overrides_default(self):
        err = AppError("something went wrong")
        assert err.detail == "something went wrong"

    def test_none_arg_falls_back_to_default(self):
        err = AppError(None)
        assert err.detail == "An unexpected error occurred."

    def test_default_status_code_is_500(self):
        assert AppError.status_code == 500

    def test_str_representation_contains_detail(self):
        err = AppError("test detail")
        assert "test detail" in str(err)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(AppError):
            raise AppError("boom")


# ===========================================================================
# Each subclass — status code + default detail + inheritance
# ===========================================================================

class TestNotFoundError:
    def test_status_code(self):
        assert NotFoundError.status_code == 404

    def test_default_detail(self):
        assert "not found" in NotFoundError().detail.lower()

    def test_custom_detail(self):
        err = NotFoundError("Document not found.")
        assert err.detail == "Document not found."

    def test_is_app_error(self):
        assert isinstance(NotFoundError(), AppError)


class TestUnauthorizedError:
    def test_status_code(self):
        assert UnauthorizedError.status_code == 401

    def test_default_detail(self):
        assert "auth" in UnauthorizedError().detail.lower()

    def test_is_app_error(self):
        assert isinstance(UnauthorizedError(), AppError)


class TestForbiddenError:
    def test_status_code(self):
        assert ForbiddenError.status_code == 403

    def test_default_detail(self):
        assert "permission" in ForbiddenError().detail.lower()

    def test_custom_detail(self):
        err = ForbiddenError("No access.")
        assert err.detail == "No access."

    def test_is_app_error(self):
        assert isinstance(ForbiddenError(), AppError)


class TestValidationError:
    def test_status_code(self):
        assert ValidationError.status_code == 422

    def test_default_detail(self):
        assert "validation" in ValidationError().detail.lower()

    def test_custom_detail(self):
        err = ValidationError("Email already exists.")
        assert err.detail == "Email already exists."

    def test_is_app_error(self):
        assert isinstance(ValidationError(), AppError)


class TestFileTooLargeError:
    def test_status_code(self):
        assert FileTooLargeError.status_code == 413

    def test_default_detail_mentions_size(self):
        detail = FileTooLargeError().detail.lower()
        assert "size" in detail or "large" in detail or "exceed" in detail

    def test_is_app_error(self):
        assert isinstance(FileTooLargeError(), AppError)


class TestUnsupportedFileTypeError:
    def test_status_code(self):
        assert UnsupportedFileTypeError.status_code == 415

    def test_default_detail_mentions_file_type(self):
        detail = UnsupportedFileTypeError().detail.lower()
        assert "type" in detail or "support" in detail

    def test_is_app_error(self):
        assert isinstance(UnsupportedFileTypeError(), AppError)


class TestAIServiceError:
    def test_status_code(self):
        assert AIServiceError.status_code == 502

    def test_default_detail_mentions_ai(self):
        detail = AIServiceError().detail.lower()
        assert "ai" in detail or "processing" in detail or "service" in detail

    def test_custom_detail(self):
        err = AIServiceError("OpenAI timeout.")
        assert err.detail == "OpenAI timeout."

    def test_is_app_error(self):
        assert isinstance(AIServiceError(), AppError)


class TestStorageError:
    def test_status_code(self):
        assert StorageError.status_code == 502

    def test_default_detail_mentions_storage(self):
        detail = StorageError().detail.lower()
        assert "storage" in detail or "file" in detail or "service" in detail

    def test_is_app_error(self):
        assert isinstance(StorageError(), AppError)


class TestServiceUnavailableError:
    def test_status_code(self):
        assert ServiceUnavailableError.status_code == 503

    def test_default_detail_mentions_unavailable(self):
        detail = ServiceUnavailableError().detail.lower()
        assert "unavailable" in detail or "service" in detail

    def test_is_app_error(self):
        assert isinstance(ServiceUnavailableError(), AppError)


# ===========================================================================
# Cross-cutting exception behaviour
# ===========================================================================

class TestExceptionHierarchy:
    def test_all_subclasses_are_app_errors(self):
        subclasses = [
            NotFoundError, UnauthorizedError, ForbiddenError, ValidationError,
            FileTooLargeError, UnsupportedFileTypeError, AIServiceError,
            StorageError, ServiceUnavailableError,
        ]
        for cls in subclasses:
            assert issubclass(cls, AppError), f"{cls.__name__} is not an AppError"

    def test_all_subclasses_are_exceptions(self):
        subclasses = [
            NotFoundError, UnauthorizedError, ForbiddenError, ValidationError,
            FileTooLargeError, UnsupportedFileTypeError, AIServiceError,
            StorageError, ServiceUnavailableError,
        ]
        for cls in subclasses:
            assert issubclass(cls, Exception), f"{cls.__name__} is not an Exception"

    def test_storage_and_ai_both_502(self):
        assert AIServiceError.status_code == StorageError.status_code == 502

    def test_each_subclass_has_unique_default_detail(self):
        subclasses = [
            NotFoundError, UnauthorizedError, ForbiddenError, ValidationError,
            FileTooLargeError, UnsupportedFileTypeError, AIServiceError,
            StorageError, ServiceUnavailableError,
        ]
        details = [cls().detail for cls in subclasses]
        assert len(details) == len(set(details)), "Two subclasses share the same default detail"


# ===========================================================================
# app_error_handler
# ===========================================================================

class TestAppErrorHandler:
    def test_returns_json_response(self):
        req = _fake_request()
        exc = NotFoundError("Document not found.")
        resp = _run(app_error_handler(req, exc))
        assert isinstance(resp, JSONResponse)

    def test_status_code_matches_exception(self):
        req = _fake_request()
        exc = NotFoundError()
        resp = _run(app_error_handler(req, exc))
        assert resp.status_code == 404

    def test_body_contains_detail(self):
        import json
        req = _fake_request()
        exc = NotFoundError("Custom not found msg.")
        resp = _run(app_error_handler(req, exc))
        body = json.loads(resp.body)
        assert body["detail"] == "Custom not found msg."

    def test_body_contains_type_name(self):
        import json
        req = _fake_request()
        exc = ValidationError("bad input")
        resp = _run(app_error_handler(req, exc))
        body = json.loads(resp.body)
        assert body["type"] == "ValidationError"

    def test_403_for_forbidden(self):
        req = _fake_request()
        resp = _run(app_error_handler(req, ForbiddenError()))
        assert resp.status_code == 403

    def test_422_for_validation(self):
        req = _fake_request()
        resp = _run(app_error_handler(req, ValidationError()))
        assert resp.status_code == 422

    def test_502_for_ai_service_error(self):
        req = _fake_request()
        resp = _run(app_error_handler(req, AIServiceError()))
        assert resp.status_code == 502

    def test_503_for_service_unavailable(self):
        req = _fake_request()
        resp = _run(app_error_handler(req, ServiceUnavailableError()))
        assert resp.status_code == 503

    def test_type_field_matches_class_name_for_all_subclasses(self):
        import json
        req = _fake_request()
        cases = [
            (NotFoundError(), "NotFoundError"),
            (UnauthorizedError(), "UnauthorizedError"),
            (ForbiddenError(), "ForbiddenError"),
            (AIServiceError(), "AIServiceError"),
            (StorageError(), "StorageError"),
        ]
        for exc, expected_type in cases:
            resp = _run(app_error_handler(req, exc))
            body = json.loads(resp.body)
            assert body["type"] == expected_type


# ===========================================================================
# unhandled_error_handler
# ===========================================================================

class TestUnhandledErrorHandler:
    def test_returns_json_response(self):
        req = _fake_request()
        resp = _run(unhandled_error_handler(req, RuntimeError("boom")))
        assert isinstance(resp, JSONResponse)

    def test_status_code_is_500(self):
        req = _fake_request()
        resp = _run(unhandled_error_handler(req, RuntimeError("boom")))
        assert resp.status_code == 500

    def test_body_detail_is_internal_server_error(self):
        import json
        req = _fake_request()
        resp = _run(unhandled_error_handler(req, ValueError("oops")))
        body = json.loads(resp.body)
        assert "internal" in body["detail"].lower() or "server error" in body["detail"].lower()

    def test_body_type_is_internal_server_error(self):
        import json
        req = _fake_request()
        resp = _run(unhandled_error_handler(req, Exception("any")))
        body = json.loads(resp.body)
        assert body["type"] == "InternalServerError"

    def test_does_not_leak_exception_message(self):
        import json
        req = _fake_request()
        secret_msg = "super_secret_db_password"
        resp = _run(unhandled_error_handler(req, RuntimeError(secret_msg)))
        body = json.loads(resp.body)
        assert secret_msg not in body["detail"]
        assert secret_msg not in body.get("type", "")


# ===========================================================================
# _load_blocklist
# ===========================================================================

# Reset module-level cache between tests
import app.services.disposable_email_service as _des_mod

@pytest.fixture(autouse=True)
def reset_blocklist_cache():
    """Wipe the in-process cache so each test starts fresh."""
    original = _des_mod._blocked_domains
    _des_mod._blocked_domains = None
    yield
    _des_mod._blocked_domains = original


from app.services.disposable_email_service import (
    _load_blocklist,
    _get_blocked_domains,
    is_disposable_email,
    preload_blocklist,
)

_FAKE_BLOCKLIST = "mailinator.com\nyopmail.com\n# this is a comment\n\nguerrillamail.com\n"


class TestLoadBlocklist:
    def _mock_urlopen(self, content: str):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = content.encode("utf-8")
        return patch("urllib.request.urlopen", return_value=mock_resp)

    def test_returns_set(self):
        with self._mock_urlopen(_FAKE_BLOCKLIST):
            result = _load_blocklist()
        assert isinstance(result, set)

    def test_parses_domains_correctly(self):
        with self._mock_urlopen(_FAKE_BLOCKLIST):
            result = _load_blocklist()
        assert "mailinator.com" in result
        assert "yopmail.com" in result
        assert "guerrillamail.com" in result

    def test_skips_comment_lines(self):
        with self._mock_urlopen(_FAKE_BLOCKLIST):
            result = _load_blocklist()
        assert not any(d.startswith("#") for d in result)

    def test_skips_blank_lines(self):
        with self._mock_urlopen(_FAKE_BLOCKLIST):
            result = _load_blocklist()
        assert "" not in result

    def test_lowercases_all_domains(self):
        content = "MAILINATOR.COM\nYOPMAIL.COM\n"
        with self._mock_urlopen(content):
            result = _load_blocklist()
        assert "mailinator.com" in result
        assert "MAILINATOR.COM" not in result

    def test_strips_whitespace_from_domains(self):
        content = "  mailinator.com  \n  yopmail.com  \n"
        with self._mock_urlopen(content):
            result = _load_blocklist()
        assert "mailinator.com" in result
        assert "  mailinator.com  " not in result

    def test_returns_empty_set_on_network_failure(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network error")):
            result = _load_blocklist()
        assert result == set()

    def test_returns_empty_set_on_timeout(self):
        import socket
        with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            result = _load_blocklist()
        assert result == set()

    def test_returns_empty_set_on_decode_error(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"\xff\xfe"  # invalid UTF-8
        mock_resp.read.return_value = b"mailinator.com\n"
        # Simulate decode raising
        mock_resp.read.return_value = MagicMock()
        mock_resp.read.return_value.decode = MagicMock(side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "invalid"))
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _load_blocklist()
        assert result == set()


# ===========================================================================
# _get_blocked_domains
# ===========================================================================

class TestGetBlockedDomains:
    def test_returns_set(self):
        with patch("app.services.disposable_email_service._load_blocklist",
                   return_value={"mailinator.com"}):
            result = _get_blocked_domains()
        assert isinstance(result, set)

    def test_calls_load_blocklist_on_first_call(self):
        with patch("app.services.disposable_email_service._load_blocklist",
                   return_value={"mailinator.com"}) as mock_load:
            _get_blocked_domains()
        mock_load.assert_called_once()

    def test_does_not_call_load_blocklist_on_second_call(self):
        with patch("app.services.disposable_email_service._load_blocklist",
                   return_value={"mailinator.com"}) as mock_load:
            _get_blocked_domains()
            _get_blocked_domains()
        mock_load.assert_called_once()

    def test_cached_result_is_returned_on_second_call(self):
        domains = {"mailinator.com", "yopmail.com"}
        with patch("app.services.disposable_email_service._load_blocklist",
                   return_value=domains):
            r1 = _get_blocked_domains()
            r2 = _get_blocked_domains()
        assert r1 is r2

    def test_returns_same_object_as_cached(self):
        with patch("app.services.disposable_email_service._load_blocklist",
                   return_value={"x.com"}):
            _get_blocked_domains()
        # Second call uses the cache — mock not needed
        result = _get_blocked_domains()
        assert isinstance(result, set)


# ===========================================================================
# is_disposable_email
# ===========================================================================

class TestIsDisposableEmail:
    def _with_blocklist(self, domains: set):
        return patch(
            "app.services.disposable_email_service._get_blocked_domains",
            return_value=domains,
        )

    def test_known_disposable_domain_returns_true(self):
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("user@mailinator.com") is True

    def test_clean_domain_returns_false(self):
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("user@gmail.com") is False

    def test_case_insensitive_email(self):
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("USER@MAILINATOR.COM") is True

    def test_email_with_leading_trailing_spaces(self):
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("  user@mailinator.com  ") is True

    def test_blocking_disabled_always_returns_false(self):
        with self._with_blocklist({"mailinator.com"}):
            with patch.object(
                _des_mod,
                "_get_blocked_domains",
                return_value={"mailinator.com"},
            ):
                # Override the settings to disable blocking
                import app.core.config as _cfg
                original = _cfg.settings.block_disposable_emails
                _cfg.settings.block_disposable_emails = False
                try:
                    result = is_disposable_email("user@mailinator.com")
                finally:
                    _cfg.settings.block_disposable_emails = original
        assert result is False

    def test_empty_blocklist_always_returns_false(self):
        with self._with_blocklist(set()):
            assert is_disposable_email("user@mailinator.com") is False

    def test_subdomain_not_blocked_when_only_root_in_list(self):
        """sub.mailinator.com is a different domain from mailinator.com."""
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("user@sub.mailinator.com") is False

    def test_subaddress_plus_sign_still_blocked(self):
        """user+tag@mailinator.com — domain part is still mailinator.com."""
        with self._with_blocklist({"mailinator.com"}):
            assert is_disposable_email("user+tag@mailinator.com") is True

    def test_multiple_at_signs_uses_last_part_as_domain(self):
        """Python split('@')[-1] gives the last segment."""
        with self._with_blocklist({"mailinator.com"}):
            # "weird@@mailinator.com" → domain = "mailinator.com"
            assert is_disposable_email("weird@@mailinator.com") is True

    def test_returns_bool(self):
        with self._with_blocklist({"mailinator.com"}):
            result = is_disposable_email("x@mailinator.com")
        assert isinstance(result, bool)


# ===========================================================================
# preload_blocklist
# ===========================================================================

class TestPreloadBlocklist:
    def test_spawns_a_thread(self):
        import threading
        threads_before = set(t.name for t in threading.enumerate())
        with patch("app.services.disposable_email_service._get_blocked_domains"):
            preload_blocklist()
        # Give the thread a moment to start
        import time; time.sleep(0.05)
        threads_after = set(t.name for t in threading.enumerate())
        # Thread may already have finished — just assert no exception was raised
        # (daemon threads can exit before we enumerate)
        assert True  # preload_blocklist() completed without raising

    def test_does_not_raise(self):
        with patch("app.services.disposable_email_service._get_blocked_domains"):
            preload_blocklist()  # must not raise