"""
Integration tests for the AI-graded reflection endpoints:
  POST /api/v1/public/plays/{play_id}/reflection/grade
  POST /api/v1/public/plays/{play_id}/reflection/accept

Requires a running Postgres instance (docker compose up -d db).
The AI grader itself is monkeypatched so no API key or network call is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.play import GradingCall
from app.models.scenario import VersionStatus
from app.models.user import User, UserRole
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.services import ai_grader
from app.services.ai_grader import DimensionScore, GradeResult

SCENARIO_JSON: dict = {
    "metadata": {"title": "Grade Test", "completion_tracking": True},
    "variables": {},
    "start_scene_id": "s1",
    "reflection_questions": ["What did you learn?", "What would you change?"],
    "reflection_prompts": ["Be specific.", "Consider context."],
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Choose",
            "choices": [{"text": "Go", "next": "s2"}],
        },
        "s2": {
            "type": "end",
            "title": "End",
            "outcome": "done",
            "outcome_message": "Finished.",
        },
    },
}


@pytest.fixture()
def client(db: Session):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def teacher(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="grade-teacher@example.com",
        role=UserRole.teacher,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def roll(db: Session, teacher: User):
    created = RollRepository(db).create(teacher.id, "Period 1", ["Alice Adams"])
    db.flush()
    return created


def _start_completed_play(client, db: Session, roll=None) -> uuid.UUID:
    repo = ScenarioRepository(db)
    s = repo.create_scenario("grade-test", "Test")
    v = repo.create_version(s.id, SCENARIO_JSON, status=VersionStatus.published)
    if roll is not None:
        RollRepository(db).assign_scenario(s.id, roll.id, visible=True)
    db.flush()
    body: dict = {"scenario_version_id": str(v.id)}
    if roll is not None:
        body["class_roll_id"] = str(roll.id)
        body["learner_label"] = "Alice Adams"
    resp = client.post("/api/v1/public/plays/start", json=body)
    assert resp.status_code == 201
    play_id = uuid.UUID(resp.json()["play_id"])
    client.post(f"/api/v1/public/plays/{play_id}/step", json={"choice_index": 0})
    return play_id


@pytest.fixture()
def completed_play_id(client, db: Session, roll) -> uuid.UUID:
    """A completed class-joined play (grading requires class attribution)."""
    return _start_completed_play(client, db, roll)


@pytest.fixture()
def grading_on(monkeypatch):
    """Enable grading and stub the AI judge with a deterministic result."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "AI_GRADER_MAX_ATTEMPTS", 3, raising=False)

    calls = {"n": 0}

    def fake_grade(
        reflection_questions, responses, choice_path, completed, difficulty="standard"
    ):
        calls["n"] += 1
        return GradeResult(
            grade_total=85,
            completion_points=20,
            dimensions={
                "engagement": DimensionScore("full", 25, 25, "e"),
                "reasoning": DimensionScore("solid", 24, 30, "r"),
                "insight": DimensionScore("minimal", 16, 25, "i"),
            },
            feedback="Solid reflection.",
            needs_human_review=False,
            review_reason=None,
            low_effort_flags=[],
            difficulty=difficulty,
            model="claude-sonnet-4-6",
            graded_at=datetime.now(timezone.utc),
            input_tokens=500,
            output_tokens=200,
        )

    monkeypatch.setattr(ai_grader, "grade_reflection", fake_grade)
    return calls


def _grade(client, play_id, responses=None):
    return client.post(
        f"/api/v1/public/plays/{play_id}/reflection/grade",
        json={"responses": responses or {"reflection_1": "a", "reflection_2": "b"}},
    )


class TestGradeEndpoint:
    def test_404_unknown_play(self, client, grading_on):
        assert _grade(client, uuid.uuid4()).status_code == 404

    def test_503_when_grading_disabled(self, client, completed_play_id, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "", raising=False)
        assert _grade(client, completed_play_id).status_code == 503

    def test_happy_path_returns_grade(self, client, completed_play_id, grading_on):
        resp = _grade(client, completed_play_id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["grade_total"] == 85
        assert body["attempts_used"] == 1
        assert body["attempts_remaining"] == 2
        assert body["can_redo"] is True
        assert body["accepted"] is False
        assert "engagement" in body["dimensions"]

    def test_attempt_cap(self, client, completed_play_id, grading_on):
        for _ in range(3):
            assert _grade(client, completed_play_id).status_code == 200
        # 4th call: capped — returns last grade without calling the judge again
        resp = _grade(client, completed_play_id)
        assert resp.status_code == 200
        assert resp.json()["can_redo"] is False
        assert grading_on["n"] == 3  # judge invoked exactly 3 times

    def test_accept_locks_reflection(self, client, completed_play_id, grading_on):
        _grade(client, completed_play_id)
        acc = client.post(
            f"/api/v1/public/plays/{completed_play_id}/reflection/accept", json={}
        )
        assert acc.status_code == 200
        assert acc.json()["accepted"] is True
        # Re-grading a locked reflection is rejected.
        assert _grade(client, completed_play_id).status_code == 409

    def test_accept_without_reflection_404(self, client, completed_play_id, grading_on):
        acc = client.post(
            f"/api/v1/public/plays/{completed_play_id}/reflection/accept", json={}
        )
        assert acc.status_code == 404


class TestGradingCostControls:
    def test_direct_link_play_gets_503(self, client, db: Session, grading_on):
        """Anonymous plays are not attributable to a teacher; grading is
        refused so the frontend falls back to plain submission."""
        play_id = _start_completed_play(client, db, roll=None)
        resp = _grade(client, play_id)
        assert resp.status_code == 503
        assert grading_on["n"] == 0

    def test_grading_call_recorded_with_usage(
        self, client, db: Session, teacher, completed_play_id, grading_on
    ):
        assert _grade(client, completed_play_id).status_code == 200
        calls = list(
            db.query(GradingCall).filter(GradingCall.teacher_id == teacher.id)
        )
        assert len(calls) == 1
        assert calls[0].play_id == completed_play_id
        assert calls[0].input_tokens == 500
        assert calls[0].output_tokens == 200
        assert calls[0].model == "claude-sonnet-4-6"

    def test_monthly_quota_blocks_grading(
        self, client, db: Session, completed_play_id, grading_on, monkeypatch
    ):
        monkeypatch.setattr(settings, "AI_GRADER_MONTHLY_TEACHER_LIMIT", 1, raising=False)
        assert _grade(client, completed_play_id).status_code == 200
        resp = _grade(client, completed_play_id)
        assert resp.status_code == 503
        assert "limit" in resp.json()["detail"].lower()
        assert grading_on["n"] == 1

    def test_zero_limit_disables_quota(
        self, client, db: Session, completed_play_id, grading_on, monkeypatch
    ):
        monkeypatch.setattr(settings, "AI_GRADER_MONTHLY_TEACHER_LIMIT", 0, raising=False)
        assert _grade(client, completed_play_id).status_code == 200
        assert _grade(client, completed_play_id).status_code == 200
        assert grading_on["n"] == 2
