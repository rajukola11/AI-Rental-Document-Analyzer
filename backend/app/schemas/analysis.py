import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Clause(BaseModel):
    type: str = Field(description="Clause category e.g. Deposit, Notice period, Pets")
    text: str = Field(description="Original or translated clause text")
    explanation: str = Field(description="Plain-English explanation for a non-German speaker")


class AnalysisResult(BaseModel):
    """Mirrors the structured JSON the AI returns."""
    summary: str
    clauses: list[Clause]
    risks: list[str]
    risk_score: Literal["low", "medium", "high"]


class AnalysisResponse(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    summary: str
    clauses: list[Clause]
    risks: list[str]
    risk_score: str
    processing_time_seconds: float | None
    tokens_used: int | None
    model_used: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentWithAnalysis(BaseModel):
    """Full document detail including embedded analysis if available."""
    id: uuid.UUID
    user_id: uuid.UUID
    original_filename: str
    file_size_bytes: int
    content_type: str
    status: str
    error_message: str | None
    created_at: datetime
    analysis: AnalysisResponse | None

    model_config = {"from_attributes": True}