"""
Student-tier endpoints authenticated by the claim-code token alone.

``GET /student/dashboard`` — the live progress dashboard. Unlike the
grace-period endpoints in public.py, this one ALWAYS requires a valid token,
even while ``STUDENT_TOKEN_ENFORCED`` is off: there is no roll + name in the
request to fall back on, so without a token there is no way to know whose
grades to show.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.student_auth import STUDENT_TOKEN_HEADER, StudentAuth, _deny, get_student_auth
from app.core.config import settings
from app.core.ratelimit import limiter
from app.models.user import ClassRoll, User
from app.repositories.roll_repo import RollRepository
from app.services.course_plan import plan_for_owner_email
from app.services.dashboard import build_dashboard
from app.services.dashboard_sources import gather_remote, scenario_records
from app.services.names import names_equivalent

router = APIRouter(prefix="/student", tags=["student"])


@router.get(
    "/dashboard",
    summary="The signed-in student's live progress dashboard",
    dependencies=[Depends(limiter.limit("dashboard", 30, 60))],
)
def student_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    auth: StudentAuth = Depends(get_student_auth),
) -> dict:
    if auth.status != "ok" or auth.roll_id is None:
        raise _deny(auth)

    roll = db.get(ClassRoll, auth.roll_id)
    if roll is None:  # roll deleted after the claim
        raise _deny(StudentAuth(status="revoked"))
    owner = db.get(User, roll.owner_id)
    student_name = auth.name or ""

    # Every roll of this teacher that lists the student (a student can sit
    # on more than one, e.g. after a schedule change).
    rolls = [
        r for r in RollRepository(db).list_for_owner(roll.owner_id)
        if any(names_equivalent(n, student_name) for n in r.student_names)
    ] or [roll]

    student = {
        "name": student_name,
        "roll_name": roll.name,
        "join_code": roll.join_code,
    }
    plan = plan_for_owner_email(owner.email if owner else None)
    if plan is None:
        return {"student": student, "plan_available": False, "sources": {}, "dashboard": None}

    as_of = datetime.now(ZoneInfo(settings.DASHBOARD_TIMEZONE)).date()
    token = request.headers.get(STUDENT_TOKEN_HEADER, "")
    scen = scenario_records(db, plan, rolls, student_name)
    essay, video = gather_remote(plan, token, student_name)

    records = {**video.records, **scen.records, **essay.records}
    return {
        "student": student,
        "plan_available": True,
        "sources": {"scenarios": scen.status, "essays": essay.status, "videos": video.status},
        "dashboard": build_dashboard(plan, records, as_of),
    }
