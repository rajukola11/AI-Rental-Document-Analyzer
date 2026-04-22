import uuid
from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    file_size_bytes: int
    content_type: str
    status: str
    error_message: str | None
    is_deleted: bool
    deleted_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(BaseModel):
    """Returned immediately after upload — before analysis completes."""
    id: uuid.UUID
    original_filename: str
    status: str
    expires_at: datetime | None
    message: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class AdminDocumentItem(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    status: str
    is_deleted: bool
    created_at: datetime

    model_config = {"from_attributes": True}