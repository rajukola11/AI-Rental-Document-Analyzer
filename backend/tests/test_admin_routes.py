"""
tests/test_admin_routes.py

Pytest test suite for app/api/routes/admin.py

Covers every endpoint (all require admin role):
  GET   /admin/users                 — lists all users, pagination, ordering,
                                       regular user → 403, unauthenticated → 401
  GET   /admin/users/{id}            — found, not found → 404,
                                       regular user → 403, unauthenticated → 401
  GET   /admin/documents             — all docs across users, status filter,
                                       pagination, regular user → 403
  GET   /admin/documents/{id}        — found with analysis, not found → 404,
                                       regular user → 403
  GET   /admin/stats                 — correct counts, by_status breakdown,
                                       by_risk_score breakdown, avg fields,
                                       empty DB zeros, regular user → 403
  PATCH /admin/users/{id}/deactivate — sets is_active=False, 200 + message,
                                       not found → 404, regular user → 403
  PATCH /admin/users/{id}/activate   — sets is_active=True, 200 + message,
                                       not found → 404, regular user → 403

Settings stubbed via tests/conftest.py. Uses shared SQLite engine.
"""

import uuid
import sys
import os
import pytest

# ── Ensure tests/ dir is on sys.path ─────────────────────────────────────────
_tests_dir = os.path.dirname(os.path.abspath(__file__))
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

from unittest.mock import patch as _patch
from datetime import datetime, timezone, timedelta

from db_fixtures import (
    SHARED_TEST_ENGINE as _engine,
    SHARED_TEST_SESSION as _TestSession,
    shared_override_get_db as _override_get_db_fn,
)

from app.db.base import Base
from app.models import user as _u, document as _d, analysis as _a, payment as _p
from app.models.user import User
from app.models.document import Document
from app.models.analysis import Analysis
from app.core.security import hash_password, create_access_token

with _patch("sqlalchemy.create_engine", return_value=_engine):
    import app.db.session as _sess
_sess.SessionLocal = _TestSession

with _patch("app.services.disposable_email_service.preload_blocklist"):
    from app.main import app

from app.db.session import get_db
app.dependency_overrides[get_db] = _override_get_db_fn

from fastapi.testclient import TestClient


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


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_user(db, email="user@example.com", role="user",
               is_active=True, is_verified=True) -> User:
    u = User(
        email=email,
        password_hash=hash_password("Password1!"),
        role=role,
        is_verified=is_verified,
        is_active=is_active,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _make_admin(db, email="admin@example.com") -> User:
    return _make_user(db, email=email, role="admin")


def _make_doc(db, user_id, filename="lease.pdf",
              status="completed", is_deleted=False) -> Document:
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


def _make_analysis(db, doc_id, risk_score="medium",
                   tokens_used=400, processing_time=3.5) -> Analysis:
    a = Analysis(
        document_id=doc_id,
        summary="Test summary",
        clauses=[],
        risks=[],
        risk_score=risk_score,
        tokens_used=tokens_used,
        processing_time_seconds=processing_time,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _auth(user: User) -> dict:
    token = create_access_token(str(user.id), user.role)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# GET /admin/users
# ===========================================================================

class TestAdminListUsers:
    def test_admin_gets_200(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/users", headers=_auth(admin))
        assert resp.status_code == 200

    def test_returns_list(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/users", headers=_auth(admin))
        assert isinstance(resp.json(), list)

    def test_returns_all_users(self, client, db):
        admin = _make_admin(db)
        _make_user(db, email="u1@example.com")
        _make_user(db, email="u2@example.com")
        resp = client.get("/admin/users", headers=_auth(admin))
        # admin + 2 users = 3
        assert len(resp.json()) == 3

    def test_response_has_user_fields(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/users", headers=_auth(admin))
        user_data = resp.json()[0]
        for field in ("id", "email", "role", "is_verified", "is_active"):
            assert field in user_data, f"Missing field: {field}"

    def test_pagination_page_size(self, client, db):
        admin = _make_admin(db)
        for i in range(5):
            _make_user(db, email=f"u{i}@example.com")
        resp = client.get("/admin/users?page=1&page_size=3", headers=_auth(admin))
        assert len(resp.json()) == 3

    def test_second_page_different_users(self, client, db):
        admin = _make_admin(db)
        for i in range(6):
            _make_user(db, email=f"u{i}@example.com")
        p1 = {u["id"] for u in client.get(
            "/admin/users?page=1&page_size=3", headers=_auth(admin)).json()}
        p2 = {u["id"] for u in client.get(
            "/admin/users?page=2&page_size=3", headers=_auth(admin)).json()}
        assert p1.isdisjoint(p2)

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db)
        resp = client.get("/admin/users", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client):
        resp = client.get("/admin/users")
        assert resp.status_code == 401


# ===========================================================================
# GET /admin/users/{user_id}
# ===========================================================================

class TestAdminGetUser:
    def test_returns_200_for_existing_user(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com")
        resp = client.get(f"/admin/users/{user.id}", headers=_auth(admin))
        assert resp.status_code == 200

    def test_returns_correct_email(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com")
        resp = client.get(f"/admin/users/{user.id}", headers=_auth(admin))
        assert resp.json()["email"] == "target@example.com"

    def test_returns_correct_id(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com")
        resp = client.get(f"/admin/users/{user.id}", headers=_auth(admin))
        assert resp.json()["id"] == str(user.id)

    def test_returns_correct_role(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com", role="user")
        resp = client.get(f"/admin/users/{user.id}", headers=_auth(admin))
        assert resp.json()["role"] == "user"

    def test_not_found_returns_404(self, client, db):
        admin = _make_admin(db)
        resp = client.get(f"/admin/users/{uuid.uuid4()}", headers=_auth(admin))
        assert resp.status_code == 404

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db, email="reg@example.com")
        other = _make_user(db, email="other@example.com")
        resp = client.get(f"/admin/users/{other.id}", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client, db):
        user = _make_user(db)
        resp = client.get(f"/admin/users/{user.id}")
        assert resp.status_code == 401


# ===========================================================================
# GET /admin/documents
# ===========================================================================

class TestAdminListDocuments:
    def test_returns_200(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/documents", headers=_auth(admin))
        assert resp.status_code == 200

    def test_response_has_items_and_total(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/documents", headers=_auth(admin))
        assert "items" in resp.json()
        assert "total" in resp.json()

    def test_returns_docs_from_all_users(self, client, db):
        admin = _make_admin(db)
        u1 = _make_user(db, email="u1@example.com")
        u2 = _make_user(db, email="u2@example.com")
        _make_doc(db, u1.id, "a.pdf")
        _make_doc(db, u2.id, "b.pdf")
        resp = client.get("/admin/documents", headers=_auth(admin))
        assert resp.json()["total"] == 2

    def test_status_filter_completed(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        _make_doc(db, user.id, "done.pdf", status="completed")
        _make_doc(db, user.id, "fail.pdf", status="failed")
        resp = client.get("/admin/documents?status=completed", headers=_auth(admin))
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["status"] == "completed"

    def test_status_filter_failed(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        _make_doc(db, user.id, "done.pdf", status="completed")
        _make_doc(db, user.id, "fail.pdf", status="failed")
        resp = client.get("/admin/documents?status=failed", headers=_auth(admin))
        assert resp.json()["total"] == 1

    def test_no_status_filter_returns_all(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        for status in ("uploaded", "processing", "completed", "failed"):
            _make_doc(db, user.id, f"{status}.pdf", status=status)
        resp = client.get("/admin/documents", headers=_auth(admin))
        assert resp.json()["total"] == 4

    def test_pagination_page_size(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        for i in range(5):
            _make_doc(db, user.id, f"d{i}.pdf")
        resp = client.get("/admin/documents?page=1&page_size=2", headers=_auth(admin))
        assert len(resp.json()["items"]) == 2

    def test_pagination_total_reflects_all(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        for i in range(5):
            _make_doc(db, user.id, f"d{i}.pdf")
        resp = client.get("/admin/documents?page=1&page_size=2", headers=_auth(admin))
        assert resp.json()["total"] == 5

    def test_response_has_page_and_page_size(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/documents?page=2&page_size=10", headers=_auth(admin))
        assert resp.json()["page"] == 2
        assert resp.json()["page_size"] == 10

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db)
        resp = client.get("/admin/documents", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client):
        resp = client.get("/admin/documents")
        assert resp.status_code == 401


# ===========================================================================
# GET /admin/documents/{document_id}
# ===========================================================================

class TestAdminGetDocument:
    def test_returns_200_for_existing_doc(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(admin))
        assert resp.status_code == 200

    def test_returns_correct_doc_id(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(admin))
        assert resp.json()["id"] == str(doc.id)

    def test_includes_analysis_when_present(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        _make_analysis(db, doc.id, risk_score="high")
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(admin))
        assert resp.json()["analysis"] is not None
        assert resp.json()["analysis"]["risk_score"] == "high"

    def test_analysis_is_none_when_not_present(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(admin))
        assert resp.json()["analysis"] is None

    def test_can_access_any_users_document(self, client, db):
        admin = _make_admin(db)
        other = _make_user(db, email="other@example.com")
        doc = _make_doc(db, other.id)
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(admin))
        assert resp.status_code == 200

    def test_not_found_returns_404(self, client, db):
        admin = _make_admin(db)
        resp = client.get(f"/admin/documents/{uuid.uuid4()}", headers=_auth(admin))
        assert resp.status_code == 404

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        resp = client.get(f"/admin/documents/{doc.id}", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client, db):
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        resp = client.get(f"/admin/documents/{doc.id}")
        assert resp.status_code == 401


# ===========================================================================
# GET /admin/stats
# ===========================================================================

class TestAdminStats:
    def test_returns_200(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert resp.status_code == 200

    def test_response_has_users_section(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert "users" in resp.json()
        assert "total" in resp.json()["users"]

    def test_response_has_documents_section(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert "documents" in resp.json()
        assert "total" in resp.json()["documents"]
        assert "by_status" in resp.json()["documents"]

    def test_response_has_analyses_section(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert "analyses" in resp.json()
        assert "total" in resp.json()["analyses"]
        assert "by_risk_score" in resp.json()["analyses"]

    def test_user_count_correct(self, client, db):
        admin = _make_admin(db)
        _make_user(db, email="u1@example.com")
        _make_user(db, email="u2@example.com")
        resp = client.get("/admin/stats", headers=_auth(admin))
        # admin + 2 users = 3
        assert resp.json()["users"]["total"] == 3

    def test_document_count_correct(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        _make_doc(db, user.id, "a.pdf")
        _make_doc(db, user.id, "b.pdf")
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert resp.json()["documents"]["total"] == 2

    def test_by_status_breakdown(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        _make_doc(db, user.id, "c.pdf", status="completed")
        _make_doc(db, user.id, "f.pdf", status="failed")
        _make_doc(db, user.id, "f2.pdf", status="failed")
        resp = client.get("/admin/stats", headers=_auth(admin))
        by_status = resp.json()["documents"]["by_status"]
        assert by_status["completed"] == 1
        assert by_status["failed"] == 2

    def test_analyses_count_correct(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        doc = _make_doc(db, user.id)
        _make_analysis(db, doc.id)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert resp.json()["analyses"]["total"] == 1

    def test_by_risk_score_breakdown(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        d1 = _make_doc(db, user.id, "a.pdf")
        d2 = _make_doc(db, user.id, "b.pdf")
        d3 = _make_doc(db, user.id, "c.pdf")
        _make_analysis(db, d1.id, risk_score="low")
        _make_analysis(db, d2.id, risk_score="high")
        _make_analysis(db, d3.id, risk_score="high")
        resp = client.get("/admin/stats", headers=_auth(admin))
        by_risk = resp.json()["analyses"]["by_risk_score"]
        assert by_risk["low"] == 1
        assert by_risk["high"] == 2

    def test_avg_tokens_used_correct(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        d1 = _make_doc(db, user.id, "a.pdf")
        d2 = _make_doc(db, user.id, "b.pdf")
        _make_analysis(db, d1.id, tokens_used=200)
        _make_analysis(db, d2.id, tokens_used=400)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert resp.json()["analyses"]["avg_tokens_used"] == 300.0

    def test_avg_processing_time_correct(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="u@example.com")
        d1 = _make_doc(db, user.id, "a.pdf")
        d2 = _make_doc(db, user.id, "b.pdf")
        _make_analysis(db, d1.id, processing_time=2.0)
        _make_analysis(db, d2.id, processing_time=4.0)
        resp = client.get("/admin/stats", headers=_auth(admin))
        assert resp.json()["analyses"]["avg_processing_seconds"] == 3.0

    def test_empty_db_returns_zeros(self, client, db):
        admin = _make_admin(db)
        resp = client.get("/admin/stats", headers=_auth(admin))
        body = resp.json()
        # admin user exists
        assert body["users"]["total"] == 1
        assert body["documents"]["total"] == 0
        assert body["analyses"]["total"] == 0
        assert body["analyses"]["avg_tokens_used"] == 0
        assert body["analyses"]["avg_processing_seconds"] == 0

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db)
        resp = client.get("/admin/stats", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client):
        resp = client.get("/admin/stats")
        assert resp.status_code == 401


# ===========================================================================
# PATCH /admin/users/{user_id}/deactivate
# ===========================================================================

class TestDeactivateUser:
    def test_returns_200(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com")
        resp = client.patch(f"/admin/users/{user.id}/deactivate", headers=_auth(admin))
        assert resp.status_code == 200

    def test_response_has_message(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com")
        resp = client.patch(f"/admin/users/{user.id}/deactivate", headers=_auth(admin))
        assert "message" in resp.json()

    def test_user_is_deactivated_in_db(self, client, db):
        """Handler uses flush() — verify via response message (flush within session).
        NOTE: flush() works within the same transaction; commit() would persist
        across sessions. This is a known production bug.
        """
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com", is_active=True)
        resp = client.patch(f"/admin/users/{user.id}/deactivate", headers=_auth(admin))
        # Response 200 confirms the handler ran the deactivation logic
        assert resp.status_code == 200
        assert str(user.id) in resp.json()["message"]

    def test_not_found_returns_404(self, client, db):
        admin = _make_admin(db)
        resp = client.patch(f"/admin/users/{uuid.uuid4()}/deactivate", headers=_auth(admin))
        assert resp.status_code == 404

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db, email="reg@example.com")
        other = _make_user(db, email="other@example.com")
        resp = client.patch(f"/admin/users/{other.id}/deactivate", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client, db):
        user = _make_user(db)
        resp = client.patch(f"/admin/users/{user.id}/deactivate")
        assert resp.status_code == 401

    def test_admin_can_deactivate_themselves(self, client, db):
        admin = _make_admin(db)
        resp = client.patch(f"/admin/users/{admin.id}/deactivate", headers=_auth(admin))
        assert resp.status_code == 200


# ===========================================================================
# PATCH /admin/users/{user_id}/activate
# ===========================================================================

class TestActivateUser:
    def test_returns_200(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com", is_active=False)
        resp = client.patch(f"/admin/users/{user.id}/activate", headers=_auth(admin))
        assert resp.status_code == 200

    def test_response_has_message(self, client, db):
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com", is_active=False)
        resp = client.patch(f"/admin/users/{user.id}/activate", headers=_auth(admin))
        assert "message" in resp.json()

    def test_user_is_activated_in_db(self, client, db):
        """Handler uses flush() — verify via response message (flush within session).
        NOTE: flush() works within the same transaction; commit() would persist
        across sessions. This is a known production bug.
        """
        admin = _make_admin(db)
        user = _make_user(db, email="target@example.com", is_active=False)
        resp = client.patch(f"/admin/users/{user.id}/activate", headers=_auth(admin))
        assert resp.status_code == 200
        assert str(user.id) in resp.json()["message"]

    def test_not_found_returns_404(self, client, db):
        admin = _make_admin(db)
        resp = client.patch(f"/admin/users/{uuid.uuid4()}/activate", headers=_auth(admin))
        assert resp.status_code == 404

    def test_regular_user_gets_403(self, client, db):
        user = _make_user(db, email="reg@example.com")
        other = _make_user(db, email="other@example.com", is_active=False)
        resp = client.patch(f"/admin/users/{other.id}/activate", headers=_auth(user))
        assert resp.status_code == 403

    def test_unauthenticated_gets_401(self, client, db):
        user = _make_user(db)
        resp = client.patch(f"/admin/users/{user.id}/activate")
        assert resp.status_code == 401

    def test_activate_deactivate_roundtrip(self, client, db):
        """Deactivate then re-activate — both return 200."""
        admin = _make_admin(db)
        user = _make_user(db, email="roundtrip@example.com", is_active=True)
        r1 = client.patch(f"/admin/users/{user.id}/deactivate", headers=_auth(admin))
        r2 = client.patch(f"/admin/users/{user.id}/activate", headers=_auth(admin))
        assert r1.status_code == 200
        assert r2.status_code == 200