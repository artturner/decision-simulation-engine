"""Data access for per-student claim codes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import StudentClaimCode, generate_claim_code
from app.models.user import ClassRoll
from app.services.names import normalize_student_name, student_name_key


class ClaimRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_code(self, code: str) -> StudentClaimCode | None:
        normalized = "".join(code.split()).replace("-", "").upper()
        stmt = select(StudentClaimCode).where(StudentClaimCode.code == normalized)
        return self._db.scalars(stmt).first()

    def list_for_roll(self, roll_id: uuid.UUID) -> list[StudentClaimCode]:
        stmt = select(StudentClaimCode).where(
            StudentClaimCode.class_roll_id == roll_id
        )
        return list(self._db.scalars(stmt))

    def _create(self, roll_id: uuid.UUID, student_name: str) -> StudentClaimCode:
        for _ in range(10):
            code = generate_claim_code()
            if self.get_by_code(code) is not None:
                continue
            claim = StudentClaimCode(
                class_roll_id=roll_id,
                student_name=normalize_student_name(student_name),
                code=code,
            )
            self._db.add(claim)
            self._db.flush()
            return claim
        raise RuntimeError("Could not generate a unique claim code")

    def ensure_for_roll(self, roll: ClassRoll) -> list[StudentClaimCode]:
        """Return the roll's claim rows in roster order, creating missing ones.

        Lazy generation: a code exists only once a teacher has viewed it.
        Duplicate roster names (scenarios rolls have no dupe guard) share
        one row, keyed by ``student_name_key`` — the same one-identity
        limitation the gradebook already has.
        """
        existing = {student_name_key(c.student_name): c for c in self.list_for_roll(roll.id)}
        ordered: list[StudentClaimCode] = []
        seen: set[str] = set()
        for name in roll.student_names:
            key = student_name_key(name)
            if not key or key in seen:
                continue
            seen.add(key)
            claim = existing.get(key)
            if claim is None:
                claim = self._create(roll.id, name)
            ordered.append(claim)
        return ordered

    def regenerate(
        self, roll: ClassRoll, student_name: str | None
    ) -> list[StudentClaimCode]:
        """Delete + recreate codes (one student, or the whole roll).

        A fresh row means a fresh id, so every token minted from the old
        code fails the per-request row check immediately.
        """
        target_key = student_name_key(student_name) if student_name else None
        for claim in self.list_for_roll(roll.id):
            if target_key is None or student_name_key(claim.student_name) == target_key:
                self._db.delete(claim)
        self._db.flush()
        return self.ensure_for_roll(roll)

    def record_claim(self, claim: StudentClaimCode) -> None:
        claim.last_claimed_at = datetime.now(timezone.utc)
        claim.claim_count = (claim.claim_count or 0) + 1
        self._db.flush()

    def sync_with_roster(self, roll: ClassRoll) -> None:
        """Reconcile claim rows after a roster edit.

        A row whose name survives (same ``student_name_key``) is kept with
        its spelling updated to the new roster form, so a formatting fix
        never signs a student out.  Rows for removed names are deleted
        (their tokens then fail the row check).  New names are created
        lazily on the next codes fetch, not here.
        """
        roster_by_key = {}
        for name in roll.student_names:
            key = student_name_key(name)
            if key and key not in roster_by_key:
                roster_by_key[key] = normalize_student_name(name)
        for claim in self.list_for_roll(roll.id):
            new_spelling = roster_by_key.get(student_name_key(claim.student_name))
            if new_spelling is None:
                self._db.delete(claim)
            elif claim.student_name != new_spelling:
                claim.student_name = new_spelling
        self._db.flush()
