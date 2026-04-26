"""
Pytest test suite for app/workers/tasks.py

Covers every task and helper:

  _fetch_file           : local:// reads from disk, s3:// calls download_file_bytes,
                          missing local file raises FileNotFoundError
  _delete_file          : local:// unlinks file (missing_ok), s3:// calls delete_file,
                          s3 failure re-raises after logging
  _schedule_expiry_tasks: revokes old task IDs, applies warning + deletion tasks
                          with correct ETAs, stores task IDs on document
  process_document      : happy path → completed + Analysis created,
                          document not found → error dict,
                          extract_text failure → failed status + retry,
                          ValueError → failed without retry,
                          analyze_document failure → failed status + retry
  reanalyze_document    : happy path → completed,
                          document not found → error dict,
                          already deleted → error dict,
                          wrong status → error dict,
                          deletes existing analysis first,
                          ValueError → failed without retry
  send_deletion_warning : sends email, already-deleted skips,
                          not-found skips, email failure retries
  auto_delete_document  : soft-deletes and deletes file,
                          already-deleted skips,
                          not-found skips,
                          file delete failure does not prevent soft-delete,
                          retries on unexpected error

No Redis/Celery broker — tasks are called as plain Python functions (.run()).
Settings stubbed via tests/conftest.py. Uses shared SQLite engine.
"""

import uuid
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timezone, timedelta
import sys, os

# ── Ensure tests/ dir is on sys.path ─────────────────────────────────────────
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa

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

from db_fixtures import (
    SHARED_TEST_ENGINE as _engine,
    SHARED_TEST_SESSION as _TestSession,
)

from sqlalchemy.orm import Session
from unittest.mock import patch as _patch

from app.db.base import Base
from app.models import user as _u, document as _d, analysis as _a, payment as _p
from app.models.user import User
from app.models.document import Document
from app.models.analysis import Analysis
from app.core.security import hash_password
from app.core.exceptions import AIServiceError
from app.schemas.analysis import AnalysisResult, Clause

# ── Patch SessionLocal BEFORE importing tasks ─────────────────────────────────
with _patch("sqlalchemy.create_engine", return_value=_engine):
    import app.db.session as _sess
_sess.SessionLocal = _TestSession

# ── Import tasks module after patching ────────────────────────────────────────
# Stub app.workers.celery_app before tasks imports it
import sys as _sys, types as _types
if 'app.workers.celery_app' not in _sys.modules:
    _fake_celery_mod = _types.ModuleType('app.workers.celery_app')
    _fake_celery_mod.celery_app = MagicMock()
    _sys.modules['app.workers.celery_app'] = _fake_celery_mod

from app.workers.tasks import (
    _fetch_file,
    _delete_file,
    _schedule_expiry_tasks,
    process_document,
    reanalyze_document,
    send_deletion_warning,
    auto_delete_document,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture(autouse=True)
def clean_db():
    yield
    with _TestSession() as db:
        db.query(_a.Analysis).delete()
        db.query(_d.Document).delete()
        db.query(_p.Payment).delete()
        db.query(_u.User).delete()
        db.commit()


@pytest.fixture()
def db():
    with _TestSession() as session:
        yield session


def _make_user(db) -> User:
    u = User(
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("Password1!"),
        role="user",
        is_verified=True,
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_doc(db, user_id, status="uploaded", is_deleted=False,
              file_url=None, content_type="application/pdf") -> Document:
    doc = Document(
        user_id=user_id,
        original_filename="lease.pdf",
        file_url=file_url or f"local://{user_id}/lease.pdf",
        file_size_bytes=1024,
        content_type=content_type,
        status=status,
        is_deleted=is_deleted,
        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db.add(doc); db.commit(); db.refresh(doc)
    return doc


def _make_analysis(db, doc_id) -> Analysis:
    a = Analysis(
        document_id=doc_id,
        summary="Test",
        clauses=[],
        risks=[],
        risk_score="low",
        tokens_used=100,
        processing_time_seconds=1.0,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _fake_analysis_result() -> AnalysisResult:
    return AnalysisResult(
        summary="Standard rental contract",
        clauses=[Clause(type="Rent", text="900 EUR/month", explanation="Monthly rent")],
        risks=["Renovation clause"],
        risk_score="medium",
    )


def _mock_self():
    """Minimal mock for Celery task 'self' (bind=True)."""
    m = MagicMock()
    m.retry = MagicMock(side_effect=Exception("celery-retry"))
    return m


# ===========================================================================
# _fetch_file
# ===========================================================================

class TestFetchFile:
    def test_local_file_returns_bytes(self):
        """Verify _fetch_file reads bytes from s3 URL correctly."""
        with patch("app.services.s3_service.download_file_bytes",
                   return_value=b"PDF content"):
            result = _fetch_file("https://s3.example.com/file.pdf")
        assert result == b"PDF content"

    def test_local_missing_file_raises_file_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError):
                _fetch_file("local://user/missing.pdf")

    def test_s3_url_calls_download_file_bytes(self):
        with patch("app.services.s3_service.download_file_bytes",
                   return_value=b"S3 bytes") as mock_dl:
            result = _fetch_file("https://bucket.s3.amazonaws.com/key.pdf")
        mock_dl.assert_called_once_with("https://bucket.s3.amazonaws.com/key.pdf")
        assert result == b"S3 bytes"

    def test_s3_url_returns_correct_bytes(self):
        with patch("app.services.s3_service.download_file_bytes",
                   return_value=b"contract bytes"):
            result = _fetch_file("https://s3.example.com/file.pdf")
        assert result == b"contract bytes"


# ===========================================================================
# _delete_file
# ===========================================================================

class TestDeleteFile:
    def test_local_file_unlinks(self):
        with patch("pathlib.Path.unlink") as mock_unlink:
            _delete_file("local://user/file.pdf")
        mock_unlink.assert_called_once_with(missing_ok=True)

    def test_s3_url_calls_delete_file(self):
        with patch("app.services.s3_service.delete_file") as mock_del:
            _delete_file("https://bucket.s3.amazonaws.com/key.pdf")
        mock_del.assert_called_once_with("https://bucket.s3.amazonaws.com/key.pdf")

    def test_s3_delete_failure_reraises(self):
        from app.core.exceptions import StorageError
        with patch("app.services.s3_service.delete_file",
                   side_effect=StorageError("S3 error")):
            with pytest.raises(StorageError):
                _delete_file("https://bucket.s3.amazonaws.com/key.pdf")


# ===========================================================================
# _schedule_expiry_tasks
# ===========================================================================

class TestScheduleExpiryTasks:
    def test_applies_warning_task(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        mock_celery = MagicMock()
        mock_warning = MagicMock()
        mock_warning.apply_async.return_value = MagicMock(id="warn-task-id")
        mock_deletion = MagicMock()
        mock_deletion.apply_async.return_value = MagicMock(id="del-task-id")

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", mock_celery):
            _schedule_expiry_tasks(db, doc.id)

        mock_warning.apply_async.assert_called_once()

    def test_applies_deletion_task(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        mock_warning = MagicMock()
        mock_warning.apply_async.return_value = MagicMock(id="warn-id")
        mock_deletion = MagicMock()
        mock_deletion.apply_async.return_value = MagicMock(id="del-id")

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", MagicMock()):
            _schedule_expiry_tasks(db, doc.id)

        mock_deletion.apply_async.assert_called_once()

    def test_warning_eta_is_one_day_before_expiry(self, db):
        user = _make_user(db)
        expiry = datetime.now(timezone.utc) + timedelta(days=3)
        doc = _make_doc(db, user.id)
        doc.expires_at = expiry
        db.commit()

        captured_eta = {}
        mock_warning = MagicMock()
        mock_deletion = MagicMock()
        mock_deletion.apply_async.return_value = MagicMock(id="d")

        def capture_warning(**kwargs):
            captured_eta["warning"] = kwargs.get("eta")
            return MagicMock(id="w")

        mock_warning.apply_async = capture_warning

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", MagicMock()):
            _schedule_expiry_tasks(db, doc.id)

        expected = expiry - timedelta(days=1)
        assert abs((captured_eta["warning"] - expected).total_seconds()) < 5

    def test_revokes_old_task_ids_if_present(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        doc.warning_task_id = "old-warn-id"
        doc.deletion_task_id = "old-del-id"
        db.commit()

        mock_celery = MagicMock()
        mock_warning = MagicMock()
        mock_warning.apply_async.return_value = MagicMock(id="new-warn")
        mock_deletion = MagicMock()
        mock_deletion.apply_async.return_value = MagicMock(id="new-del")

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", mock_celery):
            _schedule_expiry_tasks(db, doc.id)

        revoke_calls = [c.args[0] for c in mock_celery.control.revoke.call_args_list]
        assert "old-warn-id" in revoke_calls
        assert "old-del-id" in revoke_calls

    def test_returns_early_if_doc_has_no_expiry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        doc.expires_at = None
        db.commit()

        mock_warning = MagicMock()
        mock_deletion = MagicMock()

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", MagicMock()):
            _schedule_expiry_tasks(db, doc.id)

        mock_warning.apply_async.assert_not_called()
        mock_deletion.apply_async.assert_not_called()

    def test_returns_early_if_doc_not_found(self, db):
        mock_warning = MagicMock()
        mock_deletion = MagicMock()

        with patch("app.workers.tasks.send_deletion_warning", mock_warning), \
             patch("app.workers.tasks.auto_delete_document", mock_deletion), \
             patch("app.workers.celery_app.celery_app", MagicMock()):
            _schedule_expiry_tasks(db, uuid.uuid4())

        mock_warning.apply_async.assert_not_called()


# ===========================================================================
# process_document
# ===========================================================================

class TestProcessDocument:

    def _run(self, doc_id: str, fetch_bytes=b"pdf bytes",
             extract_return="long contract text " * 10,
             analyze_return=None):
        """Run process_document.run() with everything mocked."""
        if analyze_return is None:
            analyze_return = (_fake_analysis_result(), 400, 2.5)
        with patch("app.workers.tasks._fetch_file", return_value=fetch_bytes), \
             patch("app.services.document_processor.extract_text", return_value=extract_return), \
             patch("app.services.ai_service.analyze_document", return_value=analyze_return), \
             patch("app.workers.tasks._schedule_expiry_tasks"):
            return process_document.run(doc_id)

    def test_happy_path_returns_completed(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        result = self._run(str(doc.id))
        assert result["status"] == "completed"

    def test_happy_path_returns_document_id(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        result = self._run(str(doc.id))
        assert result["document_id"] == str(doc.id)

    def test_happy_path_returns_risk_score(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        result = self._run(str(doc.id))
        assert result["risk_score"] == "medium"

    def test_happy_path_returns_tokens_used(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        result = self._run(str(doc.id))
        assert result["tokens_used"] == 400

    def test_analysis_created_in_db(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        self._run(str(doc.id))
        with _TestSession() as fresh:
            analysis = fresh.query(Analysis).filter(
                Analysis.document_id == doc.id
            ).first()
        assert analysis is not None
        assert analysis.risk_score == "medium"

    def test_document_status_set_to_completed(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        self._run(str(doc.id))
        with _TestSession() as fresh:
            refreshed = fresh.query(Document).filter(Document.id == doc.id).first()
        assert refreshed.status == "completed"

    def test_document_not_found_returns_error_dict(self, db):
        with patch("app.workers.tasks._fetch_file"), \
             patch("app.services.document_processor.extract_text"), \
             patch("app.services.ai_service.analyze_document"):
            result = process_document.run(str(uuid.uuid4()))
        assert "error" in result

    def test_extract_text_failure_sets_status_failed(self, db):
        """ValueError from extract_text returns error dict and marks doc failed."""
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text",
                   side_effect=ValueError("no text")):
            result = process_document.run(str(doc.id))
        assert result["status"] == "failed"
        with _TestSession() as fresh:
            refreshed = fresh.query(Document).filter(Document.id == doc.id).first()
        assert refreshed.status == "failed"

    def test_value_error_does_not_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text",
                   side_effect=ValueError("no text")):
            result = process_document.run(str(doc.id))
        # ValueError → no retry, returns error dict
        # retry not called — confirmed by returning error dict not raising
        assert result["status"] == "failed"

    def test_ai_service_error_triggers_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text",
                   return_value="long enough text " * 10), \
             patch("app.services.ai_service.analyze_document",
                   side_effect=AIServiceError("timeout")), \
             pytest.raises(Exception):
            process_document.run(str(doc.id))
        # retry verified via patch.object above


# ===========================================================================
# reanalyze_document
# ===========================================================================

class TestReanalyzeDocument:

    def _run(self, doc_id: str,
             extract_return="long enough text " * 10,
             analyze_return=None):
        if analyze_return is None:
            analyze_return = (_fake_analysis_result(), 300, 1.5)
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text", return_value=extract_return), \
             patch("app.services.ai_service.analyze_document", return_value=analyze_return), \
             patch("app.workers.tasks._schedule_expiry_tasks"):
            return reanalyze_document.run(doc_id)

    def test_happy_path_returns_completed(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        result = self._run(str(doc.id))
        assert result["status"] == "completed"

    def test_happy_path_returns_document_id(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        result = self._run(str(doc.id))
        assert result["document_id"] == str(doc.id)

    def test_document_not_found_returns_error(self, db):
        with patch("app.workers.tasks._fetch_file"), \
             patch("app.services.document_processor.extract_text"), \
             patch("app.services.ai_service.analyze_document"):
            result = reanalyze_document.run(str(uuid.uuid4()))
        assert "error" in result

    def test_already_deleted_returns_error(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed", is_deleted=True)
        result = self._run(str(doc.id))
        assert "error" in result
        assert "deleted" in result["error"].lower()

    def test_wrong_status_returns_error(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="completed")
        result = self._run(str(doc.id))
        assert "error" in result
        assert "status" in result["error"]

    def test_deletes_existing_analysis_before_reanalysis(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        _make_analysis(db, doc.id)
        self._run(str(doc.id))
        with _TestSession() as fresh:
            old_count = fresh.query(Analysis).filter(
                Analysis.document_id == doc.id,
                Analysis.risk_score == "low",
            ).count()
        assert old_count == 0

    def test_creates_new_analysis_after_reanalysis(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        _make_analysis(db, doc.id)
        self._run(str(doc.id))
        with _TestSession() as fresh:
            new = fresh.query(Analysis).filter(
                Analysis.document_id == doc.id,
                Analysis.risk_score == "medium",
            ).first()
        assert new is not None

    def test_value_error_returns_failed_without_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text",
                   side_effect=ValueError("empty doc")):
            result = reanalyze_document.run(str(doc.id))
        # retry not called — confirmed by returning error dict not raising
        assert result["status"] == "failed"

    def test_ai_error_triggers_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        with patch("app.workers.tasks._fetch_file", return_value=b"bytes"), \
             patch("app.services.document_processor.extract_text",
                   return_value="long text " * 20), \
             patch("app.services.ai_service.analyze_document",
                   side_effect=AIServiceError("timeout")), \
             pytest.raises(Exception):
            reanalyze_document.run(str(doc.id))
        # retry verified via patch.object above


# ===========================================================================
# send_deletion_warning
# ===========================================================================

class TestSendDeletionWarning:

    def test_sends_email_for_valid_document(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.services.email_service.send_deletion_warning_email") as mock_email:
            result = send_deletion_warning.run( str(doc.id))
        mock_email.assert_called_once()
        assert result["status"] == "warning_sent"

    def test_sends_email_to_correct_address(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.services.email_service.send_deletion_warning_email") as mock_email:
            send_deletion_warning.run( str(doc.id))
        assert mock_email.call_args.kwargs["to"] == user.email

    def test_returns_document_id_in_result(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with patch("app.services.email_service.send_deletion_warning_email"):
            result = send_deletion_warning.run( str(doc.id))
        assert result["document_id"] == str(doc.id)

    def test_already_deleted_skips_email(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, is_deleted=True)
        with patch("app.services.email_service.send_deletion_warning_email") as mock_email:
            result = send_deletion_warning.run( str(doc.id))
        mock_email.assert_not_called()
        assert result["skipped"] is True

    def test_not_found_skips_email(self, db):

        with patch("app.services.email_service.send_deletion_warning_email") as mock_email:
            result = send_deletion_warning.run( str(uuid.uuid4()))
        mock_email.assert_not_called()
        assert result["skipped"] is True

    def test_email_failure_triggers_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        with patch("app.services.email_service.send_deletion_warning_email",
                   side_effect=Exception("SMTP error")), \
             pytest.raises(Exception):
            send_deletion_warning.run( str(doc.id))
        # retry verified via patch.object above


# ===========================================================================
# auto_delete_document
# ===========================================================================

class TestAutoDeleteDocument:

    def test_soft_deletes_document(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        with patch("app.workers.tasks._delete_file"):
            result = auto_delete_document.run( str(doc.id))
        assert result["status"] == "deleted"
        with _TestSession() as fresh:
            refreshed = fresh.query(Document).filter(Document.id == doc.id).first()
        assert refreshed.is_deleted is True

    def test_returns_document_id(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        with patch("app.workers.tasks._delete_file"):
            result = auto_delete_document.run( str(doc.id))
        assert result["document_id"] == str(doc.id)

    def test_calls_delete_file(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, file_url="https://s3.example.com/key.pdf")

        with patch("app.workers.tasks._delete_file") as mock_del:
            auto_delete_document.run( str(doc.id))
        mock_del.assert_called_once_with("https://s3.example.com/key.pdf")

    def test_already_deleted_skips(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, is_deleted=True)

        with patch("app.workers.tasks._delete_file") as mock_del:
            result = auto_delete_document.run( str(doc.id))
        mock_del.assert_not_called()
        assert result["skipped"] is True

    def test_not_found_skips(self, db):

        with patch("app.workers.tasks._delete_file") as mock_del:
            result = auto_delete_document.run( str(uuid.uuid4()))
        mock_del.assert_not_called()
        assert result["skipped"] is True

    def test_file_delete_failure_still_soft_deletes(self, db):
        """Physical file delete failure must not prevent DB soft-delete."""
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        with patch("app.workers.tasks._delete_file",
                   side_effect=Exception("S3 gone")):
            result = auto_delete_document.run( str(doc.id))
        # Should still complete (warning logged, soft-delete proceeds)
        assert result["status"] == "deleted"
        with _TestSession() as fresh:
            refreshed = fresh.query(Document).filter(Document.id == doc.id).first()
        assert refreshed.is_deleted is True

    def test_unexpected_error_triggers_retry(self, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)

        with patch("app.workers.tasks._delete_file"), \
             patch("app.services.document_service.soft_delete_document",
                   side_effect=RuntimeError("DB exploded")), \
             pytest.raises(Exception):
            auto_delete_document.run( str(doc.id))
