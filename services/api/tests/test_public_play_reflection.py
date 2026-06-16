"""
Integration tests for POST /api/v1/public/plays/{play_id}/reflection.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.

Blueprint requirements covered:
- 404 for unknown play
- 400 when play is not yet completed
- 409 when a reflection has already been submitted
- 200 on first successful submission
- responses stored as a dict keyed by reflection field name
- student_name persisted (optional)
- Missing required fields → 422
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.scenario import VersionStatus
from app.repositories.play_repo import PlayRepository
from app.repositories.scenario_repo import ScenarioRepository

# ---------------------------------------------------------------------------
# Scenario fixture
# ---------------------------------------------------------------------------

SCENARIO_JSON: dict = {
    "metadata": {
        "title": "Reflection Test",
        "completion_tracking": True,
    },
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(db: Session):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_and_start(
    client,
    db: Session,
    slug: str,
    scenario_json: dict,
    learner_label: str | None = None,
) -> uuid.UUID:
    repo = ScenarioRepository(db)
    s = repo.create_scenario(slug, "Test")
    v = repo.create_version(s.id, scenario_json, status=VersionStatus.published)
    db.flush()

    resp = client.post(
        "/api/v1/public/plays/start",
        json={
            "scenario_version_id": str(v.id),
            **({"learner_label": learner_label} if learner_label else {}),
        },
    )
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["play_id"])


def _step(client, play_id: uuid.UUID, choice_index=None):
    body = {} if choice_index is None else {"choice_index": choice_index}
    return client.post(f"/api/v1/public/plays/{play_id}/step", json=body)


def _reflect(client, play_id: uuid.UUID, responses=None, student_name=None):
    body: dict = {
        "responses": responses or {
            "reflection_1": "I learned a lot.",
            "reflection_2": "I would be more careful.",
        }
    }
    if student_name is not None:
        body["student_name"] = student_name
    return client.post(f"/api/v1/public/plays/{play_id}/reflection", json=body)


@pytest.fixture()
def play_id(client, db: Session) -> uuid.UUID:
    return _seed_and_start(client, db, "reflect-test", SCENARIO_JSON)


@pytest.fixture()
def completed_play_id(client, play_id) -> uuid.UUID:
    _step(client, play_id, choice_index=0)
    return play_id


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestReflectionErrors:
    def test_404_unknown_play(self, client):
        assert _reflect(client, uuid.uuid4()).status_code == 404

    def test_400_play_not_completed(self, client, play_id):
        resp = _reflect(client, play_id)
        assert resp.status_code == 400

    def test_400_play_not_completed_message(self, client, play_id):
        body = _reflect(client, play_id).json()
        assert "completed" in body["detail"].lower()

    def test_409_duplicate_submission(self, client, completed_play_id):
        _reflect(client, completed_play_id)           # first — succeeds
        resp = _reflect(client, completed_play_id)    # second — conflict
        assert resp.status_code == 409

    def test_409_message(self, client, completed_play_id):
        _reflect(client, completed_play_id)
        body = _reflect(client, completed_play_id).json()
        assert "already" in body["detail"].lower()

    def test_422_missing_responses(self, client, completed_play_id):
        """Omitting the responses field entirely should fail Pydantic validation."""
        resp = client.post(
            f"/api/v1/public/plays/{completed_play_id}/reflection",
            json={"student_name": "Alice"},
        )
        assert resp.status_code == 422

    def test_422_empty_responses_dict(self, client, completed_play_id):
        """An empty dict should fail the min_length=1 constraint."""
        resp = client.post(
            f"/api/v1/public/plays/{completed_play_id}/reflection",
            json={"responses": {}},
        )
        assert resp.status_code == 422

    def test_no_auth_required(self, client, completed_play_id):
        assert _reflect(client, completed_play_id).status_code == 200


# ---------------------------------------------------------------------------
# Successful submission
# ---------------------------------------------------------------------------


class TestReflectionSuccess:
    def test_returns_200(self, client, completed_play_id):
        assert _reflect(client, completed_play_id).status_code == 200

    def test_ok_true_in_response(self, client, completed_play_id):
        body = _reflect(client, completed_play_id).json()
        assert body["ok"] is True

    def test_responses_persisted_as_dict(self, client, completed_play_id, db: Session):
        responses = {"reflection_1": "First answer.", "reflection_2": "Second answer."}
        _reflect(client, completed_play_id, responses=responses)
        reflection = PlayRepository(db).get_reflection(completed_play_id)
        assert reflection is not None
        assert reflection.responses_json == responses

    def test_student_name_persisted(self, client, completed_play_id, db: Session):
        _reflect(client, completed_play_id, student_name="Alice")
        reflection = PlayRepository(db).get_reflection(completed_play_id)
        assert reflection.student_name == "Alice"

    def test_student_name_optional(self, client, completed_play_id, db: Session):
        _reflect(client, completed_play_id)
        reflection = PlayRepository(db).get_reflection(completed_play_id)
        assert reflection.student_name is None

    def test_defaults_student_name_to_learner_label(self, client, db: Session):
        play_id = _seed_and_start(
            client,
            db,
            "reflect-learner-label",
            SCENARIO_JSON,
            learner_label="Leo Dagleish",
        )
        _step(client, play_id, choice_index=0)
        _reflect(client, play_id)
        reflection = PlayRepository(db).get_reflection(play_id)
        assert reflection.student_name == "Leo Dagleish"

    def test_single_key_accepted(self, client, completed_play_id):
        """A dict with one key is valid (min_length=1)."""
        resp = client.post(
            f"/api/v1/public/plays/{completed_play_id}/reflection",
            json={"responses": {"reflection_1": "Only one answer."}},
        )
        assert resp.status_code == 200
