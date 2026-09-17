"""Student-token authentication for public (student-facing) endpoints.

The token arrives in the ``X-Student-Token`` header — a custom header so
it never collides with the teacher ``Authorization: Bearer`` flow.

``get_student_auth`` is deliberately optional and never raises: routes
always run it, then call one of the ``require_*`` helpers *after* loading
the record, because the access rule depends on the record (anonymous
plays stay tokenless forever).

Access ladder (both helpers):

1. Record is not tied to a class roll -> allow (anonymous play).
2. Valid token matching the record's roll + student -> allow.
3. ``STUDENT_TOKEN_ENFORCED`` is False -> allow (grace period: a missing
   or stale token never blocks anyone before codes are distributed).
4. Otherwise 401/403 with a structured ``detail.code`` the frontends
   branch on:

   - 401 ``student_token_required``  (no token)
   - 401 ``student_token_invalid``   (bad signature / expired / bad iss)
   - 401 ``student_token_revoked``   (claim row regenerated or removed)
   - 403 ``student_token_mismatch``  (valid token, different student/roll)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.claim import StudentClaimCode
from app.models.play import Play
from app.services.names import names_equivalent
from app.services.student_tokens import decode_student_token

STUDENT_TOKEN_HEADER = "X-Student-Token"


@dataclass
class StudentAuth:
    """Outcome of reading (not enforcing) the student token."""

    status: Literal["ok", "missing", "invalid", "revoked"]
    roll_id: uuid.UUID | None = None
    name: str | None = None
    owner_id: uuid.UUID | None = None
    claim: StudentClaimCode | None = None


def get_student_auth(
    request: Request, db: Session = Depends(get_db)
) -> StudentAuth:
    """Decode and row-check the student token; never raises."""
    token = request.headers.get(STUDENT_TOKEN_HEADER, "").strip()
    if not token:
        return StudentAuth(status="missing")
    claims = decode_student_token(token)
    if claims is None:
        return StudentAuth(status="invalid")
    try:
        jti = uuid.UUID(claims["jti"])
        roll_id = uuid.UUID(claims["roll_id"])
        owner_id = uuid.UUID(claims["owner"]) if claims.get("owner") else None
    except (KeyError, ValueError):
        return StudentAuth(status="invalid")
    # The row check is the revocation mechanism: regenerating a code
    # deletes the row, which invalidates every token minted from it.
    claim = db.get(StudentClaimCode, jti)
    if (
        claim is None
        or claim.class_roll_id != roll_id
        or not names_equivalent(claim.student_name, claims.get("name"))
    ):
        return StudentAuth(status="revoked")
    return StudentAuth(
        status="ok",
        roll_id=roll_id,
        name=claim.student_name,
        owner_id=owner_id,
        claim=claim,
    )


def _deny(auth: StudentAuth) -> HTTPException:
    if auth.status == "ok":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "student_token_mismatch",
                "message": "This work belongs to a different student.",
            },
        )
    code = {
        "missing": "student_token_required",
        "invalid": "student_token_invalid",
        "revoked": "student_token_revoked",
    }[auth.status]
    messages = {
        "student_token_required": "Enter your access code to continue.",
        "student_token_invalid": "Your access has expired — enter your access code again.",
        "student_token_revoked": "Your access code was reset — ask your teacher for the new one.",
    }
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": messages[code]},
    )


def _token_matches(
    auth: StudentAuth, roll_id: uuid.UUID, student_name: str | None
) -> bool:
    return (
        auth.status == "ok"
        and auth.roll_id == roll_id
        and names_equivalent(auth.name, student_name)
    )


def require_play_access(play: Play, auth: StudentAuth) -> None:
    """Enforce the access ladder for a play-scoped route."""
    if play.class_roll_id is None:
        return  # anonymous plays stay tokenless forever
    if _token_matches(auth, play.class_roll_id, play.learner_label):
        return
    if not settings.STUDENT_TOKEN_ENFORCED:
        return
    raise _deny(auth)


def require_roll_access(
    roll_id: uuid.UUID, student_name: str, auth: StudentAuth
) -> None:
    """Enforce the access ladder for a roll+name-scoped route."""
    if _token_matches(auth, roll_id, student_name):
        return
    if not settings.STUDENT_TOKEN_ENFORCED:
        return
    raise _deny(auth)
