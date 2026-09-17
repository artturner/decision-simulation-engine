"""Issue and decode student access tokens.

Students never touch Supabase: these are in-house HS256 JWTs signed with
``STUDENT_TOKEN_SECRET``, a secret shared verbatim with the essay-grader
API so one claimed code works across both apps.  The scenarios API also
re-checks the claim row (``jti``) on every request — that row check, not
expiry, is the revocation mechanism here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.core.config import settings
from app.models.claim import StudentClaimCode


def student_tokens_configured() -> bool:
    """True when a signing secret is set (claiming enabled)."""
    return bool(settings.STUDENT_TOKEN_SECRET)


def issue_student_token(
    claim: StudentClaimCode, owner_id: uuid.UUID
) -> tuple[str, datetime]:
    """Return ``(token, expires_at)`` for a redeemed claim code.

    ``owner`` is the roll owner's Supabase UUID — the essay API scopes its
    name matching to this teacher, since it cannot see our claim rows.
    """
    if not student_tokens_configured():
        raise RuntimeError(
            "STUDENT_TOKEN_SECRET is not configured; refusing to issue student tokens."
        )
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.STUDENT_TOKEN_TTL_DAYS)
    token = jwt.encode(
        {
            "jti": str(claim.id),
            "roll_id": str(claim.class_roll_id),
            "name": claim.student_name,
            "owner": str(owner_id),
            "iss": settings.STUDENT_TOKEN_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        },
        settings.STUDENT_TOKEN_SECRET,
        algorithm="HS256",
    )
    return token, expires_at


def decode_student_token(token: str) -> dict | None:
    """Return the verified claims dict, or None for any invalid token."""
    if not student_tokens_configured():
        return None
    try:
        claims = jwt.decode(
            token,
            settings.STUDENT_TOKEN_SECRET,
            algorithms=["HS256"],
            issuer=settings.STUDENT_TOKEN_ISSUER,
        )
    except JWTError:
        return None
    if not claims.get("jti") or not claims.get("name"):
        return None
    return claims
