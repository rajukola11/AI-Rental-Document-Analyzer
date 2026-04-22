import secrets
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)

_TOKEN_BYTES = 32   # 256-bit URL-safe token


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_verification_token(db: Session, token: str) -> User | None:
    return db.query(User).filter(User.verification_token == token).first()


def _generate_verification_token(db: Session, user: User) -> str:
    """Assign a fresh token + expiry to the user. Caller must flush/commit."""
    from app.core.config import settings
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    user.verification_token = token
    user.verification_token_expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.verification_token_expire_hours
    )
    return token


def create_user(db: Session, email: str, password: str, full_name: str | None = None) -> tuple["User", str]:
    """
    Create a new unverified user and return (user, verification_token).
    Raises ValidationError if email is disposable or already registered.
    """
    from app.services.disposable_email_service import is_disposable_email

    normalized = email.lower().strip()

    if is_disposable_email(normalized):
        raise ValidationError(
            "Disposable or temporary email addresses are not allowed. "
            "Please use a permanent email address."
        )

    if get_user_by_email(db, normalized):
        raise ValidationError("An account with this email already exists.")

    user = User(
        email=normalized,
        password_hash=hash_password(password),
        full_name=full_name,
        role="user",
        is_verified=False,
    )
    db.add(user)
    db.flush()  # get ID

    token = _generate_verification_token(db, user)
    db.flush()

    logger.info("User created (unverified)", extra={"user_id": str(user.id)})
    return user, token


def verify_email_token(db: Session, token: str) -> User:
    """
    Consume a verification token and mark the user as verified.
    Raises ValidationError on invalid/expired token.
    """
    user = get_user_by_verification_token(db, token)
    if not user:
        raise ValidationError("Invalid verification link.")

    if user.is_verified:
        return user  # idempotent

    now = datetime.now(timezone.utc)
    expires = user.verification_token_expires_at
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if expires is None or expires < now:
        raise ValidationError(
            "This verification link has expired. Please request a new one."
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires_at = None
    db.flush()

    logger.info("Email verified", extra={"user_id": str(user.id)})
    return user


def resend_verification(db: Session, email: str) -> tuple["User", str]:
    """
    Issue a new verification token for an unverified account.
    Raises ValidationError if already verified.
    Always raises the same message to avoid email enumeration.
    """
    user = get_user_by_email(db, email)

    # Deliberately vague — don't reveal if email exists
    _generic_msg = "If that email is registered and unverified, a new link has been sent."

    if not user:
        raise ValidationError(_generic_msg)

    if user.is_verified:
        raise ValidationError(_generic_msg)

    token = _generate_verification_token(db, user)
    db.flush()

    logger.info("Verification token reissued", extra={"user_id": str(user.id)})
    return user, token


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if not user or not verify_password(password, user.password_hash):
        raise ValidationError("Invalid email or password.")
    if not user.is_active:
        raise ValidationError("Account is disabled. Contact support.")
    return user


def increment_uploads(db: Session, user_id: uuid.UUID) -> None:
    db.query(User).filter(User.id == user_id).update(
        {User.uploads_used: User.uploads_used + 1}
    )