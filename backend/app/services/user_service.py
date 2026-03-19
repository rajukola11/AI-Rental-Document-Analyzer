import uuid
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.core.exceptions import NotFoundError, ValidationError
from app.models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, password: str, full_name: str | None = None) -> User:
    if get_user_by_email(db, email):
        raise ValidationError("An account with this email already exists.")

    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        full_name=full_name,
        role="user",
    )
    db.add(user)
    db.flush()  # get ID without committing — session.py commits on success
    return user


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