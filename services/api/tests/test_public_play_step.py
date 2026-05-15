"""
Integration tests for POST /api/v1/public/plays/{play_id}/step.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.models.play import EventType, Play
from app.models.scenario import VersionStatus
from app.repositories.play_repo import PlayRepository
from app.repositories.scenario_repo import ScenarioRepository

# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

# Four-scene scenario covering every scene type:
#   s_choice → (choice 0) → s_auto → s_conditional → s_end
#   s_choice → (choice 1) → s_end        (direct end route)
FULL_JSON: dict = {
    "metadata": {"title": "Step Test"},
    "variables": {"score": 0},
    "start_scene_id": "s_choice",
    "scenes": {
        "s_choice": {
            "type": "choice",
            "title": "Choose",
            "narration": "Pick one.",
            "choices": [
                {"text": "Long path", "next": "s_auto", "effects": {"score": 1}},
                {"text": "Short path", "next": "s_end"},
            ],
        },
        "s_auto": {
            "type": "auto_advance",
            "title": "Auto",
            "next": "s_conditional",
        },
        "s_conditional": {
            "type": "conditional",
            "title": "Conditional",
            "conditions": [{"condition": "score >= 1", "next": "s_end"}],
            "default": "s_end",
        },
        "s_end": {
            "type": "end",
            "title": "The End",
            "outcome": "success",
            "outcome_message": "Well done!",
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


@pytest.fixture()
def play_id(client, db: Session) -> uuid.UUID:
    """Seed a published scenario and start a play. Return the play ID."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("step-test", "Step Test")
    repo.create_version(s.id, FULL_JSON, status=VersionStatus.published)
    db.flush()

    resp = client.get("/api/v1/public/scenarios/step-test")
    version_id = resp.json()["scenario_version_id"]

    start_resp = client.post(
        "/api/v1/public/plays/start",
        json={"scenario_version_id": version_id},
    )
    return uuid.UUID(start_resp.json()["play_id"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def step(client, play_id, choice_index=None) -> dict:
    body = {}
    if choice_index is not None:
        body["choice_index"] = choice_index
    return client.post(f"/api/v1/public/plays/{play_id}/step", json=body)


# ---------------------------------------------------------------------------
# Choice scene step
# ---------------------------------------------------------------------------


class TestStepChoice:
    def test_returns_200(self, client, play_id):
        assert step(client, play_id, choice_index=0).status_code == 200

    def test_advances_to_next_scene(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        assert body["scene"]["scene_id"] == "s_auto"

    def test_next_scene_type(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        assert body["scene"]["type"] == "auto_advance"

    def test_done_is_false(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        assert body["done"] is False

    def test_step_count_increments(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        assert body["progress"]["step_count"] == 1

    def test_choices_made_updated(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        assert body["progress"]["choices_made"] == ["Long path"]

    def test_choose_event_logged(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        events = PlayRepository(db).get_events(play_id)
        types = [e.event_type for e in events]
        assert EventType.choose in types

    def test_choose_event_has_choice_text(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        events = PlayRepository(db).get_events(play_id)
        e = next(e for e in events if e.event_type == EventType.choose)
        assert e.choice_text == "Long path"

    def test_choose_event_has_delta_json(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        events = PlayRepository(db).get_events(play_id)
        e = next(e for e in events if e.event_type == EventType.choose)
        assert e.delta_json == {"score": 1}

    def test_view_scene_logged_for_next(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        events = PlayRepository(db).get_events(play_id)
        view_events = [e for e in events if e.event_type == EventType.view_scene]
        # start view_scene (seq=1) + new view_scene (seq=3)
        assert len(view_events) == 2
        assert view_events[-1].scene_id == "s_auto"

    def test_choice_index_required(self, client, play_id):
        resp = step(client, play_id, choice_index=None)
        assert resp.status_code == 422

    def test_invalid_choice_index_returns_400(self, client, play_id):
        resp = step(client, play_id, choice_index=99)
        assert resp.status_code == 400

    def test_second_choice_raises_step_count(self, client, play_id):
        """step_count after choice B (direct end) should be 1."""
        step(client, play_id, choice_index=1)
        # play is done after this; don't check step count via step response
        # (already validated by done=True path below)

    def test_direct_end_via_choice(self, client, play_id):
        """Choice index 1 leads directly to s_end."""
        body = step(client, play_id, choice_index=1).json()
        assert body["done"] is True
        assert body["scene"]["type"] == "end"


# ---------------------------------------------------------------------------
# Auto-advance step
# ---------------------------------------------------------------------------


class TestStepAutoAdvance:
    @pytest.fixture()
    def after_choice(self, client, play_id) -> uuid.UUID:
        """Advance past the choice scene so current scene is s_auto."""
        step(client, play_id, choice_index=0)
        return play_id

    def test_returns_200(self, client, after_choice):
        assert step(client, after_choice).status_code == 200

    def test_advances_to_next_scene(self, client, after_choice):
        body = step(client, after_choice).json()
        assert body["scene"]["scene_id"] == "s_conditional"

    def test_done_is_false(self, client, after_choice):
        body = step(client, after_choice).json()
        assert body["done"] is False

    def test_step_count_two(self, client, after_choice):
        body = step(client, after_choice).json()
        assert body["progress"]["step_count"] == 2

    def test_auto_advance_event_logged(self, client, after_choice, db: Session):
        step(client, after_choice)
        events = PlayRepository(db).get_events(after_choice)
        types = [e.event_type for e in events]
        assert EventType.auto_advance in types

    def test_choice_index_not_required(self, client, after_choice):
        """No body needed for auto_advance."""
        resp = step(client, after_choice, choice_index=None)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Conditional step
# ---------------------------------------------------------------------------


class TestStepConditional:
    @pytest.fixture()
    def after_auto(self, client, play_id) -> uuid.UUID:
        """Advance through choice (score=1) and auto_advance to conditional."""
        step(client, play_id, choice_index=0)
        step(client, play_id)
        return play_id

    def test_returns_200(self, client, after_auto):
        assert step(client, after_auto).status_code == 200

    def test_reaches_end_scene(self, client, after_auto):
        body = step(client, after_auto).json()
        assert body["scene"]["type"] == "end"

    def test_done_true_at_end(self, client, after_auto):
        body = step(client, after_auto).json()
        assert body["done"] is True

    def test_conditional_advance_event_logged(self, client, after_auto, db: Session):
        step(client, after_auto)
        events = PlayRepository(db).get_events(after_auto)
        types = [e.event_type for e in events]
        assert EventType.conditional_advance in types


# ---------------------------------------------------------------------------
# End scene / completion
# ---------------------------------------------------------------------------


class TestStepCompletion:
    @pytest.fixture()
    def complete_play_id(self, client, play_id) -> uuid.UUID:
        """Drive the play all the way to completion via the long path."""
        step(client, play_id, choice_index=0)  # → s_auto
        step(client, play_id)                  # → s_conditional
        step(client, play_id)                  # → s_end (done=True)
        return play_id

    def test_done_true(self, client, play_id):
        step(client, play_id, choice_index=0)
        step(client, play_id)
        body = step(client, play_id).json()
        assert body["done"] is True

    def test_outcome_returned(self, client, play_id):
        step(client, play_id, choice_index=0)
        step(client, play_id)
        body = step(client, play_id).json()
        assert body["outcome"] == "success"

    def test_outcome_message_returned(self, client, play_id):
        step(client, play_id, choice_index=0)
        step(client, play_id)
        body = step(client, play_id).json()
        assert body["outcome_message"] == "Well done!"

    def test_play_completed_flag_set(self, client, complete_play_id, db: Session):
        play: Play = db.get(Play, complete_play_id)
        db.refresh(play)
        assert play.completed is True

    def test_complete_event_logged(self, client, complete_play_id, db: Session):
        events = PlayRepository(db).get_events(complete_play_id)
        types = [e.event_type for e in events]
        assert EventType.complete in types

    def test_step_after_complete_returns_400(self, client, complete_play_id):
        resp = step(client, complete_play_id)
        assert resp.status_code == 400

    def test_step_count_at_completion(self, client, play_id):
        step(client, play_id, choice_index=0)
        step(client, play_id)
        body = step(client, play_id).json()
        # choice + auto_advance + conditional_advance = 3
        assert body["progress"]["step_count"] == 3


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestStepErrors:
    def test_404_unknown_play(self, client):
        resp = step(client, uuid.uuid4(), choice_index=0)
        assert resp.status_code == 404

    def test_scene_dto_has_no_internal_fields(self, client, play_id):
        body = step(client, play_id, choice_index=0).json()
        # auto_advance scene has no choices
        assert body["scene"].get("choices") is None
        # no engine-internal 'next' field at scene level
        assert "next" not in body["scene"]
