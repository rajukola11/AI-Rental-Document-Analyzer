import io
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile, status

from app.core.config import settings
from app.core.dependencies import CurrentUser, DBSession
from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError
from app.core.logging import get_logger
from app.schemas.analysis import DocumentWithAnalysis
from app.schemas.document import (
    DocumentListResponse,
    DocumentUploadResponse,
)
from app.services.document_service import (
    create_document,
    get_document_for_user,
    list_documents_for_user,
)
from app.services.user_service import increment_uploads

logger = get_logger(__name__)
router = APIRouter()

ALLOWED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# Local upload dir — used when real AWS creds are not configured
LOCAL_UPLOAD_DIR = Path(__file__).resolve().parents[4] / "uploads"
LOCAL_UPLOAD_DIR.mkdir(exist_ok=True)


def _validate_upload(file: UploadFile, size: int) -> None:
    if file.content_type not in ALLOWED_MIME:
        raise UnsupportedFileTypeError()
    if size > settings.max_upload_size_bytes:
        raise FileTooLargeError(f"File exceeds {settings.max_upload_size_mb} MB limit.")


def _store_file(contents: bytes, content_type: str, user_id: uuid.UUID) -> str:
    """
    Try S3 first. Fall back to local disk if AWS creds are not configured.
    Returns a string key stored in documents.file_url.
    """
    aws_dummy = settings.aws_access_key_id in ("", "your-aws-access-key", "dummy")

    if not aws_dummy:
        from app.services.s3_service import upload_file as s3_upload
        return s3_upload(io.BytesIO(contents), content_type, user_id)

    # ── Local fallback ────────────────────────────────────────────────────────
    ext = ALLOWED_MIME[content_type]
    filename = f"{uuid.uuid4()}.{ext}"
    dest = LOCAL_UPLOAD_DIR / str(user_id)
    dest.mkdir(exist_ok=True)
    (dest / filename).write_bytes(contents)
    local_key = f"local://{user_id}/{filename}"
    logger.info("Stored file locally (S3 not configured)", extra={"path": local_key})
    return local_key


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
    contents = await file.read()
    _validate_upload(file, len(contents))

    user_id = uuid.UUID(payload["sub"])
    file_key = _store_file(contents, file.content_type, user_id)

    doc = create_document(
        db=db,
        user_id=user_id,
        original_filename=file.filename or "upload",
        file_url=file_key,
        file_size_bytes=len(contents),
        content_type=file.content_type,
    )

    increment_uploads(db, user_id)

    # Queue background task
    from app.workers.tasks import process_document
    process_document.delay(str(doc.id))

    logger.info("Document uploaded, task queued", extra={"document_id": str(doc.id)})

    return DocumentUploadResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        status=doc.status,
        message="Document uploaded successfully. Analysis is in progress.",
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents for the current user",
)
def list_documents(
    payload: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    user_id = uuid.UUID(payload["sub"])
    items, total = list_documents_for_user(db, user_id, page, page_size)
    return DocumentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{document_id}",
    response_model=DocumentWithAnalysis,
    summary="Get a document and its analysis result",
)
def get_document(
    document_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    user_id = uuid.UUID(payload["sub"])
    role = payload.get("role", "user")
    doc = get_document_for_user(db, document_id, user_id, role)
    return doc