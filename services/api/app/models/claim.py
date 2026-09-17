"""Per-student claim codes for student access tokens.

A claim code is a teacher-issued shared secret, one per (class roll,
roster name).  A student redeems it on /join for a signed student token;
grade-reading endpoints then require that token (see app.api.student_auth).

Codes are stored as teacher-readable plaintext deliberately: they behave
like join codes, not passwords — the teacher must re-view them to reprint
handouts, the threat model is classmates guessing, and a database
compromise exposes the graded work itself anyway.

Regeneration deletes the row and inserts a fresh one.  The row id doubles
as the token's ``jti`` and is re-checked on every request, so regenerating
a code instantly signs out every device holding the old token.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# No I/L/O/0/1 — codes are read from paper handouts.
CLAIM_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CLAIM_CODE_LENGTH = 8


def generate_claim_code() -> str:
    """Return a short access code safe to read aloud or copy from paper."""
    return "".join(secrets.choice(CLAIM_CODE_ALPHABET) for _ in range(CLAIM_CODE_LENGTH))


class StudentClaimCode(Base):
    """One student's access code on one class roll."""

    __tablename__ = "student_claim_codes"
    __table_args__ = (
        UniqueConstraint("class_roll_id", "student_name", name="uq_claim_roll_student"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Doubles as the student token's jti claim",
    )
    class_roll_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("class_rolls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Canonical roster spelling at issue time",
    )
    code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,
        default=generate_claim_code,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Teacher-facing pickup signal; codes are multi-use",
    )
    claim_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    class_roll = relationship("ClassRoll")

    def __repr__(self) -> str:
        return (
            f"<StudentClaimCode roll={self.class_roll_id} "
            f"student={self.student_name!r}>"
        )
