import io
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status

from app.core.config import settings
from app.core.dependencies import CurrentUser, DBSession
from app.core.exceptions import FileTooLargeError, ForbiddenError, NotFoundError, UnsupportedFileTypeError
from app.core.logging import get_logger
from app.schemas.analysis import DocumentWithAnalysis
from app.schemas.document import DocumentListResponse, DocumentUploadResponse
from app.services.document_service import (
    create_document, get_document_for_user, list_documents_for_user,
    soft_delete_document, extend_document_expiry,
)
from app.services.user_service import increment_uploads

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def _get_local_upload_dir() -> Path:
    if settings.app_env == "production":
        d = Path("/tmp/uploads")
    else:
        d = Path(__file__).resolve().parents[4] / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _validate_upload(file: UploadFile, size: int) -> None:
    if file.content_type not in ALLOWED_MIME:
        raise UnsupportedFileTypeError()
    if size > settings.max_upload_size_bytes:
        raise FileTooLargeError(f"File exceeds {settings.max_upload_size_mb} MB limit.")


def _store_file(contents: bytes, content_type: str, user_id: uuid.UUID) -> str:
    aws_dummy = settings.aws_access_key_id in ("", "your-aws-access-key", "dummy")
    if not aws_dummy:
        from app.services.s3_service import upload_file as s3_upload
        return s3_upload(io.BytesIO(contents), content_type, user_id)
    upload_dir = _get_local_upload_dir()
    ext = ALLOWED_MIME[content_type]
    filename = f"{uuid.uuid4()}.{ext}"
    dest = upload_dir / str(user_id)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / filename).write_bytes(contents)
    local_key = f"local://{user_id}/{filename}"
    logger.info("Stored file locally", extra={"path": local_key})
    return local_key


def _queue_process(document_id: str) -> None:
    from app.workers.tasks import process_document
    process_document.delay(document_id)


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a rental contract PDF or DOCX for analysis",
)
async def upload_document(payload: CurrentUser, db: DBSession, file: UploadFile = File(...)):
    from app.models.user import User
    user_id = uuid.UUID(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    if not user.is_verified:
        raise ForbiddenError(
            "Please verify your email address before uploading documents."
        )
    if not user.can_upload:
        raise ForbiddenError(
            f"You have used all {user.uploads_used} free analyses. Purchase credits to continue."
        )

    contents = await file.read()
    _validate_upload(file, len(contents))
    file_key = _store_file(contents, file.content_type, user_id)

    doc = create_document(
        db=db,
        user_id=user_id,
        original_filename=file.filename or "upload",
        file_url=file_key,
        file_size_bytes=len(contents),
        content_type=file.content_type,
    )

    if user.upload_credits > 0:
        user.upload_credits -= 1
    increment_uploads(db, user_id)
    db.commit()

    _queue_process(str(doc.id))
    logger.info("Document uploaded", extra={"document_id": str(doc.id)})

    return DocumentUploadResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        status=doc.status,
        expires_at=doc.expires_at,
        message="Document uploaded successfully. Analysis is in progress.",
    )


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=DocumentListResponse, summary="List user documents")
def list_documents(
    payload: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    user_id = uuid.UUID(payload["sub"])
    items, total = list_documents_for_user(db, user_id, page, page_size)
    return DocumentListResponse(items=items, total=total, page=page, page_size=page_size)


# ── Get single ────────────────────────────────────────────────────────────────

@router.get("/{document_id}", response_model=DocumentWithAnalysis, summary="Get document + analysis")
def get_document(document_id: uuid.UUID, payload: CurrentUser, db: DBSession):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")
    return get_document_for_user(db, document_id, user_id, role)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.delete("/{document_id}", status_code=status.HTTP_200_OK, summary="Delete a document")
def delete_document(document_id: uuid.UUID, payload: CurrentUser, db: DBSession):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")

    doc = get_document_for_user(db, document_id, user_id, role)

    if doc.is_deleted:
        return {"message": "Document already deleted."}

    # Delete physical file in background to avoid blocking the request
    from app.workers.tasks import auto_delete_document
    auto_delete_document.delay(str(document_id))

    # Immediately soft-delete DB record so UI updates instantly
    soft_delete_document(db, document_id)
    db.commit()

    logger.info("Document manually deleted", extra={"document_id": str(document_id)})
    return {"message": "Document deleted successfully."}


# ── Reanalyze (free, only on failed documents) ────────────────────────────────

@router.post("/{document_id}/reanalyze", status_code=status.HTTP_202_ACCEPTED, summary="Reanalyze a failed document")
def reanalyze_document(document_id: uuid.UUID, payload: CurrentUser, db: DBSession):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")

    doc = get_document_for_user(db, document_id, user_id, role)

    if doc.is_deleted:
        raise ForbiddenError("Cannot reanalyze a deleted document.")
    if doc.status != "failed":
        raise ForbiddenError(f"Only failed documents can be reanalyzed. Current status: {doc.status}")

    from app.workers.tasks import reanalyze_document as reanalyze_task
    reanalyze_task.delay(str(document_id))

    logger.info("Reanalysis queued", extra={"document_id": str(document_id)})
    return {"message": "Reanalysis started. This is free since the document failed.", "document_id": str(document_id)}


# ── Keep document (extend expiry) ─────────────────────────────────────────────

@router.post("/{document_id}/keep", status_code=status.HTTP_200_OK, summary="Extend document expiry by 3 days")
def keep_document(document_id: uuid.UUID, payload: CurrentUser, db: DBSession):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")

    doc = get_document_for_user(db, document_id, user_id, role)

    if doc.is_deleted:
        raise ForbiddenError("Document has already been deleted.")

    doc = extend_document_expiry(db, document_id)

    # Reschedule warning + deletion tasks with new expiry
    from app.workers.tasks import _schedule_expiry_tasks
    _schedule_expiry_tasks(db, document_id)

    db.commit()
    logger.info("Document expiry extended", extra={"document_id": str(document_id)})
    return {
        "message": "Document kept for 3 more days.",
        "expires_at": doc.expires_at.isoformat() if doc.expires_at else None,
    }