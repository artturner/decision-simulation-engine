"""Link an essay-grader class to a roll here, so it can issue access codes.

Access codes are issued only by this app (``student_claim_codes`` hangs
off ``class_rolls``), and the essay API honors a token when its name and
roll owner match. An essays-only class therefore needs a roll here to
hold its codes. The essays dashboard calls this with its class roster:

- A roll already linked to that essay class is reused.
- Otherwise an unlinked roll of the teacher's whose roster covers most of
  the essay roster is linked — the same class, set up in both apps, keeps
  the codes students already have.
- Otherwise a mirror roll is created. A mirror's roster follows the essay
  class on every call (removed names lose their codes); a linked roll the
  teacher set up here only gains missing names, never loses any, since
  its roster is also the scenarios gradebook's.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import StudentClaimCode
from app.models.user import ClassRoll
from app.repositories.claim_repo import ClaimRepository
from app.repositories.roll_repo import RollRepository
from app.services.names import normalize_student_name, student_name_key

# Share of the essay roster an existing roll must contain to be linked.
LINK_MIN_OVERLAP = 0.8


def _keys(names: list[str]) -> set[str]:
    return {k for k in map(student_name_key, names) if k}


def _match_existing(
    candidates: list[ClassRoll], name: str, student_names: list[str]
) -> ClassRoll | None:
    keys = _keys(student_names)
    if not keys:
        return None
    target = normalize_student_name(name).casefold()

    def score(roll: ClassRoll) -> tuple[int, bool]:
        overlap = len(keys & _keys(roll.student_names))
        return overlap, normalize_student_name(roll.name).casefold() == target

    best = max(candidates, key=score, default=None)
    if best is None or score(best)[0] < LINK_MIN_OVERLAP * len(keys):
        return None
    return best


def link_essay_roll(
    db: Session,
    owner_id: uuid.UUID,
    essay_roll_id: uuid.UUID,
    name: str,
    student_names: list[str],
) -> ClassRoll:
    repo = RollRepository(db)
    roll = db.scalars(
        select(ClassRoll).where(ClassRoll.essay_roll_id == essay_roll_id)
    ).first()
    if roll is not None and roll.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That essay class is linked to another teacher's roll.",
        )
    if roll is None:
        unlinked = [r for r in repo.list_for_owner(owner_id) if r.essay_roll_id is None]
        roll = _match_existing(unlinked, name, student_names)
        if roll is None:
            roll = repo.create(owner_id, name, list(student_names))
            roll.mirrors_essay_roll = True
        roll.essay_roll_id = essay_roll_id

    if roll.mirrors_essay_roll:
        repo.update(roll, name=name, student_names=list(student_names))
        ClaimRepository(db).sync_with_roster(roll)
    else:
        have = _keys(roll.student_names)
        missing = [
            n for n in student_names
            if student_name_key(n) and student_name_key(n) not in have
        ]
        if missing:
            repo.update(roll, student_names=[*roll.student_names, *missing])
    db.flush()
    return roll


def codes_for_essay_roster(
    db: Session, roll: ClassRoll, student_names: list[str]
) -> list[StudentClaimCode]:
    """The roll's codes for the essay roster's students, in essay order."""
    by_key = {
        student_name_key(c.student_name): c
        for c in ClaimRepository(db).ensure_for_roll(roll)
    }
    ordered_keys = dict.fromkeys(k for k in map(student_name_key, student_names) if k)
    return [by_key[k] for k in ordered_keys if k in by_key]
