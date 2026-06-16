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
import json
import uuid
from functools import lru_cache
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User, UserRole

_bearer = HTTPBearer()
_JWKS_ALGORITHMS = {"ES256", "RS256"}
_DEFAULT_JWT_SECRET = "changeme-jwt-secret"


def _unauthorized(detail: str = "Invalid or expired token.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


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


@lru_cache(maxsize=8)
def _fetch_jwks(jwks_url: str) -> dict:
    """Fetch and cache a JSON Web Key Set from Supabase."""
    with urlopen(jwks_url, timeout=5) as response:
        return json.loads(response.read())


def _decode_with_jwks(token: str, jwks_url: str) -> dict:
    """Decode a Supabase JWT using the matching key from the JWKS endpoint."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _unauthorized() from exc

    kid = header.get("kid")
    header_alg = header.get("alg")
    if not kid or not header_alg:
        raise _unauthorized()

    try:
        jwks = _fetch_jwks(jwks_url)
    except (OSError, URLError, ValueError) as exc:
        raise _unauthorized() from exc

    key = next(
        (
            candidate
            for candidate in jwks.get("keys", [])
            if candidate.get("kid") == kid
        ),
        None,
    )
    if key is None:
        raise _unauthorized()

    key_alg = key.get("alg") or header_alg
    if header_alg != key_alg or key_alg not in _JWKS_ALGORITHMS:
        raise _unauthorized()

    try:
        return jwt.decode(
            token,
            key,
            algorithms=[key_alg],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise _unauthorized() from exc


def _decode_teacher_token(token: str) -> dict:
    """Decode a teacher access token using JWKS, with legacy HS256 fallback."""
    jwks_url = settings.supabase_jwks_url
    if jwks_url:
        try:
            return _decode_with_jwks(token, jwks_url)
        except HTTPException:
            # Keep the legacy fallback during rollout and local development.
            pass

    if settings.JWT_SECRET == _DEFAULT_JWT_SECRET:
        raise _unauthorized()

    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise _unauthorized() from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate a Supabase JWT and return (or create) the local User row.

    Supabase can issue JWTs signed by the current asymmetric signing-key system
    or the legacy HS256 JWT secret.  The ``sub`` claim is the user's UUID;
    ``email`` carries their address.

    On the very first request from a new teacher account, this function
    upserts a User row so the local table stays in sync without requiring
    a Supabase webhook.

    Raises:
        HTTPException 401: Token is absent, expired, or has an invalid signature.
    """
    token = credentials.credentials
    payload = _decode_teacher_token(token)

    user_id_str: str | None = payload.get("sub")
    email: str | None = payload.get("email")

    if not user_id_str or not email:
        raise _unauthorized("Token missing required claims.")

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
