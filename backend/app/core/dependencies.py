from typing import Annotated

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db


# ── Re-export DB dep ──────────────────────────────────────────────────────────

DBSession = Annotated[Session, Depends(get_db)]


# ── Auth deps ─────────────────────────────────────────────────────────────────

def _extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    return authorization.split(" ", 1)[1]


async def get_current_user_payload(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Validates the JWT and returns the raw payload.
    Raises UnauthorizedError on any failure.
    """
    token = _extract_token(authorization)
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise UnauthorizedError(f"Invalid or expired token: {exc}") from exc

    if payload.get("type") != "access":
        raise UnauthorizedError("Token is not an access token.")

    return payload


CurrentUser = Annotated[dict, Depends(get_current_user_payload)]


def require_role(*roles: str):
    """
    Factory that returns a dependency enforcing one of the given roles.

    Usage:
        @router.get("/admin/users", dependencies=[Depends(require_role("admin"))])
    """
    async def _guard(payload: CurrentUser) -> dict:
        if payload.get("role") not in roles:
            raise ForbiddenError()
        return payload

    return _guard


AdminOnly = Depends(require_role("admin"))