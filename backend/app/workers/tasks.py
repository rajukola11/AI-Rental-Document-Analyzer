import os
import uuid
from datetime import timedelta, timezone, datetime

from celery import shared_task

from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Document processing ───────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.process_document",
    max_retries=3,
    default_retry_delay=30,
    queue="documents",
)
def process_document(self, document_id: str) -> dict:
    """
    Full pipeline:
    1. Fetch file (S3 or local)
    2. Extract text
    3. OpenAI analysis
    4. Save Analysis
    5. Mark completed / failed
    6. Schedule warning + deletion tasks
    """
    from app.db.session import SessionLocal
    from app.models.analysis import Analysis
    from app.services.document_service import get_document_by_id, set_document_status
    from app.services.document_processor import extract_text
    from app.services.ai_service import analyze_document

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        doc = get_document_by_id(db, doc_uuid)
        if not doc:
            logger.error("Document not found", extra={"document_id": document_id})
            return {"error": "Document not found"}

        set_document_status(db, doc_uuid, "processing")
        db.commit()

        file_data = _fetch_file(doc.file_url)
        text = extract_text(file_data, doc.content_type)
        logger.info("Text extracted", extra={"chars": len(text), "document_id": document_id})

        result, tokens, elapsed = analyze_document(text)

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

        # Schedule warning (2 days from now) and deletion (3 days from now)
        _schedule_expiry_tasks(db, doc_uuid)

        logger.info("Document completed", extra={"document_id": document_id})
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


# ── Reanalyze (free on failure) ───────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.reanalyze_document",
    max_retries=3,
    default_retry_delay=30,
    queue="documents",
)
def reanalyze_document(self, document_id: str) -> dict:
    """
    Re-run analysis on a failed document. No credit deducted.
    Deletes existing failed Analysis record and re-runs the full pipeline.
    """
    from app.db.session import SessionLocal
    from app.models.analysis import Analysis
    from app.services.document_service import get_document_by_id, set_document_status
    from app.services.document_processor import extract_text
    from app.services.ai_service import analyze_document

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        doc = get_document_by_id(db, doc_uuid)
        if not doc:
            return {"error": "Document not found"}

        if doc.is_deleted:
            return {"error": "Document has been deleted"}

        if doc.status not in ("failed",):
            return {"error": f"Cannot reanalyze document with status '{doc.status}'"}

        # Delete existing failed analysis if any
        db.query(Analysis).filter(Analysis.document_id == doc_uuid).delete()
        set_document_status(db, doc_uuid, "processing")
        db.commit()

        file_data = _fetch_file(doc.file_url)
        text = extract_text(file_data, doc.content_type)

        result, tokens, elapsed = analyze_document(text)

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

        _schedule_expiry_tasks(db, doc_uuid)

        logger.info("Reanalysis completed", extra={"document_id": document_id})
        return {"document_id": document_id, "status": "completed"}

    except Exception as exc:
        db.rollback()
        logger.error("Reanalysis failed: %s", exc, extra={"document_id": document_id}, exc_info=True)
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


# ── Deletion warning email ────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.send_deletion_warning",
    max_retries=3,
    default_retry_delay=60,
    queue="documents",
)
def send_deletion_warning(self, document_id: str) -> dict:
    """Send 24-hour deletion warning email to document owner."""
    from app.db.session import SessionLocal
    from app.services.document_service import get_document_by_id

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        doc = get_document_by_id(db, doc_uuid)
        if not doc or doc.is_deleted:
            return {"skipped": True, "reason": "Document already deleted"}

        user = doc.user
        if not user:
            return {"skipped": True, "reason": "User not found"}

        from app.services.email_service import send_deletion_warning_email
        send_deletion_warning_email(
            to=user.email,
            full_name=user.full_name,
            filename=doc.original_filename,
            document_id=str(doc.id),
            expires_at=doc.expires_at,
        )

        logger.info("Deletion warning sent", extra={"document_id": document_id})
        return {"document_id": document_id, "status": "warning_sent"}

    except Exception as exc:
        logger.error("Warning email failed: %s", exc, extra={"document_id": document_id})
        raise self.retry(exc=exc)
    finally:
        db.close()


# ── Auto delete document ──────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.workers.tasks.auto_delete_document",
    max_retries=3,
    default_retry_delay=120,
    queue="documents",
)
def auto_delete_document(self, document_id: str) -> dict:
    """
    Automatically delete a document after expiry.
    Idempotent — safe to retry.
    """
    from app.db.session import SessionLocal
    from app.services.document_service import get_document_by_id, soft_delete_document

    doc_uuid = uuid.UUID(document_id)
    db = SessionLocal()

    try:
        doc = get_document_by_id(db, doc_uuid)
        if not doc:
            return {"skipped": True, "reason": "Not found"}

        if doc.is_deleted:
            return {"skipped": True, "reason": "Already deleted"}

        # Delete physical file
        try:
            _delete_file(doc.file_url)
        except Exception as exc:
            logger.warning("File delete failed (will still soft-delete DB): %s", exc)

        # Soft-delete the DB record
        soft_delete_document(db, doc_uuid)
        db.commit()

        logger.info("Document auto-deleted", extra={"document_id": document_id})
        return {"document_id": document_id, "status": "deleted"}

    except Exception as exc:
        db.rollback()
        logger.error("Auto-delete failed: %s", exc, extra={"document_id": document_id})
        raise self.retry(exc=exc)
    finally:
        db.close()


# ── Scheduling helper ─────────────────────────────────────────────────────────

def _schedule_expiry_tasks(db, doc_uuid: uuid.UUID) -> None:
    """
    Schedule warning (expires_at - 1 day) and deletion (expires_at) tasks.
    Revokes any previously scheduled tasks for this document first.
    """
    from app.services.document_service import get_document_by_id
    from app.workers.celery_app import celery_app

    doc = get_document_by_id(db, doc_uuid)
    if not doc or not doc.expires_at:
        return

    # Revoke old tasks if they exist
    for task_id in [doc.warning_task_id, doc.deletion_task_id]:
        if task_id:
            try:
                celery_app.control.revoke(task_id, terminate=False)
            except Exception:
                pass

    expires_at = doc.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    warning_eta = expires_at - timedelta(days=1)
    deletion_eta = expires_at

    warning_result = send_deletion_warning.apply_async(
        args=[str(doc_uuid)],
        eta=warning_eta,
        queue="documents",
    )
    deletion_result = auto_delete_document.apply_async(
        args=[str(doc_uuid)],
        eta=deletion_eta,
        queue="documents",
    )

    # Store task IDs so we can revoke them if user extends
    db.query(__import__("app.models.document", fromlist=["Document"]).Document).filter_by(id=doc_uuid).update({
        "warning_task_id": warning_result.id,
        "deletion_task_id": deletion_result.id,
    })
    db.commit()

    logger.info(
        "Expiry tasks scheduled",
        extra={
            "document_id": str(doc_uuid),
            "warning_eta": str(warning_eta),
            "deletion_eta": str(deletion_eta),
        },
    )


# ── File helpers ──────────────────────────────────────────────────────────────

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
            logger.warning("Failed to delete file from S3: %s", exc)
            raise