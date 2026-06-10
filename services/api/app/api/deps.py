"""
FastAPI dependencies shared across routers.

Admin authentication (legacy)
------------------------------
``verify_admin_key`` reads the ``X-Admin-Key`` request header and compares it
to ``settings.ADMIN_API_KEY`` using a timing-safe comparison.  Any mismatch
raises ``HTTPException(403)``.

Teacher authentication (JWT)
-----------------------------
``get_current_user`` validates the Supabase-issued Bearer JWT and returns the
corresponding ``User`` row.  On first call the user is upserted so the local
``users`` table stays in sync with Supabase Auth without a separate webhook.

Usage::

    from app.api.deps import verify_admin_key, get_current_user

    # legacy admin endpoints
    router = APIRouter(dependencies=[Depends(verify_admin_key)])

    # teacher endpoints
    @router.get("/my-stuff")
    def my_stuff(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        ...

Database session
----------------
``get_db`` yields a SQLAlchemy ``Session`` for the request lifetime and
commits/rolls back automatically.
"""

from __future__ import annotations

import hmac
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserRole

_bearer = HTTPBearer()


def verify_admin_key(request: Request) -> None:
    """Dependency that enforces admin API key authentication.

    Reads the ``X-Admin-Key`` header and compares it to
    ``settings.ADMIN_API_KEY`` with a constant-time comparison to prevent
    timing attacks.

    Raises:
        HTTPException 403: Header is absent or the key does not match.
    """
    provided = request.headers.get("X-Admin-Key", "")
    expected = settings.ADMIN_API_KEY

    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin API key.",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate a Supabase JWT and return (or create) the local User row.

    Supabase issues HS256 JWTs signed with the project JWT secret.  The
    ``sub`` claim is the user's UUID; ``email`` carries their address.

    On the very first request from a new teacher account, this function
    upserts a User row so the local table stays in sync without requiring
    a Supabase webhook.

    Raises:
        HTTPException 401: Token is absent, expired, or has an invalid signature.
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id_str: str | None = payload.get("sub")
    email: str | None = payload.get("email")

    if not user_id_str or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = uuid.UUID(user_id_str)
    user = db.get(User, user_id)

    if user is None:
        user = User(id=user_id, email=email, role=UserRole.teacher)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.email != email:
        # Keep email in sync if the user changed it in Supabase.
        user.email = email
        db.commit()

    return user


__all__ = ["verify_admin_key", "get_current_user", "get_db"]
