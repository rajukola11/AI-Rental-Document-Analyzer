import os
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
    Full document processing pipeline:
    1. Fetch file (S3 or local)
    2. Extract text (pdfplumber / python-docx / OCR fallback)
    3. Send to OpenAI -> structured JSON
    4. Save Analysis to DB
    5. Mark document as completed (or failed)
    """
    from app.db.session import SessionLocal
    from app.models.analysis import Analysis
    from app.services.document_service import get_document_by_id, set_document_status
    from app.services.document_processor import extract_text
    from app.services.ai_service import analyze_document

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        # 1. Load document record
        doc = get_document_by_id(db, doc_uuid)
        if not doc:
            logger.error("Document not found", extra={"document_id": document_id})
            return {"error": "Document not found"}

        set_document_status(db, doc_uuid, "processing")
        db.commit()
        logger.info("Processing started", extra={"document_id": document_id})

        # 2. Fetch file bytes
        file_data = _fetch_file(doc.file_url)

        # 3. Extract text
        text = extract_text(file_data, doc.content_type)
        logger.info("Text extracted", extra={"chars": len(text), "document_id": document_id})

        # 4. AI analysis
        result, tokens, elapsed = analyze_document(text)
        logger.info(
            "AI analysis complete",
            extra={"risk_score": result.risk_score, "tokens": tokens, "document_id": document_id},
        )

        # 5. Save analysis
        from app.core.config import settings
        analysis = Analysis(
            document_id=doc_uuid,
            summary=result.summary,
            clauses=[c.model_dump() for c in result.clauses],
            risks=result.risks,
            risk_score=result.risk_score,
            processing_time_seconds=elapsed,
            tokens_used=tokens,
            model_used=settings.openai_model,
        )
        db.add(analysis)
        set_document_status(db, doc_uuid, "completed")
        db.commit()

        logger.info("Document completed", extra={"document_id": document_id})

        # 6. GDPR: delete file if configured
        from app.core.config import settings as s
        if s.delete_files_after_processing:
            _delete_file(doc.file_url)

        return {
            "document_id": document_id,
            "status": "completed",
            "risk_score": result.risk_score,
            "tokens_used": tokens,
        }

    except Exception as exc:
        db.rollback()
        logger.error("Processing failed: %s", exc, extra={"document_id": document_id}, exc_info=True)
        try:
            set_document_status(db, doc_uuid, "failed", error_message=str(exc))
            db.commit()
        except Exception:
            db.rollback()

        if not isinstance(exc, ValueError):
            raise self.retry(exc=exc)
        return {"document_id": document_id, "status": "failed", "error": str(exc)}

    finally:
        db.close()


def _fetch_file(file_url: str) -> bytes:
    if file_url.startswith("local://"):
        from pathlib import Path
        relative = file_url.replace("local://", "")
        base = Path(__file__).resolve().parents[3] / "uploads"
        path = base / relative
        if not path.exists():
            raise FileNotFoundError(f"Local file not found: {path}")
        return path.read_bytes()
    else:
        from app.services.s3_service import download_file_bytes
        return download_file_bytes(file_url)


def _delete_file(file_url: str) -> None:
    if file_url.startswith("local://"):
        from pathlib import Path
        relative = file_url.replace("local://", "")
        base = Path(__file__).resolve().parents[3] / "uploads"
        (base / relative).unlink(missing_ok=True)
    else:
        from app.services.s3_service import delete_file
        try:
            delete_file(file_url)
        except Exception as exc:
            logger.warning("Failed to delete file: %s", exc)