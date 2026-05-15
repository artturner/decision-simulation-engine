"""
Integration tests for POST /api/v1/public/plays/{play_id}/back.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.

Blueprint requirements covered:
- 404 for unknown play
- 400 when already at the start (no step events exist)
- After back from a choice step: returns previous scene, step_count
  decrements, choices_made removes the undone choice, done=False
- After back from an auto_advance step: returns the auto_advance scene
- Multiple consecutive back calls work correctly
- Back from a completed play: resets play.completed and allows replay
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
# Scenario fixture
# ---------------------------------------------------------------------------

# Three-path scenario that exercises every relevant step type:
#   s1 (choice) → (0) → s2 (auto_advance) → s3 (end, long path)
#               → (1) → s3 (end, short path)
STANDARD_JSON: dict = {
    "metadata": {
        "title": "Back Test",
        "completion_tracking": False,
    },
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "reflection_questions": [],
    "reflection_prompts": [],
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Choose",
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


def _seed_and_start(client, db: Session, slug: str, scenario_json: dict) -> uuid.UUID:
    """Seed a published scenario and start a play. Return the play_id."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario(slug, "Test")
    v = repo.create_version(s.id, scenario_json, status=VersionStatus.published)
    db.flush()

    resp = client.post(
        "/api/v1/public/plays/start",
        json={"scenario_version_id": str(v.id)},
    )
    assert resp.status_code == 201
    return uuid.UUID(resp.json()["play_id"])


@pytest.fixture()
def play_id(client, db: Session) -> uuid.UUID:
    return _seed_and_start(client, db, "back-test", STANDARD_JSON)


def step(client, play_id: uuid.UUID, choice_index=None):
    body = {} if choice_index is None else {"choice_index": choice_index}
    return client.post(f"/api/v1/public/plays/{play_id}/step", json=body)


def back(client, play_id: uuid.UUID):
    return client.post(f"/api/v1/public/plays/{play_id}/back")


# ---------------------------------------------------------------------------
# Basic shape and error cases
# ---------------------------------------------------------------------------


class TestBackBasic:
    def test_404_for_unknown_play(self, client):
        assert back(client, uuid.uuid4()).status_code == 404

    def test_400_when_at_start(self, client, play_id):
        """No steps taken yet — cannot go back further."""
        assert back(client, play_id).status_code == 400

    def test_400_error_message(self, client, play_id):
        body = back(client, play_id).json()
        assert "start" in body["detail"].lower()

    def test_returns_200_after_step(self, client, play_id):
        step(client, play_id, choice_index=0)
        assert back(client, play_id).status_code == 200

    def test_play_id_in_response(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert uuid.UUID(body["play_id"]) == play_id

    def test_done_always_false(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert body["done"] is False

    def test_no_auth_required(self, client, play_id):
        """Public endpoint — no X-Admin-Key needed."""
        step(client, play_id, choice_index=0)
        assert back(client, play_id).status_code == 200


# ---------------------------------------------------------------------------
# Back after a choice step
# ---------------------------------------------------------------------------


class TestBackAfterChoice:
    def test_scene_reverts_to_start(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert body["scene"]["scene_id"] == "s1"

    def test_scene_type_reverts(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert body["scene"]["type"] == "choice"

    def test_step_count_reverts_to_zero(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert body["progress"]["step_count"] == 0

    def test_choices_made_cleared(self, client, play_id):
        step(client, play_id, choice_index=0)
        body = back(client, play_id).json()
        assert body["progress"]["choices_made"] == []

    def test_choose_event_removed(self, client, play_id, db: Session):
        step(client, play_id, choice_index=0)
        back(client, play_id)
        events = PlayRepository(db).get_events(play_id)
        types = [e.event_type for e in events]
        assert EventType.choose not in types

    def test_only_start_events_remain(self, client, play_id, db: Session):
        """After backing from one step, only start + view_scene(s1) remain."""
        step(client, play_id, choice_index=0)
        back(client, play_id)
        events = PlayRepository(db).get_events(play_id)
        assert len(events) == 2  # seq=0 start, seq=1 view_scene


# ---------------------------------------------------------------------------
# Back after an auto_advance step
# ---------------------------------------------------------------------------


class TestBackAfterAutoAdvance:
    @pytest.fixture()
    def at_auto(self, client, play_id) -> uuid.UUID:
        """Advance to s2 (auto_advance)."""
        step(client, play_id, choice_index=0)
        return play_id

    @pytest.fixture()
    def after_auto_step(self, client, at_auto) -> uuid.UUID:
        """Step through s2 so current scene is s3 (end); then go back."""
        # We can't step from s3 (end) — step into s3 happens via the auto scene
        step(client, at_auto)  # auto_advance step: s2 → s3 (end, triggers complete)
        return at_auto

    def test_back_from_auto_returns_200(self, client, at_auto):
        step(client, at_auto)  # auto_advance
        assert back(client, at_auto).status_code == 200

    def test_back_from_auto_reverts_to_auto_scene(self, client, at_auto):
        """Undoing the auto_advance step puts us back at s2."""
        step(client, at_auto)  # auto_advance: s2 → s3 (completes play)
        body = back(client, at_auto).json()
        assert body["scene"]["scene_id"] == "s2"

    def test_back_from_auto_step_count(self, client, at_auto):
        step(client, at_auto)  # step_count was 2 (choose + auto_advance)
        body = back(client, at_auto).json()
        # After undoing auto_advance, step_count drops to 1 (only choose remains)
        assert body["progress"]["step_count"] == 1

    def test_back_from_auto_choices_preserved(self, client, at_auto):
        step(client, at_auto)
        body = back(client, at_auto).json()
        # The earlier choice ("Long way") should still be in choices_made
        assert body["progress"]["choices_made"] == ["Long way"]


# ---------------------------------------------------------------------------
# Back from a completed play
# ---------------------------------------------------------------------------


class TestBackFromCompleted:
    @pytest.fixture()
    def completed_play(self, client, play_id) -> uuid.UUID:
        """Drive play to completion via the short cut (choice 1 → s3)."""
        step(client, play_id, choice_index=1)
        return play_id

    def test_back_from_done_returns_200(self, client, completed_play):
        assert back(client, completed_play).status_code == 200

    def test_back_resets_done_to_false(self, client, completed_play):
        body = back(client, completed_play).json()
        assert body["done"] is False

    def test_play_completed_flag_reset(self, client, completed_play, db: Session):
        back(client, completed_play)
        play: Play = db.get(Play, completed_play)
        db.refresh(play)
        assert play.completed is False

    def test_play_outcome_cleared(self, client, completed_play, db: Session):
        back(client, completed_play)
        play: Play = db.get(Play, completed_play)
        db.refresh(play)
        assert play.outcome is None
        assert play.outcome_message is None

    def test_scene_reverts_before_end(self, client, completed_play):
        """After back, the scene should be the choice scene again (s1)."""
        body = back(client, completed_play).json()
        assert body["scene"]["scene_id"] == "s1"

    def test_can_step_after_back_from_done(self, client, completed_play):
        """After going back from a completed play, a new step should work."""
        back(client, completed_play)
        resp = step(client, completed_play, choice_index=0)
        assert resp.status_code == 200
        assert resp.json()["scene"]["scene_id"] == "s2"

    def test_complete_event_removed(self, client, completed_play, db: Session):
        back(client, completed_play)
        events = PlayRepository(db).get_events(completed_play)
        types = [e.event_type for e in events]
        assert EventType.complete not in types


# ---------------------------------------------------------------------------
# Multiple consecutive back calls
# ---------------------------------------------------------------------------


class TestBackMultipleTimes:
    def test_two_backs_returns_to_start(self, client, play_id):
        """Two steps forward → two backs → start scene."""
        step(client, play_id, choice_index=0)  # s1 → s2
        step(client, play_id)                  # s2 → s3 (complete)
        back(client, play_id)                  # s3 → s2
        body = back(client, play_id).json()    # s2 → s1
        assert body["scene"]["scene_id"] == "s1"
        assert body["progress"]["step_count"] == 0
        assert body["progress"]["choices_made"] == []

    def test_third_back_returns_400(self, client, play_id):
        """After returning to start, another back is refused."""
        step(client, play_id, choice_index=0)
        step(client, play_id)
        back(client, play_id)
        back(client, play_id)  # now at start
        assert back(client, play_id).status_code == 400

    def test_back_then_different_choice(self, client, play_id):
        """Going back and choosing differently should change the path."""
        step(client, play_id, choice_index=0)   # chose "Long way"
        back(client, play_id)                    # undo
        body = step(client, play_id, choice_index=1).json()  # choose "Short cut"
        assert body["done"] is True
        assert body["scene"]["scene_id"] == "s3"
        assert body["progress"]["choices_made"] == ["Short cut"]
