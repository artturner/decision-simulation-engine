"""
Student dashboard data sources.

Turns what each app knows about one student into
:class:`~app.services.dashboard.ItemRecord` values keyed by course-plan item:

* scenarios — this API's own database (same best-attempt rule as the roll
  gradebook, so the number matches the D2L export);
* essays — the essay API's ``/public/student/progress``, forwarding the
  student's own token (the essay API scopes by token owner + name);
* videos — the video-quiz app's ``/api/internal/student-progress``, guarded by
  a shared key (that app is single-teacher and has no student tokens).

Every upstream is optional and failure-isolated: a timeout or error marks
that source unavailable and the dashboard still renders the rest.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.play import Play, Reflection
from app.models.scenario import Scenario, ScenarioVersion
from app.models.user import ClassRoll
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.services.course_plan import CoursePlan, norm_title
from app.services.dashboard import (
    ALMOST,
    DONE,
    IN_PROGRESS,
    NOT_STARTED,
    PENDING,
    ItemRecord,
)
from app.services.names import names_equivalent

log = logging.getLogger(__name__)


@dataclass
class SourceResult:
    records: dict[str, ItemRecord] = field(default_factory=dict)  # plan key -> record
    status: str = "ok"  # ok | unavailable | not_configured


def _local_naive(value: datetime | str | None) -> datetime | None:
    """Convert an aware timestamp to naive local (dashboard timezone) time."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(settings.DASHBOARD_TIMEZONE)).replace(tzinfo=None)


def _swap_origin(url: str | None, base: str) -> str | None:
    """Same path and query on another origin (the unblocked fallback)."""
    if not url or not base:
        return None
    u, b = urlsplit(url), urlsplit(base)
    if not u.netloc or u.netloc == b.netloc:
        return None
    return urlunsplit((b.scheme, b.netloc, u.path, u.query, u.fragment))


def _plan_index(plan: CoursePlan, source: str) -> dict[str, str]:
    """normalized app title -> plan key, for one source."""
    return {norm_title(it.match_title): it.key for it in plan.items if it.source == source}


# ---------------------------------------------------------------------------
# Scenarios (local DB)
# ---------------------------------------------------------------------------


def _best_attempt(reflection: Reflection):
    best = None
    for a in reflection.attempts or []:
        if best is None or (a.grade_total, a.graded_at) > (best.grade_total, best.graded_at):
            best = a
    return best


def _play_grade(play: Play) -> int:
    """Best-attempt score for a play; -1 when ungraded (as the gradebook)."""
    r = play.reflection
    if r is not None:
        best = _best_attempt(r)
        if best is not None and best.grade_total is not None:
            return best.grade_total
        if r.grade_total is not None:
            return r.grade_total
    return -1


def scenario_records(
    db: Session,
    plan: CoursePlan,
    rolls: list[ClassRoll],
    student_name: str,
) -> SourceResult:
    index = _plan_index(plan, "scenario")
    out = SourceResult()
    if not rolls:
        return out
    roll_ids = [r.id for r in rolls]
    join_code_of = {r.id: r.join_code for r in rolls}

    # Visible scenarios on the student's rolls, by plan key.
    roll_repo, scen_repo = RollRepository(db), ScenarioRepository(db)
    visible: dict[str, tuple[Scenario, uuid.UUID]] = {}  # key -> (scenario, roll)
    scenario_key: dict[uuid.UUID, str] = {}
    for roll in rolls:
        for a in roll_repo.visible_assignments_for_roll(roll.id):
            sc = db.get(Scenario, a.scenario_id)
            if sc is None:
                continue
            version = scen_repo.get_published_version(sc.slug)
            meta_title = ((version.scenario_json or {}).get("metadata") or {}).get("title") if version else None
            key = index.get(norm_title(sc.title)) or (meta_title and index.get(norm_title(meta_title)))
            if key:
                visible.setdefault(key, (sc, roll.id))
                scenario_key[sc.id] = key

    # Every class play by this student on those rolls (any version).
    stmt = (
        select(Play)
        .where(Play.class_roll_id.in_(roll_ids))
        .options(
            selectinload(Play.reflection).selectinload(Reflection.attempts),
            selectinload(Play.scenario_version),
        )
    )
    plays_by_key: dict[str, list[Play]] = defaultdict(list)
    for play in db.scalars(stmt):
        if not names_equivalent(play.learner_label, student_name):
            continue
        sv: ScenarioVersion = play.scenario_version
        key = scenario_key.get(sv.scenario_id)
        if key is None:
            sc = db.get(Scenario, sv.scenario_id)
            key = index.get(norm_title(sc.title)) if sc else None
        if key:
            plays_by_key[key].append(play)

    max_attempts = settings.AI_GRADER_MAX_ATTEMPTS
    for key in set(visible) | set(plays_by_key):
        sc_roll = visible.get(key)
        slug = sc_roll[0].slug if sc_roll else None
        plays = plays_by_key.get(key, [])
        completed = [p for p in plays if p.completed]
        rec = ItemRecord(available=sc_roll is not None)
        if sc_roll:
            rec.link = f"/join?code={join_code_of[sc_roll[1]]}"

        best = None
        for p in completed:
            if best is None:
                best = p
                continue
            pg, bg = _play_grade(p), _play_grade(best)
            p_at = p.ended_at or p.started_at
            b_at = best.ended_at or best.started_at
            if pg > bg or (pg == bg and (b_at is None or (p_at is not None and p_at >= b_at))):
                best = p

        if best is not None and _play_grade(best) >= 0:
            rec.state = DONE
            rec.score = float(_play_grade(best))
            graded_times = [
                p.reflection.submitted_at or p.ended_at
                for p in completed
                if p.reflection is not None and _play_grade(p) >= 0
            ]
            rec.completed_at = _local_naive(min((t for t in graded_times if t), default=None))
            r = best.reflection
            ba = _best_attempt(r)
            breakdown = (ba.grade_breakdown if ba else r.grade_breakdown) or {}
            dims = {
                k: {"level": d.get("level"), "points": d.get("points"),
                    "max_points": d.get("max_points"), "evidence": d.get("evidence")}
                for k, d in (breakdown.get("dimensions") or {}).items()
            }
            first = min(r.attempts or [], key=lambda a: a.attempt_number, default=None)
            rec.detail = {
                "dimensions": dims,
                "feedback": (ba.feedback if ba else r.feedback),
                "outcome": best.outcome,
                "attempts_used": r.grade_attempts or 0,
                "improved_by_revision": bool(
                    first and ba and ba.attempt_number != first.attempt_number
                    and (ba.grade_total or 0) > (first.grade_total or 0)
                ),
            }
            used = r.grade_attempts or 0
            if not r.accepted and used < max_attempts and slug:
                rec.can_revise = True
                rec.revisions_left = max_attempts - used
                rec.link = f"/{slug}/complete/{best.id}"
        elif any(p.reflection is not None and p.reflection.submitted_at for p in completed):
            rec.state = PENDING
            rec.completed_at = _local_naive(min(
                p.reflection.submitted_at for p in completed
                if p.reflection is not None and p.reflection.submitted_at
            ))
        elif completed:
            rec.state = ALMOST
            rec.almost_label = "Reflection not submitted"
            last = max(completed, key=lambda p: p.ended_at or p.started_at)
            if slug:
                rec.link = f"/{slug}/complete/{last.id}"
        elif plays:
            rec.state = IN_PROGRESS
            last = max(plays, key=lambda p: p.started_at)
            if slug:
                rec.link = f"/{slug}/play/{last.id}"
        else:
            rec.state = NOT_STARTED
        out.records[key] = rec
    return out


# ---------------------------------------------------------------------------
# Essays (forward the student's token)
# ---------------------------------------------------------------------------


def _get(url: str, headers: dict[str, str], params: dict | None = None) -> Any:
    with httpx.Client(timeout=settings.DASHBOARD_UPSTREAM_TIMEOUT) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


def essay_records(plan: CoursePlan, token: str) -> SourceResult:
    if not settings.ESSAY_API_BASE:
        return SourceResult(status="not_configured")
    try:
        data = _get(
            f"{settings.ESSAY_API_BASE.rstrip('/')}/api/v1/public/student/progress",
            {"X-Student-Token": token},
        )
    except Exception as exc:  # noqa: BLE001 — any upstream failure degrades
        log.warning("dashboard: essay source unavailable: %s", exc)
        return SourceResult(status="unavailable")
    return essay_records_from(plan, data)


def essay_records_from(plan: CoursePlan, data: dict) -> SourceResult:
    index = _plan_index(plan, "essay")
    out = SourceResult()
    for a in data.get("assignments") or []:
        key = index.get(norm_title(a.get("title", "")))
        if not key:
            continue
        link = f"{settings.ESSAY_WEB_BASE.rstrip('/')}/join?code={a.get('join_code', '')}"
        rec = ItemRecord(available=True, link=link,
                         alt_link=_swap_origin(link, settings.ESSAY_WEB_FALLBACK_BASE))
        status = a.get("status")
        score, max_total = a.get("score"), a.get("max_total") or 0
        if score is not None and max_total:
            rec.state = DONE
            rec.score = round(100.0 * float(score) / float(max_total), 2)
            rec.completed_at = _local_naive(a.get("first_graded_at") or a.get("graded_at"))
            attempts, max_att = a.get("attempts") or 0, a.get("max_attempts") or 0
            if status == "graded" and not a.get("overridden") and attempts < max_att:
                rec.can_revise = True
                rec.revisions_left = max_att - attempts
        elif status in ("graded", "accepted"):
            rec.state = PENDING
        elif status == "draft":
            rec.state = ALMOST
            rec.almost_label = "Draft not submitted for grading"
        else:
            rec.state = NOT_STARTED
        rec.detail = {
            "dimensions": [
                {k: d.get(k) for k in ("key", "title", "level", "points", "max_points",
                                       "evidence", "next_anchor")}
                for d in a.get("dimensions") or []
            ],
            "feedback": a.get("feedback"),
            "teacher_comment": a.get("teacher_comment"),
            "word_count": a.get("word_count"),
            "on_time": a.get("submitted_on_time"),
        }
        prev = out.records.get(key)
        if prev is None or (rec.score or -1) > (prev.score or -1):
            out.records[key] = rec
    return out


# ---------------------------------------------------------------------------
# Videos (shared internal key)
# ---------------------------------------------------------------------------


def video_grade(status: str, first_try: int, total_questions: int) -> float | None:
    """75 for completing + up to 25 for first-try accuracy (d2l_prep.py)."""
    if status != "completed":
        return None
    if total_questions <= 0:
        return 75.0
    return 75 + 25 * first_try / total_questions


def video_records(plan: CoursePlan, student_name: str) -> SourceResult:
    if not (settings.VIDEO_API_BASE and settings.VIDEO_INTERNAL_KEY):
        return SourceResult(status="not_configured")
    try:
        data = _get(
            f"{settings.VIDEO_API_BASE.rstrip('/')}/api/internal/student-progress",
            {"X-Internal-Key": settings.VIDEO_INTERNAL_KEY},
            {"name": student_name},
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("dashboard: video source unavailable: %s", exc)
        return SourceResult(status="unavailable")
    return video_records_from(plan, data)


def video_records_from(plan: CoursePlan, data: dict) -> SourceResult:
    index = _plan_index(plan, "video")
    out = SourceResult()
    for lesson in data.get("lessons") or []:
        key = index.get(norm_title(lesson.get("video_title") or "")) or index.get(
            norm_title(lesson.get("assignment_title") or ""))
        if not key:
            continue
        link = lesson.get("link")
        tq = int(lesson.get("total_questions") or 0)
        ftc = int(lesson.get("first_try_correct") or 0)
        status = lesson.get("status") or "not_started"
        dur = lesson.get("duration_seconds")
        rec = ItemRecord(
            available=True, link=link,
            alt_link=_swap_origin(link, settings.VIDEO_WEB_FALLBACK_BASE),
            effort_minutes=int(dur / 60) + 3 if dur else None,
        )
        rec.score = video_grade(status, ftc, tq)
        if rec.score is not None:
            rec.state = DONE
            rec.completed_at = _local_naive(lesson.get("completed_at"))
        elif status == "in_progress":
            rec.state = IN_PROGRESS
        rec.detail = {
            "total_questions": tq,
            "first_try_correct": ftc if rec.score is not None else None,
            "questions_answered": lesson.get("questions_answered"),
            "missed": [
                {"prompt": m.get("prompt")} for m in (lesson.get("missed") or []) if m.get("prompt")
            ] if rec.score is not None else [],
        }
        prev = out.records.get(key)
        if prev is None or (rec.score or -1) > (prev.score or -1):
            out.records[key] = rec
    return out


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------


def gather_remote(plan: CoursePlan, token: str, student_name: str) -> tuple[SourceResult, SourceResult]:
    """Fetch essays and videos concurrently."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_essay = pool.submit(essay_records, plan, token)
        f_video = pool.submit(video_records, plan, student_name)
        return f_essay.result(), f_video.result()
