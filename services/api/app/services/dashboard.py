"""
Student dashboard engine — pure computation, no I/O.

Takes a :class:`~app.services.course_plan.CoursePlan`, the student's
per-item records gathered from the three apps, and a date, and produces the
dashboard payload: weighted grade, pace, the checklist, next-best moves,
stats, tips, and the motivational layer (XP, streaks, badges).

Grade and pace math deliberately mirror tools/unit-reports/student_report.py
(the FERPA counselor report) so a student never sees a different number than
the one their counselor is handed:

* grade = syllabus-weighted mean per type, where every past-due item with no
  grade counts as 0 ("submitted only" ignores missing items);
* pace = 0 missing → On track (Ahead with N+ items done before their dates),
  1..M missing → Slightly behind, more → Behind.

Self-referential only by design: nothing here compares a student to
classmates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from app.services.course_plan import CoursePlan, PlanItem

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

# Normalized per-item states across apps.
NOT_STARTED = "not_started"
IN_PROGRESS = "in_progress"
ALMOST = "almost"  # one step left: reflection unsubmitted / essay draft
PENDING = "pending_grade"  # turned in, no grade yet
DONE = "done"  # has a grade


@dataclass
class ItemRecord:
    """What one app knows about one plan item for this student."""

    state: str = NOT_STARTED
    score: float | None = None  # percent 0..100, the gradebook grade
    completed_at: datetime | None = None
    link: str | None = None
    alt_link: str | None = None  # same destination on an unblocked domain
    available: bool = False  # assigned & visible in the app right now
    almost_label: str | None = None  # e.g. "Reflection not submitted"
    can_revise: bool = False
    revisions_left: int | None = None
    effort_minutes: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)


DEFAULT_EXPECTED = 85.0
EFFORT = {"video": 12, "scenario": 25, "frq": 50}
ALMOST_EFFORT = {"video": 6, "scenario": 10, "frq": 25}
REVISE_EFFORT = {"scenario": 15, "frq": 30}
REVISE_GAIN = 10.0  # assumed points gained on a revision (capped at 100)
REVISE_BELOW = {"scenario": 80.0, "frq": 85.0}

XP_BASE = {"video": 100, "scenario": 250, "frq": 500}
XP_EARLY_BONUS = 0.20
LEVELS = (
    (0, "Bystander"),
    (500, "Citizen"),
    (1200, "Voter"),
    (2200, "Organizer"),
    (3500, "Delegate"),
    (5000, "Representative"),
    (6800, "Senator"),
    (8800, "Justice"),
    (11000, "Founder"),
)

REFLECTION_DIM_TIPS = {
    "engagement": "Name the specific choice you made and the situation that pushed you toward it.",
    "reasoning": "Give the why: weigh the tradeoff you faced and say what you gave up by choosing it.",
    "insight": "Connect your choice to a bigger idea from the chapter, or say what you'd do differently next time.",
}
LEVEL_RANK = {"low_effort": 0, "minimal": 1, "developing": 2, "solid": 3, "full": 4}


def _round(v: float | None, n: int = 1) -> float | None:
    return None if v is None else round(v, n)


# ---------------------------------------------------------------------------
# Grade math (mirrors student_report.analyze)
# ---------------------------------------------------------------------------


def _is_missing(item: PlanItem, rec: ItemRecord, as_of: date) -> bool:
    return rec.score is None and rec.state != PENDING and item.target < as_of


def compute_grade(
    plan: CoursePlan,
    records: dict[str, ItemRecord],
    as_of: date,
    overrides: dict[str, float] | None = None,
) -> tuple[float | None, float | None, dict[str, dict]]:
    """(grade with missing=0, grade on submitted only, per-type stats)."""
    overrides = overrides or {}
    by_type: dict[str, dict] = {}
    for typ in plan.weights:
        graded: list[float] = []
        counted: list[float] = []
        total = due = missing = 0
        for item in plan.items:
            if item.type != typ:
                continue
            total += 1
            rec = records.get(item.key) or ItemRecord()
            score = overrides.get(item.key, rec.score)
            if item.target < as_of:
                due += 1
            if score is not None:
                graded.append(score)
                counted.append(score)
            elif rec.state != PENDING and item.target < as_of:
                missing += 1
                counted.append(0.0)
        by_type[typ] = {
            "total": total,
            "done": len(graded),
            "due": due,
            "missing": missing,
            "avg_submitted": sum(graded) / len(graded) if graded else None,
            "avg_counted": sum(counted) / len(counted) if counted else None,
        }

    def weighted(key: str) -> float | None:
        parts = [(plan.weights[t], v[key]) for t, v in by_type.items() if v[key] is not None]
        wsum = sum(w for w, _ in parts)
        return sum(w * a for w, a in parts) / wsum if wsum else None

    return weighted("avg_counted"), weighted("avg_submitted"), by_type


def letter(pct: float | None) -> str | None:
    if pct is None:
        return None
    return "A" if pct >= 90 else "B" if pct >= 80 else "C" if pct >= 70 else "D" if pct >= 60 else "F"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_dashboard(
    plan: CoursePlan,
    records: dict[str, ItemRecord],
    as_of: date,
) -> dict[str, Any]:
    items = plan.items
    rec_of = {it.key: records.get(it.key) or ItemRecord() for it in items}

    grade, grade_submitted, by_type = compute_grade(plan, rec_of, as_of)
    missing = [it for it in items if _is_missing(it, rec_of[it.key], as_of)]
    early = [
        it for it in items
        if rec_of[it.key].score is not None and it.target > as_of
    ]
    if missing:
        pace = ("slight", "Slightly behind") if len(missing) <= plan.slightly_behind_max else ("behind", "Behind")
    elif len(early) >= plan.ahead_min_early:
        pace = ("ahead", "Ahead of schedule")
    else:
        pace = ("ok", "On track")

    expected = {
        t: (v["avg_submitted"] if v["avg_submitted"] is not None else DEFAULT_EXPECTED)
        for t, v in by_type.items()
    }

    checklist = [_checklist_row(it, rec_of[it.key], as_of) for it in items]
    moves = _next_moves(plan, rec_of, as_of, grade, expected)
    # On weekends "this week" means the coming school week.
    week_start = as_of - timedelta(days=as_of.weekday())
    if as_of.weekday() >= 5:
        week_start += timedelta(days=7)
    week_end = week_start + timedelta(days=6)

    # Grade if every past-due item were turned in at the student's usual level.
    catch_up = None
    if missing:
        g_after, _, _ = compute_grade(
            plan, rec_of, as_of, {it.key: expected[it.type] for it in missing}
        )
        catch_up = {"items": len(missing), "grade_after": _round(g_after),
                    "letter_after": letter(g_after)}

    done_count = sum(1 for it in items if rec_of[it.key].score is not None)
    due_count = sum(1 for it in items if it.target < as_of)

    xp, level = _xp_and_level(items, rec_of)
    streak = _streaks(items, rec_of, as_of)
    activity = _weekly_activity(items, rec_of, as_of)

    return {
        "as_of": as_of.isoformat(),
        "course": plan.course,
        "term": plan.term,
        "late_policy": plan.late_policy,
        "summary": {
            "grade": _round(grade),
            "letter": letter(grade),
            "grade_submitted": _round(grade_submitted),
            "letter_submitted": letter(grade_submitted),
            "pace": pace[0],
            "pace_label": pace[1],
            "missing_count": len(missing),
            "early_count": len(early),
            "done_count": done_count,
            "due_count": due_count,
            "total_count": len(items),
            "pending_count": sum(1 for it in items if rec_of[it.key].state == PENDING),
            "catch_up": catch_up,
        },
        "by_type": [
            {
                "type": t,
                "label": plan.type_labels.get(t, t),
                "weight": plan.weights[t],
                **{k: (_round(v) if isinstance(v, float) else v) for k, v in s.items()},
            }
            for t, s in by_type.items()
        ],
        "this_week": {
            "start": week_start.isoformat(),
            "end": week_end.isoformat(),
            "keys": [it.key for it in items if week_start <= it.target <= week_end],
        },
        "next_moves": moves,
        "units": _units(plan, rec_of, as_of),
        "checklist": checklist,
        "stats": _stats(items, rec_of),
        "tips": _tips(plan, rec_of, as_of, missing, catch_up, grade),
        "game": {
            "xp": xp,
            "level": level,
            "streak": streak,
            "activity": activity,
            "badges": _badges(plan, rec_of, as_of, missing, streak),
        },
    }


# ---------------------------------------------------------------------------
# Checklist + units
# ---------------------------------------------------------------------------


def _status_for(it: PlanItem, rec: ItemRecord, as_of: date) -> str:
    """One display status per item."""
    if rec.score is not None:
        if rec.completed_at and rec.completed_at.date() <= it.target:
            return "done_on_time"
        return "done" if rec.completed_at is None or it.target >= as_of else "done_late"
    if rec.state == PENDING:
        return "pending_grade"
    if it.target < as_of:
        return "missing"
    if rec.state in (IN_PROGRESS, ALMOST):
        return "in_progress"
    return "upcoming"


def _checklist_row(it: PlanItem, rec: ItemRecord, as_of: date) -> dict[str, Any]:
    return {
        "key": it.key,
        "title": it.title,
        "type": it.type,
        "unit": it.unit,
        "chapter": it.chapter,
        "target": it.target.isoformat(),
        "flexible": it.flexible,
        "status": _status_for(it, rec, as_of),
        "state": rec.state,
        "score": _round(rec.score),
        "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
        "link": rec.link,
        "alt_link": rec.alt_link,
        "available": rec.available,
        "almost_label": rec.almost_label,
        "can_revise": rec.can_revise,
        "revisions_left": rec.revisions_left,
        "detail": rec.detail,
    }


def _units(plan: CoursePlan, rec_of: dict[str, ItemRecord], as_of: date) -> list[dict]:
    out = []
    for u, name in sorted(plan.units.items()):
        its = [it for it in plan.items if it.unit == u]
        done = sum(1 for it in its if rec_of[it.key].score is not None)
        start = min(it.target for it in its)
        end = max(it.target for it in its)
        if done == len(its):
            state = "cleared"
        elif as_of > end:
            state = "open_past"
        elif start - timedelta(days=10) <= as_of <= end:
            state = "current"
        elif as_of < start:
            state = "future"
        else:
            state = "open_past"
        out.append({
            "unit": u, "name": name, "done": done, "total": len(its),
            "start": start.isoformat(), "end": end.isoformat(), "state": state,
            "missing": sum(1 for it in its if _is_missing(it, rec_of[it.key], as_of)),
        })
    return out


# ---------------------------------------------------------------------------
# Next-best moves
# ---------------------------------------------------------------------------


def _next_moves(
    plan: CoursePlan,
    rec_of: dict[str, ItemRecord],
    as_of: date,
    grade_now: float | None,
    expected: dict[str, float],
) -> list[dict]:
    """Rank actionable items by grade impact, urgency and effort.

    Impact is exact, from the weighted-grade formula: for past-due work, the
    change in today's grade if the item were finished at the student's own
    average for that type; for upcoming work, the points it would cost on
    the day after its target date if it were still not done.  Priority is
    impact per unit of effort, scaled by urgency, with a boost for one-step
    quick wins (an unsubmitted reflection, a half-watched video).
    """
    base = grade_now or 0.0
    cands: list[dict] = []
    for it in plan.items:
        rec = rec_of[it.key]
        if not rec.available or not rec.link:
            continue
        days = (it.target - as_of).days
        if rec.score is None and rec.state != PENDING:
            if days > 10 and rec.state not in (ALMOST, IN_PROGRESS):
                continue  # far-future work isn't a "next move" yet
            exp = expected[it.type]
            if days < 0:
                g_after, _, _ = compute_grade(plan, rec_of, as_of, {it.key: exp})
                delta = (g_after or 0.0) - base
                urgency = 1.0
            else:
                when = max(it.target + timedelta(days=1), as_of)
                g_skip, _, _ = compute_grade(plan, rec_of, when)
                g_do, _, _ = compute_grade(plan, rec_of, when, {it.key: exp})
                delta = (g_do or 0.0) - (g_skip or 0.0)
                urgency = 1.0 if days <= 3 else 0.7 if days <= 7 else 0.4
            if rec.state == ALMOST:
                kind, effort = "finish", rec.effort_minutes or ALMOST_EFFORT[it.type]
            elif rec.state == IN_PROGRESS:
                kind, effort = "resume", rec.effort_minutes or ALMOST_EFFORT[it.type]
            else:
                kind, effort = "start", rec.effort_minutes or EFFORT[it.type]
            boost = 1.5 if kind in ("finish", "resume") else 1.0
        elif rec.can_revise and rec.score is not None and it.type in REVISE_BELOW                 and rec.score < REVISE_BELOW[it.type]:
            new = min(100.0, rec.score + REVISE_GAIN)
            g_after, _, _ = compute_grade(plan, rec_of, as_of, {it.key: new})
            delta = (g_after or 0.0) - base
            kind, effort, urgency, boost = "revise", REVISE_EFFORT[it.type], 0.6, 1.0
        else:
            continue
        delta = max(delta, 0.0)
        priority = delta / (effort / 30 + 0.5) * urgency * boost
        cands.append({
            "key": it.key, "title": it.title, "type": it.type, "kind": kind,
            "label": (rec.almost_label if kind == "finish" else
                      (f"{rec.revisions_left} revision{'s' if rec.revisions_left != 1 else ''} left"
                       if kind == "revise" and rec.revisions_left is not None else None)),
            "target": it.target.isoformat(), "days_until_due": days,
            "past_due": days < 0 and kind != "revise", "grade_delta": _round(delta, 2),
            "effort_minutes": effort, "link": rec.link, "alt_link": rec.alt_link,
            "_sort": (-priority, days),
        })
    cands.sort(key=lambda c: c["_sort"])
    for c in cands:
        c.pop("_sort")
    return cands[:6]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def _stats(items: tuple[PlanItem, ...], rec_of: dict[str, ItemRecord]) -> dict[str, Any]:
    q_total = q_first = 0
    vids = []
    refl_dims: dict[str, list[int]] = {}
    frq_dims: dict[str, dict] = {}
    scores_over_time = []
    for it in items:
        rec = rec_of[it.key]
        d = rec.detail
        if it.type == "video" and rec.score is not None:
            tq, ftc = d.get("total_questions") or 0, d.get("first_try_correct") or 0
            q_total += tq
            q_first += ftc
            vids.append(it.key)
        if it.type == "scenario":
            for k, dim in (d.get("dimensions") or {}).items():
                if dim.get("level") in LEVEL_RANK:
                    refl_dims.setdefault(k, []).append(LEVEL_RANK[dim["level"]])
        if it.type == "frq":
            for dim in d.get("dimensions") or []:
                agg = frq_dims.setdefault(dim["key"], {"title": dim.get("title") or dim["key"],
                                                       "points": 0.0, "max": 0.0})
                agg["points"] += dim.get("points") or 0
                agg["max"] += dim.get("max_points") or 0
        if rec.score is not None and rec.completed_at:
            scores_over_time.append({"key": it.key, "type": it.type, "title": it.title,
                                     "date": rec.completed_at.date().isoformat(),
                                     "score": _round(rec.score)})
    scores_over_time.sort(key=lambda s: s["date"])
    level_names = {v: k for k, v in LEVEL_RANK.items()}
    return {
        "video_first_try_pct": _round(100 * q_first / q_total) if q_total else None,
        "video_questions": q_total,
        "videos_completed": len(vids),
        "reflection_dimensions": [
            {"key": k, "avg_rank": _round(sum(v) / len(v), 2), "count": len(v),
             "typical_level": level_names[round(sum(v) / len(v))]}
            for k, v in refl_dims.items()
        ],
        "frq_dimensions": [
            {"key": k, "title": v["title"], "pct": _round(100 * v["points"] / v["max"]) if v["max"] else None}
            for k, v in frq_dims.items()
        ],
        "scores_over_time": scores_over_time,
    }


# ---------------------------------------------------------------------------
# Tips (rules + surfacing feedback the graders already wrote)
# ---------------------------------------------------------------------------


def _tips(
    plan: CoursePlan,
    rec_of: dict[str, ItemRecord],
    as_of: date,
    missing: list[PlanItem],
    catch_up: dict | None,
    grade: float | None,
) -> list[dict]:
    tips: list[tuple[int, dict]] = []
    items = plan.items

    almost = [it for it in items if rec_of[it.key].state == ALMOST and rec_of[it.key].score is None]
    refl = [it for it in almost if it.type == "scenario"]
    if refl:
        tips.append((0, {
            "kind": "quick_win", "title": "Finish what you started",
            "body": ("You played " + _join([it.title for it in refl]) + " but haven't submitted the "
                     "reflection. The reflection is where the grade comes from, so this is your fastest win."),
        }))

    if missing and catch_up and grade is not None and catch_up["grade_after"] is not None:
        tips.append((1, {
            "kind": "catch_up", "title": "Late work still counts",
            "body": (f"Turning in your {len(missing)} past-due item{'s' if len(missing) != 1 else ''} "
                     f"at your usual level would move your grade from {grade:.0f}% to about "
                     f"{catch_up['grade_after']:.0f}%. {plan.late_policy}").strip(),
        }))

    # FRQ: weakest rubric dimension on the most recent graded FRQ.
    frqs = [it for it in items if it.type == "frq" and rec_of[it.key].detail.get("dimensions")]
    if frqs:
        last = max(frqs, key=lambda it: rec_of[it.key].completed_at or datetime.min)
        d = rec_of[last.key].detail
        dims = [x for x in d["dimensions"] if x.get("max_points")]
        if dims:
            weakest = min(dims, key=lambda x: (x.get("points") or 0) / x["max_points"])
            if (weakest.get("points") or 0) < weakest["max_points"]:
                body = f"On {last.title}, your growth area was {str(weakest.get('title') or weakest['key']).lower()}."
                if weakest.get("next_anchor"):
                    body += f" To reach the next level: {weakest['next_anchor']}"
                tips.append((2, {"kind": "frq", "title": "Level up your FRQ writing", "body": body,
                                 "quote": d.get("feedback")}))

    # Reflections: weakest dimension across graded reflections.
    ranks: dict[str, list[int]] = {}
    latest_fb = None
    latest_at = datetime.min
    for it in items:
        rec = rec_of[it.key]
        if it.type != "scenario":
            continue
        for k, dim in (rec.detail.get("dimensions") or {}).items():
            if dim.get("level") in LEVEL_RANK:
                ranks.setdefault(k, []).append(LEVEL_RANK[dim["level"]])
        if rec.detail.get("feedback") and rec.completed_at and rec.completed_at.replace(tzinfo=None) > latest_at:
            latest_at = rec.completed_at.replace(tzinfo=None)
            latest_fb = rec.detail["feedback"]
    if ranks:
        weak_key, weak = min(ranks.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        if sum(weak) / len(weak) < LEVEL_RANK["full"] and weak_key in REFLECTION_DIM_TIPS:
            tips.append((3, {"kind": "reflection", "title": f"Reflections: work on {weak_key}",
                             "body": REFLECTION_DIM_TIPS[weak_key], "quote": latest_fb}))

    # Videos: accuracy habit + concepts to review.
    q_total = sum(rec_of[it.key].detail.get("total_questions") or 0
                  for it in items if it.type == "video" and rec_of[it.key].score is not None)
    q_first = sum(rec_of[it.key].detail.get("first_try_correct") or 0
                  for it in items if it.type == "video" and rec_of[it.key].score is not None)
    n_vid = sum(1 for it in items if it.type == "video" and rec_of[it.key].score is not None)
    if n_vid >= 5 and q_total:
        pct = 100 * q_first / q_total
        if pct < 60:
            tips.append((2, {"kind": "video", "title": "Slow down at checkpoints",
                             "body": (f"Your first-try accuracy is {pct:.0f}%. Each first-try answer is worth "
                                      "points, so pause before answering, and rewind 30 seconds when a "
                                      "question surprises you.")}))
        elif pct >= 85:
            tips.append((6, {"kind": "praise", "title": "Sharp listener",
                             "body": f"{pct:.0f}% of your checkpoint answers are right on the first try. Keep it up."}))
    recent = sorted(
        (it for it in items if it.type == "video" and rec_of[it.key].detail.get("missed")),
        key=lambda it: rec_of[it.key].completed_at or datetime.min, reverse=True,
    )[:3]
    review = [{"video": it.title, "prompt": m["prompt"]}
              for it in recent for m in rec_of[it.key].detail["missed"][:2]][:4]
    if review:
        tips.append((4, {"kind": "review", "title": "Concepts to review",
                         "body": "These checkpoint questions tripped you up on your first try. They're likely FRQ material.",
                         "review": review}))

    revisable = [it for it in items if rec_of[it.key].can_revise and rec_of[it.key].score is not None
                 and it.type in REVISE_BELOW and rec_of[it.key].score < REVISE_BELOW[it.type]]
    if revisable:
        tips.append((5, {"kind": "revise", "title": "Only your best attempt counts",
                         "body": ("You can still revise " + _join([it.title for it in revisable[:3]]) +
                                  ". Revising never lowers your grade.")}))

    if not tips:
        tips.append((9, {"kind": "praise", "title": "Everything's on track",
                         "body": "No gaps right now. Get ahead on next week's items to stay ahead."}))
    tips.sort(key=lambda t: t[0])
    return [t for _, t in tips[:5]]


def _join(xs: list[str]) -> str:
    if len(xs) <= 1:
        return "".join(xs)
    return ", ".join(xs[:-1]) + " and " + xs[-1]


# ---------------------------------------------------------------------------
# Game layer
# ---------------------------------------------------------------------------


def _xp_and_level(items: tuple[PlanItem, ...], rec_of: dict[str, ItemRecord]) -> tuple[int, dict]:
    xp = 0.0
    for it in items:
        rec = rec_of[it.key]
        if rec.score is None:
            continue
        pts = XP_BASE[it.type] * rec.score / 100
        if rec.completed_at and rec.completed_at.date() <= it.target:
            pts *= 1 + XP_EARLY_BONUS
        xp += pts
    xp_i = int(round(xp))
    idx = max(i for i, (th, _) in enumerate(LEVELS) if xp_i >= th)
    floor, name = LEVELS[idx]
    nxt = LEVELS[idx + 1] if idx + 1 < len(LEVELS) else None
    return xp_i, {
        "number": idx + 1,
        "name": name,
        "floor": floor,
        "next_at": nxt[0] if nxt else None,
        "next_name": nxt[1] if nxt else None,
        "progress": _round((xp_i - floor) / (nxt[0] - floor), 3) if nxt else 1.0,
    }


def _streaks(items: tuple[PlanItem, ...], rec_of: dict[str, ItemRecord], as_of: date) -> dict:
    """Consecutive pacing-guide weeks where every target was met on time.

    Weeks with no targets are skipped. The current week counts only once
    it is already fully met, so a streak never "breaks" mid-week.
    """
    weeks: dict[date, list[PlanItem]] = {}
    for it in items:
        ws = it.target - timedelta(days=it.target.weekday())
        weeks.setdefault(ws, []).append(it)
    this_week = as_of - timedelta(days=as_of.weekday())

    def met(ws: date) -> bool:
        we = ws + timedelta(days=6)
        for it in weeks[ws]:
            rec = rec_of[it.key]
            if rec.score is None and rec.state != PENDING:
                return False
            if rec.completed_at and rec.completed_at.date() > we:
                return False
        return True

    history = []
    for ws in sorted(weeks):
        if ws > this_week:
            break
        ok = met(ws)
        if ws == this_week and not ok:
            break  # in progress, not failed
        history.append(ok)
    current = 0
    for ok in reversed(history):
        if not ok:
            break
        current += 1
    best = run = 0
    for ok in history:
        run = run + 1 if ok else 0
        best = max(best, run)
    return {"current_weeks": current, "best_weeks": best, "weeks_counted": len(history)}


def _weekly_activity(items: tuple[PlanItem, ...], rec_of: dict[str, ItemRecord], as_of: date) -> dict:
    this_week = as_of - timedelta(days=as_of.weekday())
    starts = [this_week - timedelta(weeks=n) for n in range(7, -1, -1)]
    counts = {ws: 0 for ws in starts}
    last7 = 0
    for it in items:
        rec = rec_of[it.key]
        if rec.score is None or not rec.completed_at:
            continue
        d = rec.completed_at.date()
        ws = d - timedelta(days=d.weekday())
        if ws in counts:
            counts[ws] += 1
        if as_of - timedelta(days=6) <= d <= as_of:
            last7 += 1
    return {"weeks": [{"start": ws.isoformat(), "completed": counts[ws]} for ws in starts],
            "last_7_days": last7}


def _badges(
    plan: CoursePlan,
    rec_of: dict[str, ItemRecord],
    as_of: date,
    missing: list[PlanItem],
    streak: dict,
) -> list[dict]:
    items = plan.items
    out: list[dict] = []

    def badge(bid, name, desc, icon, earned, progress=None, goal=None):
        out.append({"id": bid, "name": name, "description": desc, "icon": icon,
                    "earned": bool(earned), "progress": progress, "goal": goal})

    early = sum(1 for it in items if rec_of[it.key].score is not None and rec_of[it.key].completed_at
                and rec_of[it.key].completed_at.date() < it.target)
    badge("early_bird", "Early Bird", "Finish 3 items before their target dates", "sunrise",
          early >= 3, min(early, 3), 3)

    perfect = sum(1 for it in items if it.type == "video" and rec_of[it.key].score is not None
                  and (rec_of[it.key].detail.get("total_questions") or 0) >= 3
                  and rec_of[it.key].detail.get("first_try_correct") == rec_of[it.key].detail.get("total_questions"))
    badge("sharpshooter", "Sharpshooter", "Ace every checkpoint in a video on the first try", "target",
          perfect >= 1, min(perfect, 1), 1)

    deep = any((rec_of[it.key].detail.get("dimensions") or {}).get("insight", {}).get("level") == "full"
               for it in items if it.type == "scenario")
    badge("deep_thinker", "Deep Thinker", "Earn top marks for insight on a scenario reflection", "bulb", deep)

    revised = any(rec_of[it.key].detail.get("improved_by_revision") for it in items)
    badge("revision_pro", "Revision Pro", "Raise a score by revising your work", "loop", revised)

    late_done = sum(1 for it in items if rec_of[it.key].score is not None and rec_of[it.key].completed_at
                    and rec_of[it.key].completed_at.date() > it.target)
    badge("comeback", "Comeback", "Clear all past-due work after falling behind", "rocket",
          late_done > 0 and not missing)

    frq_best = max((rec_of[it.key].score or 0 for it in items if it.type == "frq"), default=0)
    badge("frq_ace", "FRQ Ace", "Score 90% or higher on an FRQ unit exam", "pen", frq_best >= 90)

    badge("on_fire", "On Fire", "Hit every weekly target 3 weeks in a row", "flame",
          streak["best_weeks"] >= 3, min(streak["best_weeks"], 3), 3)

    for u, name in sorted(plan.units.items()):
        its = [it for it in items if it.unit == u]
        done = sum(1 for it in its if rec_of[it.key].score is not None)
        badge(f"unit_{u}", f"Unit {u} Cleared", f"Complete everything in Unit {u}: {name}", "flag",
              done == len(its), done, len(its))
    return out
