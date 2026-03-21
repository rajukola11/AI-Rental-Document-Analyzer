import io
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status

from app.core.config import settings
from app.core.dependencies import CurrentUser, DBSession
from app.core.exceptions import FileTooLargeError, ForbiddenError, UnsupportedFileTypeError
from app.core.logging import get_logger
from app.schemas.analysis import DocumentWithAnalysis
from app.schemas.document import DocumentListResponse, DocumentUploadResponse
from app.services.document_service import (
    create_document, get_document_for_user, list_documents_for_user,
)
from app.services.user_service import increment_uploads

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

LOCAL_UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads"
LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)


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

    ext = ALLOWED_MIME[content_type]
    filename = f"{uuid.uuid4()}.{ext}"
    dest = LOCAL_UPLOAD_DIR / str(user_id)
    dest.mkdir(exist_ok=True)
    (dest / filename).write_bytes(contents)
    local_key = f"local://{user_id}/{filename}"
    logger.info("Stored file locally", extra={"path": local_key})
    return local_key


def _queue_task(document_id: str) -> None:
    import os
    os.environ.setdefault("CELERY_BROKER_URL", settings.celery_broker_url)
    os.environ.setdefault("CELERY_RESULT_BACKEND", settings.celery_result_backend)
    from app.workers.tasks import process_document
    process_document.delay(document_id)


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a rental contract PDF or DOCX for analysis",
)
async def upload_document(
    payload: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
):
    from app.models.user import User
    user_id = uuid.UUID(payload["sub"])
    user = db.query(User).filter(User.id == user_id).first()

    # ── Enforce upload limits ─────────────────────────────────────────────────
    if not user.can_upload:
        raise ForbiddenError(
            f"You have used all {user.uploads_used} free analyses. "
            "Purchase credits to continue."
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

    # Deduct credit: paid first, then free
    if user.upload_credits > 0:
        user.upload_credits -= 1
    increment_uploads(db, user_id)

    _queue_task(str(doc.id))

    logger.info("Document uploaded", extra={"document_id": str(doc.id)})

    return DocumentUploadResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        status=doc.status,
        message="Document uploaded successfully. Analysis is in progress.",
    )


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


@router.get("/{document_id}", response_model=DocumentWithAnalysis, summary="Get document + analysis")
def get_document(
    document_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")
    return get_document_for_user(db, document_id, user_id, role)