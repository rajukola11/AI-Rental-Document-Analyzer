import uuid
from fastapi import APIRouter, Query,Depends
from app.core.dependencies import CurrentUser, DBSession, require_role
from app.core.exceptions import NotFoundError
from app.schemas.user import UserListItem
from app.schemas.document import AdminDocumentItem, DocumentListResponse
from app.schemas.analysis import DocumentWithAnalysis
from app.services.document_service import (
    get_document_by_id,
    list_all_documents,
)

router = APIRouter(dependencies=[Depends(require_role("admin"))])


@router.get(
    "/users",
    response_model=list[UserListItem],
    summary="List all registered users",
)
def list_users(
    payload: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    from app.models.user import User
    offset = (page - 1) * page_size
    users = (
        db.query(User)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
    return users


@router.get(
    "/users/{user_id}",
    response_model=UserListItem,
    summary="Get a specific user by ID",
)
def get_user(
    user_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("User not found.")
    return user


@router.get(
    "/documents",
    summary="List all documents across all users",
)
def list_documents(
    payload: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: str | None = Query(None, description="Filter by status: uploaded|processing|completed|failed"),
):
    from app.models.document import Document
    q = db.query(Document)
    if status:
        q = q.filter(Document.status == status)
    total = q.count()
    items = (
        q.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get(
    "/documents/{document_id}",
    response_model=DocumentWithAnalysis,
    summary="Get any document with its analysis",
)
def get_document(
    document_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    doc = get_document_by_id(db, document_id)
    if not doc:
        raise NotFoundError("Document not found.")
    return doc


@router.get(
    "/stats",
    summary="System usage statistics",
)
def get_stats(
    payload: CurrentUser,
    db: DBSession,
):
    from app.models.user import User
    from app.models.document import Document
    from app.models.analysis import Analysis
    from sqlalchemy import func

    total_users     = db.query(func.count(User.id)).scalar()
    total_documents = db.query(func.count(Document.id)).scalar()
    total_analyses  = db.query(func.count(Analysis.id)).scalar()

    by_status = (
        db.query(Document.status, func.count(Document.id))
        .group_by(Document.status)
        .all()
    )
    by_risk = (
        db.query(Analysis.risk_score, func.count(Analysis.id))
        .group_by(Analysis.risk_score)
        .all()
    )
    avg_tokens = db.query(func.avg(Analysis.tokens_used)).scalar()
    avg_time   = db.query(func.avg(Analysis.processing_time_seconds)).scalar()

    return {
        "users": {"total": total_users},
        "documents": {
            "total": total_documents,
            "by_status": {s: c for s, c in by_status},
        },
        "analyses": {
            "total": total_analyses,
            "by_risk_score": {r: c for r, c in by_risk},
            "avg_tokens_used": round(avg_tokens or 0, 1),
            "avg_processing_seconds": round(avg_time or 0, 2),
        },
    }


@router.patch(
    "/users/{user_id}/deactivate",
    summary="Deactivate a user account",
)
def deactivate_user(
    user_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("User not found.")
    user.is_active = False
    db.flush()
    return {"message": f"User {user_id} deactivated."}


@router.patch(
    "/users/{user_id}/activate",
    summary="Reactivate a user account",
)
def activate_user(
    user_id: uuid.UUID,
    payload: CurrentUser,
    db: DBSession,
):
    from app.models.user import User
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise NotFoundError("User not found.")
    user.is_active = True
    db.flush()
    return {"message": f"User {user_id} activated."}