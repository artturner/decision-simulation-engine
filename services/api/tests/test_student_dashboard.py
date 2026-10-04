"""GET /api/v1/student/dashboard — auth, plan scoping, scenario states, upstreams."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.play import Reflection, ReflectionAttempt
from app.models.scenario import VersionStatus
from app.models.user import User, UserRole
from app.repositories.claim_repo import ClaimRepository
from app.repositories.play_repo import PlayRepository
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.services import dashboard_sources
from app.services.course_plan import CoursePlan, PlanItem
from app.services.student_tokens import issue_student_token

URL = "/api/v1/student/dashboard"


def _scenario_json(title: str) -> dict:
    return {
        "metadata": {"title": title, "description": "d"},
        "variables": {},
        "start_scene_id": "s1",
        "scenes": {
            "s1": {"type": "choice", "title": "Start", "choices": [{"text": "Go", "next": "s2"}]},
            "s2": {"type": "end", "title": "Done", "outcome": "ok", "outcome_message": ""},
        },
    }


TITLES = ["Dash Alpha", "Dash Bravo", "Dash Charlie", "Dash Delta"]


def _plan() -> CoursePlan:
    return CoursePlan(
        id="dash-test", course="Test Course", term="T", owner_emails=("dash-teacher@example.com",),
        weights={"video": 0.2, "scenario": 0.35, "frq": 0.45},
        type_labels={"video": "V", "scenario": "S", "frq": "F"}, units={1: "One"},
        term_end=date(2026, 12, 11), late_policy="", ahead_min_early=3, slightly_behind_max=3,
        items=tuple(
            PlanItem(key=t.lower().replace(" ", "-"), title=t, type="scenario", source="scenario",
                     match_title=t, chapter=1, unit=1, target=date(2026, 9, 1), flexible=False)
            for t in TITLES
        ) + (
            PlanItem(key="frq-1", title="FRQ 1", type="frq", source="essay", match_title="Unit 1 FRQ",
                     chapter=None, unit=1, target=date(2026, 9, 10), flexible=False),
            PlanItem(key="vid-1", title="Vid 1", type="video", source="video", match_title="Vid One",
                     chapter=1, unit=1, target=date(2026, 9, 1), flexible=False),
        ),
    )


@pytest.fixture()
def teacher(db: Session) -> User:
    user = User(id=uuid.uuid4(), email="dash-teacher@example.com", role=UserRole.teacher, is_approved=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client(db: Session, monkeypatch):
    def override_get_db():
        yield db

    plan = _plan()
    monkeypatch.setattr(
        "app.api.v1.student.plan_for_owner_email",
        lambda email: plan if email == "dash-teacher@example.com" else None,
    )
    monkeypatch.setattr(settings, "ESSAY_API_BASE", "")
    monkeypatch.setattr(settings, "VIDEO_API_BASE", "")
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def roll(db: Session, teacher: User):
    roll = RollRepository(db).create(teacher.id, "Dash Period", ["Lee, Amy", "Ng, Ben"])
    db.flush()
    return roll


@pytest.fixture()
def versions(db: Session, roll):
    repo = ScenarioRepository(db)
    out = {}
    for i, title in enumerate(TITLES):
        sc = repo.create_scenario(f"dash-{i}-{uuid.uuid4().hex[:6]}", title)
        out[title] = repo.create_version(sc.id, _scenario_json(title), status=VersionStatus.published)
        RollRepository(db).assign_scenario(sc.id, roll.id, visible=True, sort_order=i)
    db.flush()
    return out


def token_for(db: Session, roll, name: str) -> str:
    claims = ClaimRepository(db).ensure_for_roll(roll)
    db.flush()
    claim = next(c for c in claims if c.student_name == name)
    return issue_student_token(claim, roll.owner_id)[0]


def _play(db, version, roll, name="Lee, Amy", completed=False):
    play = PlayRepository(db).create_play(version.id, learner_label=name, class_roll_id=roll.id)
    if completed:
        play.completed = True
        play.ended_at = datetime(2026, 8, 30, 15, tzinfo=timezone.utc)
    db.flush()
    return play


def _reflect(db, play, grades: list[int] | None):
    r = Reflection(play_id=play.id, student_name=play.learner_label, responses_json={"q": "a"},
                   submitted_at=datetime(2026, 8, 30, 16, tzinfo=timezone.utc))
    db.add(r)
    db.flush()
    if grades:
        for n, g in enumerate(grades, 1):
            db.add(ReflectionAttempt(
                reflection_id=r.id, attempt_number=n, responses_json={"q": "a"}, grade_total=g,
                grade_breakdown={"dimensions": {"insight": {"level": "full", "points": 25, "max_points": 25,
                                                            "evidence": "e"}},
                                 "needs_human_review": True, "review_reason": "SECRET-REASON"},
                feedback=f"fb{n}", graded_at=datetime(2026, 8, 30, 16, n, tzinfo=timezone.utc)))
        r.grade_total = grades[-1]
        r.grade_attempts = len(grades)
        r.graded_at = datetime(2026, 8, 30, 17, tzinfo=timezone.utc)
    db.flush()
    db.expire_all()
    return r


# ---------------------------------------------------------------------------


@pytest.mark.parametrize("enforced", [False, True])
def test_requires_token_even_in_grace_period(client, monkeypatch, enforced):
    monkeypatch.setattr(settings, "STUDENT_TOKEN_ENFORCED", enforced)
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers={"X-Student-Token": "garbage"}).status_code == 401


def test_revoked_token_is_rejected(client, db, roll):
    token = token_for(db, roll, "Lee, Amy")
    for c in ClaimRepository(db).ensure_for_roll(roll):
        if c.student_name == "Lee, Amy":
            db.delete(c)
    db.flush()
    resp = client.get(URL, headers={"X-Student-Token": token})
    assert resp.status_code == 401


def test_teacher_without_plan_gets_not_set_up(client, db):
    other = User(id=uuid.uuid4(), email="no-plan@example.com", role=UserRole.teacher, is_approved=True)
    db.add(other)
    db.flush()
    roll = RollRepository(db).create(other.id, "Other", ["Lee, Amy"])
    db.flush()
    body = client.get(URL, headers={"X-Student-Token": token_for(db, roll, "Lee, Amy")}).json()
    assert body["plan_available"] is False and body["dashboard"] is None
    assert body["student"]["name"] == "Lee, Amy"


def test_scenario_states_grades_and_privacy(client, db, roll, versions):
    v = versions
    # Alpha: two completed plays; best graded attempt 92 (latest 70) → done 92.
    p1 = _play(db, v["Dash Alpha"], roll, completed=True)
    _reflect(db, p1, [92, 70])
    p2 = _play(db, v["Dash Alpha"], roll, completed=True)
    _reflect(db, p2, [60])
    # Bravo: completed, no reflection → almost.
    pb = _play(db, v["Dash Bravo"], roll, completed=True)
    # Charlie: in progress.
    pc = _play(db, v["Dash Charlie"], roll)
    # Delta: untouched; plus a classmate's play that must not leak.
    _reflect(db, _play(db, v["Dash Delta"], roll, name="Ng, Ben", completed=True), [99])

    resp = client.get(URL, headers={"X-Student-Token": token_for(db, roll, "Lee, Amy")})
    assert resp.status_code == 200, resp.text
    assert "SECRET-REASON" not in resp.text
    body = resp.json()
    assert body["sources"] == {"scenarios": "ok", "essays": "not_configured", "videos": "not_configured"}
    rows = {r["key"]: r for r in body["dashboard"]["checklist"]}
    alpha = rows["dash-alpha"]
    assert alpha["score"] == 92.0 and alpha["state"] == "done"
    assert alpha["can_revise"] is True and alpha["revisions_left"] == settings.AI_GRADER_MAX_ATTEMPTS - 2
    assert alpha["link"].endswith(f"/complete/{p1.id}")
    assert alpha["detail"]["feedback"] == "fb1"
    assert rows["dash-bravo"]["state"] == "almost"
    assert rows["dash-bravo"]["link"].endswith(f"/complete/{pb.id}")
    assert rows["dash-charlie"]["state"] == "in_progress"
    assert rows["dash-charlie"]["link"].endswith(f"/play/{pc.id}")
    delta = rows["dash-delta"]
    assert delta["state"] == "not_started" and delta["score"] is None
    assert delta["link"] == f"/join?code={roll.join_code}"
    moves = body["dashboard"]["next_moves"]
    assert moves[0]["key"] == "dash-bravo" and moves[0]["kind"] == "finish"


def test_name_equivalence_across_rolls(client, db, teacher, roll, versions):
    second = RollRepository(db).create(teacher.id, "Dash Period B", ["amy lee"])
    db.flush()
    RollRepository(db).assign_scenario(versions["Dash Alpha"].scenario_id, second.id, visible=True, sort_order=1)
    _reflect(db, _play(db, versions["Dash Alpha"], second, name="amy lee", completed=True), [88])
    body = client.get(URL, headers={"X-Student-Token": token_for(db, roll, "Lee, Amy")}).json()
    rows = {r["key"]: r for r in body["dashboard"]["checklist"]}
    assert rows["dash-alpha"]["score"] == 88.0


def test_upstreams_merge_and_degrade(client, db, roll, versions, monkeypatch):
    monkeypatch.setattr(settings, "ESSAY_API_BASE", "https://essay.test")
    monkeypatch.setattr(settings, "VIDEO_API_BASE", "https://video.test")
    monkeypatch.setattr(settings, "VIDEO_INTERNAL_KEY", "k" * 40)
    seen = {}

    def fake_get(url, headers, params=None):
        seen[url] = (headers, params)
        if url.startswith("https://essay.test"):
            return {"assignments": [{"title": "Unit 1 FRQ", "join_code": "ESS111", "status": "graded",
                                     "score": 80.0, "max_total": 100.0, "attempts": 1, "max_attempts": 3,
                                     "first_graded_at": "2026-09-09T12:00:00Z", "dimensions": []}]}
        raise RuntimeError("video down")

    monkeypatch.setattr(dashboard_sources, "_get", fake_get)
    token = token_for(db, roll, "Lee, Amy")
    body = client.get(URL, headers={"X-Student-Token": token}).json()
    assert body["sources"]["essays"] == "ok" and body["sources"]["videos"] == "unavailable"
    rows = {r["key"]: r for r in body["dashboard"]["checklist"]}
    assert rows["frq-1"]["score"] == 80.0
    essay_headers, _ = seen["https://essay.test/api/v1/public/student/progress"]
    assert essay_headers["X-Student-Token"] == token
    vid_headers, vid_params = seen["https://video.test/api/internal/student-progress"]
    assert vid_headers["X-Internal-Key"] == "k" * 40 and vid_params == {"name": "Lee, Amy"}
