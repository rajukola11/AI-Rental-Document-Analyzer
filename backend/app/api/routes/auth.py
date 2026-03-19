import uuid

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.dependencies import DBSession, CurrentUser
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.schemas.user import UserRegister, UserLogin, UserResponse, TokenResponse
from app.services.user_service import authenticate_user, create_user, get_user_by_id

router = APIRouter()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
def register(payload: UserRegister, db: DBSession):
    user = create_user(
        db=db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
    )
    return user


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
def login(payload: UserLogin, db: DBSession):
    user = authenticate_user(db, payload.email, payload.password)

    access_token = create_access_token(subject=str(user.id), role=user.role)
    refresh_token = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Get a new access token using a refresh token",
)
def refresh_token(db: DBSession, authorization: str = None):
    from fastapi import Header
    from jose import JWTError

    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")

    token = authorization.split(" ", 1)[1]

    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise UnauthorizedError(f"Invalid or expired refresh token: {exc}")

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Token is not a refresh token.")

    user_id = payload.get("sub")
    user = get_user_by_id(db, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise UnauthorizedError("User not found or inactive.")

    access_token = create_access_token(subject=str(user.id), role=user.role)
    new_refresh = create_refresh_token(subject=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
def get_me(payload: CurrentUser, db: DBSession):
    user_id = payload.get("sub")
    user = get_user_by_id(db, uuid.UUID(user_id))
    if not user:
        raise UnauthorizedError("User not found.")
    return user