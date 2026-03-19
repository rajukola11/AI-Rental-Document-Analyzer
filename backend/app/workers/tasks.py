import uuid
from celery import shared_task
from app.core.logging import get_logger

logger = get_logger(__name__)


@shared_task(
    bind=True,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=30,
    queue="documents",
)
def process_document(self, document_id: str) -> dict:
    """
    Main pipeline task:
    1. Fetch file from S3
    2. Extract text (pdfplumber / python-docx / OCR fallback)
    3. Send to OpenAI
    4. Parse JSON response
    5. Save Analysis to DB

    AI pipeline implemented in Phase 5.
    """
    from app.db.session import SessionLocal
    from app.services.document_service import get_document_by_id, set_document_status

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        doc = get_document_by_id(db, doc_uuid)
        if not doc:
            logger.error("Document not found in worker", extra={"document_id": document_id})
            return {"error": "Document not found"}

        # Mark as processing
        set_document_status(db, doc_uuid, "processing")
        db.commit()

        logger.info("Processing document", extra={"document_id": document_id})

        # ── Phase 5 will add: extract_text → ai_service → save_analysis ──

        return {"document_id": document_id, "status": "processing"}

    except Exception as exc:
        db.rollback()
        set_document_status(db, doc_uuid, "failed", error_message=str(exc))
        db.commit()
        logger.error("Document processing failed: %s", exc, extra={"document_id": document_id})
        raise self.retry(exc=exc)
    finally:
        db.close()