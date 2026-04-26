"""
Pytest test suite for app/api/routes/documents.py

Covers every endpoint:
  POST /documents/upload         — happy path (202), unverified user (403),
                                   no upload credits (403), unsupported file type (415),
                                   file too large (413), response shape
  GET  /documents                — list owned docs, pagination params,
                                   unauthenticated (401)
  GET  /documents/{id}           — owner access (200), wrong user (403),
                                   not found (404), unauthenticated (401)
  DELETE /documents/{id}         — owner can delete (200), wrong user (403),
                                   already deleted is idempotent, unauthenticated (401)
  POST /documents/{id}/reanalyze — failed doc starts reanalysis (202),
                                   non-failed doc raises 403, deleted raises 403
  POST /documents/{id}/keep      — extends expiry (200), deleted raises 403,
                                   not found raises 404

All Celery/broker calls are mocked — no Redis needed.
File storage is local (aws_access_key_id = "test-key-id" triggers local path).
Settings stubbed via tests/conftest.py.
"""

import io
import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa

# ── SQLite type stubs ─────────────────────────────────────────────────────────

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

# ── DB + App setup ─────────────────────────────────────────────────────────────

from unittest.mock import patch as _patch

from app.db.base import Base
from app.models import user as _u, document as _d, analysis as _a, payment as _p
import sys, os as _os
_sys_tests_dir = _os.path.dirname(_os.path.abspath(__file__))
if _sys_tests_dir not in sys.path:
    sys.path.insert(0, _sys_tests_dir)
from db_fixtures import SHARED_TEST_ENGINE as _engine, SHARED_TEST_SESSION as _TestSession, shared_override_get_db as _override_get_db_fn
from app.models.user import User, FREE_UPLOAD_LIMIT
from app.models.document import Document
from app.core.security import hash_password, create_access_token


with _patch("sqlalchemy.create_engine", return_value=_engine):
    import app.db.session as _sess
_sess.SessionLocal = _TestSession

with _patch("app.services.disposable_email_service.preload_blocklist"):
    from app.main import app

from app.db.session import get_db
app.dependency_overrides[get_db] = _override_get_db_fn

from fastapi.testclient import TestClient

# ── Celery / broker always mocked ────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_celery(monkeypatch):
    """Prevent any real Celery/broker calls in every test."""
    mock_task = MagicMock()
    mock_task.delay = MagicMock(return_value=MagicMock(id="fake-task-id"))
    # Patch tasks at source
    monkeypatch.setattr("app.workers.tasks.process_document", mock_task)
    monkeypatch.setattr("app.workers.tasks.auto_delete_document", mock_task)
    monkeypatch.setattr("app.workers.tasks.reanalyze_document", mock_task)
    # Patch broker health to always be healthy → Celery path taken, .delay() is safe mock
    monkeypatch.setattr("app.workers.broker_health.wait_for_broker", lambda **kw: True)
    # Also patch _run_processing_in_background to avoid direct task execution
    monkeypatch.setattr("app.api.routes.documents._run_processing_in_background", lambda doc_id: None)
    # Patch _store_file to avoid real S3 calls (test-key-id is not in dummy list)
    monkeypatch.setattr("app.api.routes.documents._store_file",
                        lambda contents, ct, uid: f"local://{uid}/test-file.pdf")
    return mock_task


@pytest.fixture(autouse=True)
def clean_db():
    yield
    with _TestSession() as db:
        db.query(_a.Analysis).delete()
        db.query(_d.Document).delete()
        db.query(_u.User).delete()
        db.commit()


@pytest.fixture()
def db():
    with _TestSession() as session:
        yield session


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(db, email="user@example.com", password="Password1!",
               is_verified=True, is_active=True,
               uploads_used=0, upload_credits=0, role="user") -> User:
    u = User(
        email=email,
        password_hash=hash_password(password),
        role=role,
        is_verified=is_verified,
        is_active=is_active,
        uploads_used=uploads_used,
        upload_credits=upload_credits,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_doc(db, user_id, filename="lease.pdf", status="completed",
              is_deleted=False) -> Document:
    doc = Document(
        user_id=user_id,
        original_filename=filename,
        file_url=f"local://{user_id}/{filename}",
        file_size_bytes=12345,
        content_type="application/pdf",
        status=status,
        is_deleted=is_deleted,
        expires_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db.add(doc); db.commit(); db.refresh(doc)
    return doc


def _auth(user: User) -> dict:
    token = create_access_token(str(user.id), user.role)
    return {"Authorization": f"Bearer {token}"}


def _pdf_upload(filename="contract.pdf", size=1024):
    return {"file": (filename, io.BytesIO(b"A" * size), "application/pdf")}


def _docx_upload(filename="contract.docx", size=1024):
    return {
        "file": (filename, io.BytesIO(b"A" * size),
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    }


# ===========================================================================
# POST /documents/upload
# ===========================================================================

class TestUploadDocument:

    def test_returns_202(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert resp.status_code == 202

    def test_response_has_id(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert "id" in resp.json()

    def test_response_has_status(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert resp.json()["status"] == "uploaded"

    def test_response_has_message(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert "message" in resp.json()

    def test_response_has_original_filename(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload",
                               files={"file": ("my_lease.pdf", io.BytesIO(b"A" * 100), "application/pdf")},
                               headers=_auth(user))
        assert resp.json()["original_filename"] == "my_lease.pdf"

    def test_docx_upload_also_accepted(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_docx_upload(), headers=_auth(user))
        assert resp.status_code == 202

    def test_unverified_user_gets_403(self, client, db):
        user = _make_user(db, is_verified=False)
        resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert resp.status_code == 403

    def test_user_at_upload_limit_without_credits_gets_403(self, client, db):
        user = _make_user(db, uploads_used=FREE_UPLOAD_LIMIT, upload_credits=0)
        resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert resp.status_code == 403

    def test_user_at_limit_with_credits_can_upload(self, client, db):
        user = _make_user(db, uploads_used=FREE_UPLOAD_LIMIT, upload_credits=3)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        assert resp.status_code == 202

    def test_unsupported_file_type_returns_415(self, client, db):
        user = _make_user(db)
        resp = client.post("/documents/upload",
                           files={"file": ("photo.jpg", io.BytesIO(b"jpeg"), "image/jpeg")},
                           headers=_auth(user))
        assert resp.status_code == 415

    def test_file_too_large_returns_413(self, client, db):
        user = _make_user(db)
        big = io.BytesIO(b"A" * (21 * 1024 * 1024))  # 21 MB > 20 MB limit
        resp = client.post("/documents/upload",
                           files={"file": ("big.pdf", big, "application/pdf")},
                           headers=_auth(user))
        assert resp.status_code == 413

    def test_unauthenticated_returns_401(self, client):
        resp = client.post("/documents/upload", files=_pdf_upload())
        assert resp.status_code == 401

    def test_increments_uploads_used(self, client, db):
        user = _make_user(db, uploads_used=0)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        db.refresh(user)
        assert user.uploads_used == 1

    def test_credit_decremented_when_using_paid_credit(self, client, db):
        user = _make_user(db, uploads_used=FREE_UPLOAD_LIMIT, upload_credits=2)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        db.refresh(user)
        assert user.upload_credits == 1

    def test_document_created_in_db(self, client, db):
        user = _make_user(db)
        with _patch("app.api.routes.documents._run_processing_in_background"):
            resp = client.post("/documents/upload", files=_pdf_upload(), headers=_auth(user))
        doc_id = resp.json()["id"]
        doc = db.query(Document).filter(Document.id == uuid.UUID(doc_id)).first()
        assert doc is not None


# ===========================================================================
# GET /documents
# ===========================================================================

class TestListDocuments:

    def test_returns_200(self, client, db):
        user = _make_user(db)
        resp = client.get("/documents", headers=_auth(user))
        assert resp.status_code == 200

    def test_empty_list_when_no_docs(self, client, db):
        user = _make_user(db)
        resp = client.get("/documents", headers=_auth(user))
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    def test_returns_user_documents(self, client, db):
        user = _make_user(db)
        _make_doc(db, user.id, "doc1.pdf")
        _make_doc(db, user.id, "doc2.pdf")
        resp = client.get("/documents", headers=_auth(user))
        assert resp.json()["total"] == 2

    def test_does_not_return_other_users_docs(self, client, db):
        user = _make_user(db, email="mine@example.com")
        other = _make_user(db, email="other@example.com")
        _make_doc(db, other.id, "other.pdf")
        resp = client.get("/documents", headers=_auth(user))
        assert resp.json()["total"] == 0

    def test_pagination_page_size(self, client, db):
        user = _make_user(db)
        for i in range(5):
            _make_doc(db, user.id, f"doc{i}.pdf")
        resp = client.get("/documents?page=1&page_size=2", headers=_auth(user))
        assert len(resp.json()["items"]) == 2

    def test_pagination_total_reflects_all(self, client, db):
        user = _make_user(db)
        for i in range(5):
            _make_doc(db, user.id, f"doc{i}.pdf")
        resp = client.get("/documents?page=1&page_size=2", headers=_auth(user))
        assert resp.json()["total"] == 5

    def test_response_contains_page_and_page_size(self, client, db):
        user = _make_user(db)
        resp = client.get("/documents?page=2&page_size=10", headers=_auth(user))
        assert resp.json()["page"] == 2
        assert resp.json()["page_size"] == 10

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/documents")
        assert resp.status_code == 401


# ===========================================================================
# GET /documents/{id}
# ===========================================================================

class TestGetDocument:

    def test_owner_gets_200(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.get(f"/documents/{doc.id}", headers=_auth(user))
        assert resp.status_code == 200

    def test_response_has_correct_id(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.get(f"/documents/{doc.id}", headers=_auth(user))
        assert resp.json()["id"] == str(doc.id)

    def test_admin_can_access_any_document(self, client, db):
        owner = _make_user(db, email="owner@example.com")
        admin = _make_user(db, email="admin@example.com", role="admin")
        doc = _make_doc(db, owner.id)
        resp = client.get(f"/documents/{doc.id}", headers=_auth(admin))
        assert resp.status_code == 200

    def test_wrong_user_gets_403(self, client, db):
        owner = _make_user(db, email="owner@example.com")
        other = _make_user(db, email="other@example.com")
        doc = _make_doc(db, owner.id)
        resp = client.get(f"/documents/{doc.id}", headers=_auth(other))
        assert resp.status_code == 403

    def test_not_found_returns_404(self, client, db):
        user = _make_user(db)
        resp = client.get(f"/documents/{uuid.uuid4()}", headers=_auth(user))
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.get(f"/documents/{doc.id}")
        assert resp.status_code == 401


# ===========================================================================
# DELETE /documents/{id}
# ===========================================================================

class TestDeleteDocument:

    def test_owner_can_delete(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.delete(f"/documents/{doc.id}", headers=_auth(user))
        assert resp.status_code == 200

    def test_delete_response_has_message(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.delete(f"/documents/{doc.id}", headers=_auth(user))
        assert "message" in resp.json()

    def test_doc_is_soft_deleted_in_db(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        client.delete(f"/documents/{doc.id}", headers=_auth(user))
        db.refresh(doc)
        assert doc.is_deleted is True

    def test_wrong_user_gets_403(self, client, db):
        owner = _make_user(db, email="owner@example.com")
        other = _make_user(db, email="other@example.com")
        doc = _make_doc(db, owner.id)
        resp = client.delete(f"/documents/{doc.id}", headers=_auth(other))
        assert resp.status_code == 403

    def test_already_deleted_returns_200_with_message(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, is_deleted=True)
        resp = client.delete(f"/documents/{doc.id}", headers=_auth(user))
        assert resp.status_code == 200
        assert "already deleted" in resp.json()["message"]

    def test_not_found_returns_404(self, client, db):
        user = _make_user(db)
        resp = client.delete(f"/documents/{uuid.uuid4()}", headers=_auth(user))
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.delete(f"/documents/{doc.id}")
        assert resp.status_code == 401


# ===========================================================================
# POST /documents/{id}/reanalyze
# ===========================================================================

class TestReanalyzeDocument:

    def test_failed_doc_returns_202(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(user))
        assert resp.status_code == 202

    def test_failed_doc_response_has_message(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(user))
        assert "message" in resp.json()

    def test_non_failed_doc_returns_403(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="completed")
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(user))
        assert resp.status_code == 403

    def test_uploaded_status_returns_403(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="uploaded")
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(user))
        assert resp.status_code == 403

    def test_deleted_doc_returns_403(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed", is_deleted=True)
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(user))
        assert resp.status_code == 403

    def test_wrong_user_gets_403(self, client, db):
        owner = _make_user(db, email="owner@example.com")
        other = _make_user(db, email="other@example.com")
        doc = _make_doc(db, owner.id, status="failed")
        resp = client.post(f"/documents/{doc.id}/reanalyze", headers=_auth(other))
        assert resp.status_code == 403

    def test_not_found_returns_404(self, client, db):
        user = _make_user(db)
        resp = client.post(f"/documents/{uuid.uuid4()}/reanalyze", headers=_auth(user))
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, status="failed")
        resp = client.post(f"/documents/{doc.id}/reanalyze")
        assert resp.status_code == 401


# ===========================================================================
# POST /documents/{id}/keep
# ===========================================================================

class TestKeepDocument:

    def test_returns_200(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with _patch("app.workers.tasks._schedule_expiry_tasks"):
            resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(user))
        assert resp.status_code == 200

    def test_response_has_expires_at(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with _patch("app.workers.tasks._schedule_expiry_tasks"):
            resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(user))
        assert "expires_at" in resp.json()

    def test_expires_at_is_pushed_forward(self, client, db):
        user = _make_user(db)
        old_expiry = datetime.now(timezone.utc) + timedelta(days=1)
        doc = _make_doc(db, user.id)
        doc.expires_at = old_expiry
        db.commit()
        with _patch("app.workers.tasks._schedule_expiry_tasks"):
            resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(user))
        db.refresh(doc)
        new_expiry = doc.expires_at
        if new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)
        assert new_expiry > old_expiry

    def test_response_has_message(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        with _patch("app.workers.tasks._schedule_expiry_tasks"):
            resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(user))
        assert "message" in resp.json()

    def test_deleted_doc_returns_403(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id, is_deleted=True)
        resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(user))
        assert resp.status_code == 403

    def test_wrong_user_returns_403(self, client, db):
        owner = _make_user(db, email="owner@example.com")
        other = _make_user(db, email="other@example.com")
        doc = _make_doc(db, owner.id)
        resp = client.post(f"/documents/{doc.id}/keep", headers=_auth(other))
        assert resp.status_code == 403

    def test_not_found_returns_404(self, client, db):
        user = _make_user(db)
        resp = client.post(f"/documents/{uuid.uuid4()}/keep", headers=_auth(user))
        assert resp.status_code == 404

    def test_unauthenticated_returns_401(self, client, db):
        user = _make_user(db)
        doc = _make_doc(db, user.id)
        resp = client.post(f"/documents/{doc.id}/keep")
        assert resp.status_code == 401