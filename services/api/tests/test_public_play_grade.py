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
from app.models.scenario import VersionStatus
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
def completed_play_id(client, db: Session) -> uuid.UUID:
    repo = ScenarioRepository(db)
    s = repo.create_scenario("grade-test", "Test")
    v = repo.create_version(s.id, SCENARIO_JSON, status=VersionStatus.published)
    db.flush()
    resp = client.post(
        "/api/v1/public/plays/start", json={"scenario_version_id": str(v.id)}
    )
    assert resp.status_code == 201
    play_id = uuid.UUID(resp.json()["play_id"])
    client.post(f"/api/v1/public/plays/{play_id}/step", json={"choice_index": 0})
    return play_id


@pytest.fixture()
def grading_on(monkeypatch):
    """Enable grading and stub the AI judge with a deterministic result."""
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "AI_GRADER_MAX_ATTEMPTS", 3, raising=False)

    calls = {"n": 0}

    def fake_grade(reflection_questions, responses, choice_path, completed):
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
            model="claude-sonnet-4-6",
            graded_at=datetime.now(timezone.utc),
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
