"""
Course plans for the student dashboard.

A course plan is the teacher's syllabus as data: every graded item, its
type (video / scenario / frq), unit, pacing-guide target date, and which app
assignment it corresponds to.  Plans live as JSON in ``app/data/`` and are
shared with the offline report tooling (tools/unit-reports/student_report.py),
so the printed counselor report and the live dashboard can never disagree.

A plan is scoped to teacher accounts by email; students of a teacher with no
plan get a "not set up for your class yet" dashboard.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ITEM_TYPES = ("video", "scenario", "frq")


@dataclass(frozen=True)
class PlanItem:
    key: str
    title: str
    type: str  # video | scenario | frq
    source: str  # video | scenario | essay — which app holds it
    match_title: str  # the app's assignment title (normalized at match time)
    chapter: int | None
    unit: int
    target: date
    flexible: bool


@dataclass(frozen=True)
class CoursePlan:
    id: str
    course: str
    term: str
    owner_emails: tuple[str, ...]
    weights: dict[str, float]
    type_labels: dict[str, str]
    units: dict[int, str]
    term_end: date
    late_policy: str
    ahead_min_early: int
    slightly_behind_max: int
    items: tuple[PlanItem, ...]


def norm_title(s: str) -> str:
    """Casefold to alphanumeric words — same rule as export_all_grades.py."""
    s = (s or "").casefold().replace("&", " and ")
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return " ".join(s.split())


def _parse(raw: dict) -> CoursePlan:
    items = tuple(
        PlanItem(
            key=i["key"],
            title=i["title"],
            type=i["type"],
            source=i["source"],
            match_title=i["match_title"],
            chapter=i.get("chapter"),
            unit=int(i["unit"]),
            target=date.fromisoformat(i["target"]),
            flexible=bool(i.get("flexible")),
        )
        for i in raw["items"]
    )
    for it in items:
        if it.type not in ITEM_TYPES:
            raise ValueError(f"course plan {raw['id']}: bad item type {it.type!r}")
    return CoursePlan(
        id=raw["id"],
        course=raw["course"],
        term=raw["term"],
        owner_emails=tuple(e.casefold() for e in raw["owner_emails"]),
        weights={k: float(v) for k, v in raw["weights"].items()},
        type_labels=dict(raw["type_labels"]),
        units={int(k): v for k, v in raw["units"].items()},
        term_end=date.fromisoformat(raw["term_end"]),
        late_policy=raw.get("late_policy", ""),
        ahead_min_early=int(raw["pace"]["ahead_min_early"]),
        slightly_behind_max=int(raw["pace"]["slightly_behind_max"]),
        items=items,
    )


@lru_cache(maxsize=1)
def load_plans() -> tuple[CoursePlan, ...]:
    return tuple(
        _parse(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted(DATA_DIR.glob("course_plan_*.json"))
    )


def plan_for_owner_email(email: str | None) -> CoursePlan | None:
    if not email:
        return None
    e = email.casefold()
    for plan in load_plans():
        if e in plan.owner_emails:
            return plan
    return None
