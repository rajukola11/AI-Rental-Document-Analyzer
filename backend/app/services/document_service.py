import uuid
from sqlalchemy.orm import Session, joinedload

from app.models.document import Document
from app.models.analysis import Analysis
from app.core.exceptions import NotFoundError, ForbiddenError
from app.core.logging import get_logger

logger = get_logger(__name__)


def create_document(
    db: Session,
    user_id: uuid.UUID,
    original_filename: str,
    file_url: str,
    file_size_bytes: int,
    content_type: str,
) -> Document:
    doc = Document(
        user_id=user_id,
        original_filename=original_filename,
        file_url=file_url,
        file_size_bytes=file_size_bytes,
        content_type=content_type,
        status="uploaded",
    )
    db.add(doc)
    db.flush()
    logger.info("Document record created", extra={"document_id": str(doc.id)})
    return doc


def get_document_by_id(db: Session, document_id: uuid.UUID) -> Document | None:
    return (
        db.query(Document)
        .options(joinedload(Document.analysis))
        .filter(Document.id == document_id)
        .first()
    )


def get_document_for_user(
    db: Session, document_id: uuid.UUID, user_id: uuid.UUID, role: str
) -> Document:
    doc = get_document_by_id(db, document_id)
    if not doc:
        raise NotFoundError("Document not found.")
    if role != "admin" and doc.user_id != user_id:
        raise ForbiddenError()
    return doc


def list_documents_for_user(
    db: Session, user_id: uuid.UUID, page: int = 1, page_size: int = 20
) -> tuple[list[Document], int]:
    q = db.query(Document).filter(Document.user_id == user_id)
    total = q.count()
    items = q.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def list_all_documents(
    db: Session, page: int = 1, page_size: int = 50
) -> tuple[list[Document], int]:
    q = db.query(Document)
    total = q.count()
    items = q.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def set_document_status(
    db: Session, document_id: uuid.UUID, status: str, error_message: str | None = None
) -> None:
    db.query(Document).filter(Document.id == document_id).update(
        {"status": status, "error_message": error_message}
    )