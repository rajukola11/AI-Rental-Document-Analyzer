import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_url: Mapped[str] = mapped_column(Text, nullable=False)        # S3 key
    file_size_bytes: Mapped[int] = mapped_column(nullable=False, default=0)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)

    # uploaded | processing | completed | failed
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="documents")  # noqa: F821
    analysis: Mapped["Analysis | None"] = relationship(  # noqa: F821
        "Analysis", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} status={self.status} user={self.user_id}>"