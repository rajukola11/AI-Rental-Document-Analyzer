import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Analysis(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "analyses"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # AI output fields
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    clauses: Mapped[list] = mapped_column(JSON, nullable=False, default=list)   # list of clause dicts
    risks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)     # list of risk strings
    risk_score: Mapped[str] = mapped_column(String(10), nullable=False)         # low | medium | high

    # Performance tracking
    processing_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # relationship
    document: Mapped["Document"] = relationship("Document", back_populates="analysis")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Analysis id={self.id} document={self.document_id} risk={self.risk_score}>"