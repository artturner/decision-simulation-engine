"""
Integration tests for GET /api/v1/public/plays/{play_id}.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.

Blueprint requirements covered:
- After start + initial view: returns start_scene_id scene, step_count=0
- After a choice step: returns next scene, step_count increments,
  choices_made includes the choice text
- After event truncation (simulating go-back): returns previous scene
  with prior progress
- When play is done: done=True, outcome, reflection_required,
  reflection_questions, reflection_prompts are populated
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
# Scenario fixtures
# ---------------------------------------------------------------------------

# Two-path scenario:  s1 (choice) → s2 (auto_advance) → s3 (end)
#                                 ↘ s3 (end, direct)
STANDARD_JSON: dict = {
    "metadata": {
        "title": "View Test",
        "completion_tracking": False,
    },
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "reflection_questions": [],
    "reflection_prompts": [],
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "First Choice",
            "choices": [
                {"text": "Long way", "next": "s2", "effects": {"score": 1}},
                {"text": "Short cut", "next": "s3"},
            ],
        },
        "s2": {
            "type": "auto_advance",
            "title": "Middle",
            "next": "s3",
        },
        "s3": {
            "type": "end",
            "title": "Done",
            "outcome": "success",
            "outcome_message": "Great work!",
        },
    },
}

# Same scenario but with completion_tracking=True and reflection prompts
REFLECTION_JSON: dict = {
    "metadata": {
        "title": "Reflection Test",
        "completion_tracking": True,
    },
    "variables": {},
    "start_scene_id": "s1",
    "reflection_questions": ["What did you learn?", "What would you change?"],
    "reflection_prompts": ["Consider the broader context.", "Be specific."],
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
    """Seed a published scenario and start a play. Return the play_id."""
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


@pytest.fixture()
def play_id(client, db: Session) -> uuid.UUID:
    return _seed_and_start(client, db, "view-standard", STANDARD_JSON)


@pytest.fixture()
def reflect_play_id(client, db: Session) -> uuid.UUID:
    return _seed_and_start(client, db, "view-reflect", REFLECTION_JSON)


def get_play(client, play_id: uuid.UUID):
    return client.get(f"/api/v1/public/plays/{play_id}")


def step(client, play_id: uuid.UUID, choice_index=None):
    body = {} if choice_index is None else {"choice_index": choice_index}
    return client.post(f"/api/v1/public/plays/{play_id}/step", json=body)


# ---------------------------------------------------------------------------
# Basic shape and 404
# ---------------------------------------------------------------------------


class TestGetPlayBasic:
    def test_returns_200(self, client, play_id):
        assert get_play(client, play_id).status_code == 200

    def test_play_id_in_response(self, client, play_id):
        body = get_play(client, play_id).json()
        assert uuid.UUID(body["play_id"]) == play_id

    def test_learner_label_in_response(self, client, db: Session):
        play_id = _seed_and_start(
            client,
            db,
            "view-learner-label",
            STANDARD_JSON,
            learner_label="Leo Dagleish",
        )
        body = get_play(client, play_id).json()
        assert body["learner_label"] == "Leo Dagleish"

    def test_404_for_unknown_play(self, client):
        assert get_play(client, uuid.uuid4()).status_code == 404

    def test_no_auth_required(self, client, play_id):
        """Public endpoint — no X-Admin-Key needed."""
        assert get_play(client, play_id).status_code == 200


# ---------------------------------------------------------------------------
# State immediately after start (no steps taken)
# ---------------------------------------------------------------------------


class TestGetPlayAfterStart:
    def test_scene_is_start_scene(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["scene"]["scene_id"] == "s1"

    def test_scene_type_is_choice(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["scene"]["type"] == "choice"

    def test_step_count_zero(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["progress"]["step_count"] == 0

    def test_choices_made_empty(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["progress"]["choices_made"] == []

    def test_done_false(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["done"] is False

    def test_outcome_none(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["outcome"] is None

    def test_reflection_required_false(self, client, play_id):
        body = get_play(client, play_id).json()
        assert body["reflection_required"] is False


# ---------------------------------------------------------------------------
# State after one choice step
# ---------------------------------------------------------------------------


class TestGetPlayAfterStep:
    def test_scene_advances(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = get_play(client, play_id).json()
        assert body["scene"]["scene_id"] == "s2"

    def test_step_count_increments(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = get_play(client, play_id).json()
        assert body["progress"]["step_count"] == 1

    def test_choices_made_populated(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = get_play(client, play_id).json()
        assert body["progress"]["choices_made"] == ["Long way"]

    def test_done_still_false(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = get_play(client, play_id).json()
        assert body["done"] is False


# ---------------------------------------------------------------------------
# State after event truncation (simulates go-back)
# ---------------------------------------------------------------------------


class TestGetPlayAfterTruncate:
    def test_scene_reverts(self, client, play_id, db: Session):
        """Truncating the choose event should restore the start scene."""
        step(client, play_id, choice_index=0)

        # Event log after step:
        #   seq=0 start, seq=1 view_scene(s1), seq=2 choose(s1), seq=3 view_scene(s2)
        # Keep only seq ≤ 1 to undo the choice.
        PlayRepository(db).truncate_events_after(play_id, seq=1)
        db.flush()

        body = get_play(client, play_id).json()
        assert body["scene"]["scene_id"] == "s1"

    def test_progress_reverts(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        PlayRepository(db).truncate_events_after(play_id, seq=1)
        db.flush()

        body = get_play(client, play_id).json()
        assert body["progress"]["step_count"] == 0
        assert body["progress"]["choices_made"] == []

    def test_done_reverts_to_false(self, client, play_id, db: Session):
        """Even if play was marked complete, truncating restores done=False
        at the DB level (play.completed) if we also reset the play flag.
        This test checks that GET correctly reflects the event-sourced state
        regardless of the play.completed flag (which the back endpoint will
        manage in Prompt 22)."""
        # Here we only truncate events; play.completed is not touched.
        # get_play uses play.completed as the authoritative done source.
        # After a single choice (not yet complete), truncating should show done=False.
        step(client, play_id, choice_index=0)
        PlayRepository(db).truncate_events_after(play_id, seq=1)
        db.flush()

        body = get_play(client, play_id).json()
        assert body["done"] is False


# ---------------------------------------------------------------------------
# Completed play state
# ---------------------------------------------------------------------------


class TestGetPlayWhenDone:
    @pytest.fixture()
    def done_play_id(self, client, play_id) -> uuid.UUID:
        """Drive play to completion via the short-cut path (choice 1 → s3)."""
        step(client, play_id, choice_index=1)
        return play_id

    def test_done_true(self, client, done_play_id):
        body = get_play(client, done_play_id).json()
        assert body["done"] is True

    def test_end_scene_returned(self, client, done_play_id):
        body = get_play(client, done_play_id).json()
        assert body["scene"]["type"] == "end"
        assert body["scene"]["scene_id"] == "s3"

    def test_outcome_populated(self, client, done_play_id):
        body = get_play(client, done_play_id).json()
        assert body["outcome"] == "success"

    def test_outcome_message_populated(self, client, done_play_id):
        body = get_play(client, done_play_id).json()
        assert body["outcome_message"] == "Great work!"

    def test_reflection_required_false_without_tracking(self, client, done_play_id):
        """STANDARD_JSON has completion_tracking=False."""
        body = get_play(client, done_play_id).json()
        assert body["reflection_required"] is False

    def test_reflection_lists_empty_without_tracking(self, client, done_play_id):
        body = get_play(client, done_play_id).json()
        assert body["reflection_questions"] == []
        assert body["reflection_prompts"] == []


# ---------------------------------------------------------------------------
# Reflection fields when completion_tracking=True
# ---------------------------------------------------------------------------


class TestGetPlayReflectionFields:
    @pytest.fixture()
    def done_reflect_id(self, client, reflect_play_id) -> uuid.UUID:
        step(client, reflect_play_id, choice_index=0)
        return reflect_play_id

    def test_reflection_required_true(self, client, done_reflect_id):
        body = get_play(client, done_reflect_id).json()
        assert body["reflection_required"] is True

    def test_reflection_questions_populated(self, client, done_reflect_id):
        body = get_play(client, done_reflect_id).json()
        assert body["reflection_questions"] == [
            "What did you learn?",
            "What would you change?",
        ]

    def test_reflection_prompts_populated(self, client, done_reflect_id):
        body = get_play(client, done_reflect_id).json()
        assert body["reflection_prompts"] == [
            "Consider the broader context.",
            "Be specific.",
        ]

    def test_reflection_not_populated_before_done(self, client, reflect_play_id):
        """Reflection fields are empty while the play is still in progress."""
        body = get_play(client, reflect_play_id).json()
        assert body["reflection_required"] is False
        assert body["reflection_questions"] == []
        assert body["reflection_prompts"] == []
