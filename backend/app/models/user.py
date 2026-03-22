import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin

FREE_UPLOAD_LIMIT = 2


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email:          Mapped[str]      = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash:  Mapped[str]      = mapped_column(String(255), nullable=False)
    full_name:      Mapped[str|None] = mapped_column(String(255), nullable=True)
    role:           Mapped[str]      = mapped_column(String(20),  nullable=False, default="user")
    is_active:      Mapped[bool]     = mapped_column(Boolean,     nullable=False, default=True)
    uploads_used:   Mapped[int]      = mapped_column(nullable=False, default=0)
    upload_credits: Mapped[int]      = mapped_column(nullable=False, default=0, server_default='0')

    # ── Email verification ────────────────────────────────────────────────────
    is_verified:                  Mapped[bool]           = mapped_column(Boolean,      nullable=False, default=False, server_default='false')
    verification_token:           Mapped[str | None]     = mapped_column(String(64),   nullable=True,  index=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["Document"]] = relationship(  # noqa: F821
        "Document", back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(  # noqa: F821
        "Payment", back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def can_upload(self) -> bool:
        """True if user is verified AND has free uploads remaining OR paid credits."""
        if not self.is_verified:
            return False
        return self.uploads_used < FREE_UPLOAD_LIMIT or self.upload_credits > 0

    @property
    def free_uploads_remaining(self) -> int:
        return max(0, FREE_UPLOAD_LIMIT - self.uploads_used)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role} verified={self.is_verified}>"