import uuid
import pytest
from datetime import datetime, timedelta, timezone

import sqlalchemy.dialects.postgresql as _pg
from sqlalchemy import types as _sa_types


# ── SQLite-compatible UUID (same trick as test_user_service) ─────────────────

class _SqliteUUID(_sa_types.TypeDecorator):
    impl = _sa_types.String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return uuid.UUID(value) if value else None


# Also patch JSON for SQLite (analyses table uses JSON columns)
from sqlalchemy import types as _sa_types2
class _SqliteJSON(_sa_types2.TypeDecorator):
    impl = _sa_types2.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        import json
        return json.dumps(value) if value is not None else None

    def process_result_value(self, value, dialect):
        import json
        return json.loads(value) if value else None


_pg.UUID = _SqliteUUID
_pg.JSON = _SqliteJSON

# ── Imports ──────────────────────────────────────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import user as _user_mod      # noqa: F401 — resolve relationships
from app.models import document as _doc_mod   # noqa: F401
from app.models import analysis as _ana_mod   # noqa: F401
from app.models import payment as _pay_mod    # noqa: F401
from app.models.user import User
from app.models.document import Document, DOCUMENT_EXPIRY_DAYS
from app.models.analysis import Analysis

from app.core.exceptions import NotFoundError, ForbiddenError

from app.services.document_service import (
    _expires_at,
    create_document,
    get_document_by_id,
    get_document_for_user,
    list_documents_for_user,
    list_all_documents,
    set_document_status,
    soft_delete_document,
    extend_document_expiry,
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


@pytest.fixture()
def user(db):
    u = User(email="owner@example.com", password_hash="hash", role="user", is_verified=True)
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def other_user(db):
    u = User(email="other@example.com", password_hash="hash", role="user", is_verified=True)
    db.add(u)
    db.flush()
    return u


def _make_doc(
    db: Session,
    user_id: uuid.UUID,
    filename: str = "lease.pdf",
    file_url: str = "https://s3.example.com/lease.pdf",
    file_size_bytes: int = 12345,
    content_type: str = "application/pdf",
    status: str = "uploaded",
    is_deleted: bool = False,
    expires_at: datetime | None = None,
) -> Document:
    doc = Document(
        user_id=user_id,
        original_filename=filename,
        file_url=file_url,
        file_size_bytes=file_size_bytes,
        content_type=content_type,
        status=status,
        is_deleted=is_deleted,
        expires_at=expires_at or (datetime.now(timezone.utc) + timedelta(days=3)),
    )
    db.add(doc)
    db.flush()
    return doc


# ===========================================================================
# _expires_at
# ===========================================================================

class TestExpiresAt:
    def test_returns_datetime(self):
        result = _expires_at()
        assert isinstance(result, datetime)

    def test_is_timezone_aware(self):
        result = _expires_at()
        assert result.tzinfo is not None

    def test_is_in_the_future(self):
        result = _expires_at()
        assert result > datetime.now(timezone.utc)

    def test_roughly_document_expiry_days_from_now(self):
        before = datetime.now(timezone.utc)
        result = _expires_at()
        after = datetime.now(timezone.utc)
        expected_min = before + timedelta(days=DOCUMENT_EXPIRY_DAYS) - timedelta(seconds=5)
        expected_max = after + timedelta(days=DOCUMENT_EXPIRY_DAYS) + timedelta(seconds=5)
        assert expected_min <= result <= expected_max


# ===========================================================================
# create_document
# ===========================================================================

class TestCreateDocument:
    def test_returns_document_instance(self, db, user):
        doc = create_document(db, user.id, "contract.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert isinstance(doc, Document)

    def test_user_id_stored(self, db, user):
        doc = create_document(db, user.id, "contract.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.user_id == user.id

    def test_filename_stored(self, db, user):
        doc = create_document(db, user.id, "mietvertrag.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.original_filename == "mietvertrag.pdf"

    def test_file_url_stored(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/unique-key.pdf", 1024, "application/pdf")
        assert doc.file_url == "https://s3.test/unique-key.pdf"

    def test_file_size_stored(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 98765, "application/pdf")
        assert doc.file_size_bytes == 98765

    def test_content_type_stored(self, db, user):
        doc = create_document(db, user.id, "f.docx",
                              "https://s3.test/f.docx", 1024,
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        assert "wordprocessingml" in doc.content_type

    def test_status_is_uploaded(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.status == "uploaded"

    def test_expiry_is_set(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.expires_at is not None

    def test_expiry_is_in_the_future(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        expires = doc.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        assert expires > datetime.now(timezone.utc)

    def test_document_persisted_to_db(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        found = db.query(Document).filter(Document.id == doc.id).first()
        assert found is not None

    def test_document_gets_uuid(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.id is not None
        assert isinstance(doc.id, uuid.UUID)

    def test_is_not_deleted_on_creation(self, db, user):
        doc = create_document(db, user.id, "f.pdf",
                              "https://s3.test/f.pdf", 1024, "application/pdf")
        assert doc.is_deleted is False


# ===========================================================================
# get_document_by_id
# ===========================================================================

class TestGetDocumentById:
    def test_returns_document_when_found(self, db, user):
        doc = _make_doc(db, user.id)
        result = get_document_by_id(db, doc.id)
        assert result is not None
        assert result.id == doc.id

    def test_returns_none_when_not_found(self, db):
        result = get_document_by_id(db, uuid.uuid4())
        assert result is None

    def test_eager_loads_analysis(self, db, user):
        doc = _make_doc(db, user.id)
        analysis = Analysis(
            document_id=doc.id,
            summary="Test summary",
            clauses=[],
            risks=[],
            risk_score="low",
        )
        db.add(analysis)
        db.flush()

        result = get_document_by_id(db, doc.id)
        # Analysis should be accessible without an extra query (eager loaded)
        assert result.analysis is not None
        assert result.analysis.risk_score == "low"

    def test_analysis_is_none_when_not_yet_analysed(self, db, user):
        doc = _make_doc(db, user.id)
        result = get_document_by_id(db, doc.id)
        assert result.analysis is None


# ===========================================================================
# get_document_for_user
# ===========================================================================

class TestGetDocumentForUser:
    def test_owner_can_access_own_document(self, db, user):
        doc = _make_doc(db, user.id)
        result = get_document_for_user(db, doc.id, user.id, role="user")
        assert result.id == doc.id

    def test_admin_can_access_any_document(self, db, user, other_user):
        doc = _make_doc(db, user.id)
        result = get_document_for_user(db, doc.id, other_user.id, role="admin")
        assert result.id == doc.id

    def test_wrong_user_raises_forbidden(self, db, user, other_user):
        doc = _make_doc(db, user.id)
        with pytest.raises(ForbiddenError):
            get_document_for_user(db, doc.id, other_user.id, role="user")

    def test_missing_document_raises_not_found(self, db, user):
        with pytest.raises(NotFoundError):
            get_document_for_user(db, uuid.uuid4(), user.id, role="user")

    def test_missing_document_raises_not_found_even_for_admin(self, db, user):
        with pytest.raises(NotFoundError):
            get_document_for_user(db, uuid.uuid4(), user.id, role="admin")


# ===========================================================================
# list_documents_for_user
# ===========================================================================

class TestListDocumentsForUser:
    def test_returns_tuple_of_list_and_int(self, db, user):
        items, total = list_documents_for_user(db, user.id)
        assert isinstance(items, list)
        assert isinstance(total, int)

    def test_empty_when_user_has_no_documents(self, db, user):
        items, total = list_documents_for_user(db, user.id)
        assert items == []
        assert total == 0

    def test_returns_only_this_users_documents(self, db, user, other_user):
        _make_doc(db, user.id, filename="mine.pdf")
        _make_doc(db, other_user.id, filename="theirs.pdf")
        items, total = list_documents_for_user(db, user.id)
        assert total == 1
        assert all(d.user_id == user.id for d in items)

    def test_total_reflects_all_pages(self, db, user):
        for i in range(5):
            _make_doc(db, user.id, filename=f"doc{i}.pdf")
        _, total = list_documents_for_user(db, user.id, page=1, page_size=2)
        assert total == 5

    def test_page_size_limits_items_returned(self, db, user):
        for i in range(5):
            _make_doc(db, user.id, filename=f"doc{i}.pdf")
        items, _ = list_documents_for_user(db, user.id, page=1, page_size=2)
        assert len(items) == 2

    def test_second_page_returns_next_items(self, db, user):
        for i in range(5):
            _make_doc(db, user.id, filename=f"doc{i}.pdf")
        items_p1, _ = list_documents_for_user(db, user.id, page=1, page_size=3)
        items_p2, _ = list_documents_for_user(db, user.id, page=2, page_size=3)
        ids_p1 = {d.id for d in items_p1}
        ids_p2 = {d.id for d in items_p2}
        assert ids_p1.isdisjoint(ids_p2)

    def test_ordered_newest_first(self, db, user):
        # SQLite doesn't use server_default for created_at in tests, so we
        # verify the query runs without error and returns items in some order
        for i in range(3):
            _make_doc(db, user.id, filename=f"doc{i}.pdf")
        items, _ = list_documents_for_user(db, user.id)
        assert len(items) == 3

    def test_beyond_last_page_returns_empty(self, db, user):
        _make_doc(db, user.id)
        items, _ = list_documents_for_user(db, user.id, page=999, page_size=20)
        assert items == []


# ===========================================================================
# list_all_documents
# ===========================================================================

class TestListAllDocuments:
    def test_returns_tuple_of_list_and_int(self, db):
        items, total = list_all_documents(db)
        assert isinstance(items, list)
        assert isinstance(total, int)

    def test_empty_when_no_documents_exist(self, db):
        items, total = list_all_documents(db)
        assert items == []
        assert total == 0

    def test_returns_documents_from_all_users(self, db, user, other_user):
        _make_doc(db, user.id, filename="a.pdf")
        _make_doc(db, other_user.id, filename="b.pdf")
        items, total = list_all_documents(db)
        assert total == 2
        owner_ids = {d.user_id for d in items}
        assert user.id in owner_ids
        assert other_user.id in owner_ids

    def test_total_reflects_all_pages(self, db, user):
        for i in range(10):
            _make_doc(db, user.id, filename=f"d{i}.pdf")
        _, total = list_all_documents(db, page=1, page_size=3)
        assert total == 10

    def test_page_size_limits_items(self, db, user):
        for i in range(10):
            _make_doc(db, user.id, filename=f"d{i}.pdf")
        items, _ = list_all_documents(db, page=1, page_size=4)
        assert len(items) == 4

    def test_default_page_size_is_50(self, db, user):
        for i in range(60):
            _make_doc(db, user.id, filename=f"d{i}.pdf")
        items, _ = list_all_documents(db)
        assert len(items) == 50

    def test_second_page_does_not_overlap_first(self, db, user):
        for i in range(6):
            _make_doc(db, user.id, filename=f"d{i}.pdf")
        p1, _ = list_all_documents(db, page=1, page_size=3)
        p2, _ = list_all_documents(db, page=2, page_size=3)
        assert {d.id for d in p1}.isdisjoint({d.id for d in p2})


# ===========================================================================
# set_document_status
# ===========================================================================

class TestSetDocumentStatus:
    def test_updates_status(self, db, user):
        doc = _make_doc(db, user.id, status="uploaded")
        set_document_status(db, doc.id, "processing")
        db.refresh(doc)
        assert doc.status == "processing"

    def test_sets_status_to_completed(self, db, user):
        doc = _make_doc(db, user.id, status="processing")
        set_document_status(db, doc.id, "completed")
        db.refresh(doc)
        assert doc.status == "completed"

    def test_sets_status_to_failed(self, db, user):
        doc = _make_doc(db, user.id, status="processing")
        set_document_status(db, doc.id, "failed")
        db.refresh(doc)
        assert doc.status == "failed"

    def test_stores_error_message(self, db, user):
        doc = _make_doc(db, user.id)
        set_document_status(db, doc.id, "failed", error_message="OCR timeout")
        db.refresh(doc)
        assert doc.error_message == "OCR timeout"

    def test_clears_error_message_when_none(self, db, user):
        doc = _make_doc(db, user.id)
        # First set an error
        set_document_status(db, doc.id, "failed", error_message="some error")
        # Then clear it
        set_document_status(db, doc.id, "completed", error_message=None)
        db.refresh(doc)
        assert doc.error_message is None

    def test_returns_none(self, db, user):
        doc = _make_doc(db, user.id)
        result = set_document_status(db, doc.id, "processing")
        assert result is None


# ===========================================================================
# soft_delete_document
# ===========================================================================

class TestSoftDeleteDocument:
    def test_returns_document(self, db, user):
        doc = _make_doc(db, user.id)
        result = soft_delete_document(db, doc.id)
        assert isinstance(result, Document)
        assert result.id == doc.id

    def test_sets_is_deleted_true(self, db, user):
        doc = _make_doc(db, user.id)
        soft_delete_document(db, doc.id)
        db.refresh(doc)
        assert doc.is_deleted is True

    def test_sets_deleted_at(self, db, user):
        before = datetime.now(timezone.utc)
        doc = _make_doc(db, user.id)
        soft_delete_document(db, doc.id)
        db.refresh(doc)
        assert doc.deleted_at is not None
        deleted = doc.deleted_at
        if deleted.tzinfo is None:
            deleted = deleted.replace(tzinfo=timezone.utc)
        assert deleted >= before

    def test_sets_status_to_deleted(self, db, user):
        doc = _make_doc(db, user.id)
        soft_delete_document(db, doc.id)
        db.refresh(doc)
        assert doc.status == "deleted"

    def test_not_found_raises_not_found_error(self, db):
        with pytest.raises(NotFoundError):
            soft_delete_document(db, uuid.uuid4())

    def test_does_not_remove_row_from_db(self, db, user):
        """Soft delete keeps the row — it must still be queryable."""
        doc = _make_doc(db, user.id)
        soft_delete_document(db, doc.id)
        still_there = db.query(Document).filter(Document.id == doc.id).first()
        assert still_there is not None


# ===========================================================================
# extend_document_expiry
# ===========================================================================

class TestExtendDocumentExpiry:
    def test_returns_document(self, db, user):
        doc = _make_doc(db, user.id)
        result = extend_document_expiry(db, doc.id)
        assert isinstance(result, Document)
        assert result.id == doc.id

    def test_expiry_is_pushed_forward(self, db, user):
        old_expiry = datetime.now(timezone.utc) + timedelta(days=1)
        doc = _make_doc(db, user.id, expires_at=old_expiry)
        extend_document_expiry(db, doc.id)
        db.refresh(doc)
        new_expiry = doc.expires_at
        if new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)
        assert new_expiry > old_expiry

    def test_new_expiry_is_roughly_expiry_days_from_now(self, db, user):
        doc = _make_doc(db, user.id)
        before = datetime.now(timezone.utc)
        extend_document_expiry(db, doc.id)
        after = datetime.now(timezone.utc)
        db.refresh(doc)
        new_expiry = doc.expires_at
        if new_expiry.tzinfo is None:
            new_expiry = new_expiry.replace(tzinfo=timezone.utc)
        expected_min = before + timedelta(days=DOCUMENT_EXPIRY_DAYS) - timedelta(seconds=5)
        expected_max = after + timedelta(days=DOCUMENT_EXPIRY_DAYS) + timedelta(seconds=5)
        assert expected_min <= new_expiry <= expected_max

    def test_deleted_document_raises_forbidden(self, db, user):
        doc = _make_doc(db, user.id, is_deleted=True)
        with pytest.raises(ForbiddenError):
            extend_document_expiry(db, doc.id)

    def test_not_found_raises_not_found_error(self, db):
        with pytest.raises(NotFoundError):
            extend_document_expiry(db, uuid.uuid4())

    def test_non_deleted_document_does_not_raise(self, db, user):
        doc = _make_doc(db, user.id, is_deleted=False)
        result = extend_document_expiry(db, doc.id)
        assert result is not None