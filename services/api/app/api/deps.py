"""
FastAPI dependencies shared across routers.

Admin authentication
--------------------
``verify_admin_key`` reads the ``X-Admin-Key`` request header and compares it
to ``settings.ADMIN_API_KEY`` using a timing-safe comparison.  Any mismatch
raises ``HTTPException(403)``.

Usage::

    from app.api.deps import verify_admin_key

    router = APIRouter(dependencies=[Depends(verify_admin_key)])

Database session
----------------
``get_db`` yields a SQLAlchemy ``Session`` for the request lifetime and
commits/rolls back automatically.
"""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db


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

    # hmac.compare_digest requires str or bytes of the same type.
    # Always compare — even when the header is missing — to avoid
    # leaking timing information about key length.
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin API key.",
        )


# Re-export get_db so callers can import everything from deps.
__all__ = ["verify_admin_key", "get_db"]
