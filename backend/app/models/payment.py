import uuid
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin, UUIDMixin


class Payment(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stripe_session_id:      Mapped[str]      = mapped_column(String(255), nullable=False, unique=True)
    stripe_payment_intent:  Mapped[str|None] = mapped_column(String(255), nullable=True)
    amount_cents:           Mapped[int]      = mapped_column(Integer, nullable=False)
    currency:               Mapped[str]      = mapped_column(String(10), nullable=False, default="eur")
    credits:                Mapped[int]      = mapped_column(Integer, nullable=False, default=1)
    # pending | completed | failed | refunded
    status:                 Mapped[str]      = mapped_column(String(20), nullable=False, default="pending")

    user: Mapped["User"] = relationship("User", back_populates="payments")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Payment id={self.id} user={self.user_id} status={self.status} credits={self.credits}>"