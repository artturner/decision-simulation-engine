"""
Integration tests for POST /api/v1/public/plays/start.

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
from app.models.play import Event, EventType
from app.models.scenario import VersionStatus
from app.repositories.play_repo import PlayRepository
from app.repositories.scenario_repo import ScenarioRepository

# ---------------------------------------------------------------------------
# Scenario fixtures
# ---------------------------------------------------------------------------

CHOICE_JSON: dict = {
    "metadata": {"title": "Start Test"},
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "First Scene",
            "narration": "What do you do?",
            "description": "A crossroads.",
            "choices": [
                {"text": "Go left", "next": "s2", "effects": {"score": 1}},
                {"text": "Go right", "next": "s2"},
            ],
        },
        "s2": {
            "type": "end",
            "title": "The End",
            "outcome": "success",
            "outcome_message": "Done.",
        },
    },
}

IMAGE_JSON: dict = {
    "metadata": {"title": "Image Test"},
    "variables": {},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "auto_advance",
            "title": "Scene with Image",
            "image": "scenes/intro.jpg",
            "next": "s2",
        },
        "s2": {
            "type": "end",
            "title": "Done",
            "outcome": "ok",
            "outcome_message": "",
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
def published_version_id(db: Session) -> uuid.UUID:
    """Seed a published scenario version and return its ID."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("play-test", "Play Test")
    v = repo.create_version(s.id, CHOICE_JSON, status=VersionStatus.published)
    db.flush()
    return v.id


@pytest.fixture()
def draft_version_id(db: Session) -> uuid.UUID:
    """Seed a draft-only scenario version and return its ID."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("draft-play", "Draft Play")
    v = repo.create_version(s.id, CHOICE_JSON, status=VersionStatus.draft)
    db.flush()
    return v.id


@pytest.fixture()
def image_version_id(db: Session) -> uuid.UUID:
    """Seed a scenario with an image field and return the version ID."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("image-test", "Image Test")
    v = repo.create_version(s.id, IMAGE_JSON, status=VersionStatus.published)
    db.flush()
    return v.id


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def start(client, version_id, learner_label=None) -> dict:
    body: dict = {"scenario_version_id": str(version_id)}
    if learner_label is not None:
        body["learner_label"] = learner_label
    return client.post("/api/v1/public/plays/start", json=body)


# ---------------------------------------------------------------------------
# Status and top-level shape
# ---------------------------------------------------------------------------


class TestStartPlayStatus:
    def test_returns_201(self, client, published_version_id):
        assert start(client, published_version_id).status_code == 201

    def test_response_has_play_id(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert uuid.UUID(body["play_id"])

    def test_response_has_scenario_version_id(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert uuid.UUID(body["scenario_version_id"]) == published_version_id

    def test_404_for_unknown_version(self, client):
        resp = start(client, uuid.uuid4())
        assert resp.status_code == 404

    def test_404_for_draft_version(self, client, draft_version_id):
        resp = start(client, draft_version_id)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scene DTO
# ---------------------------------------------------------------------------


class TestStartPlayScene:
    def test_scene_id_is_start_scene(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["scene"]["scene_id"] == "s1"

    def test_scene_type(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["scene"]["type"] == "choice"

    def test_scene_title(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["scene"]["title"] == "First Scene"

    def test_scene_narration(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["scene"]["narration"] == "What do you do?"

    def test_choices_count(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert len(body["scene"]["choices"]) == 2

    def test_choice_text(self, client, published_version_id):
        body = start(client, published_version_id).json()
        texts = [c["text"] for c in body["scene"]["choices"]]
        assert texts == ["Go left", "Go right"]

    def test_choices_do_not_expose_next_or_effects(self, client, published_version_id):
        """Internal state-machine fields must be stripped from choice objects."""
        body = start(client, published_version_id).json()
        for choice in body["scene"]["choices"]:
            assert "next" not in choice
            assert "effects" not in choice

    def test_no_image_url_when_none(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["scene"]["image_url"] is None

    def test_image_url_constructed(self, client, image_version_id, db: Session):
        """image_url must be MEDIA_BASE_URL / slug / version_number / relative_path."""
        from app.core.config import settings

        body = start(client, image_version_id).json()
        expected = f"{settings.MEDIA_BASE_URL}/image-test/1/scenes/intro.jpg"
        assert body["scene"]["image_url"] == expected


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


class TestStartPlayProgress:
    def test_step_count_is_zero(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["progress"]["step_count"] == 0

    def test_choices_made_is_empty(self, client, published_version_id):
        body = start(client, published_version_id).json()
        assert body["progress"]["choices_made"] == []


# ---------------------------------------------------------------------------
# Learner label
# ---------------------------------------------------------------------------


class TestStartPlayLearnerLabel:
    def test_learner_label_stored(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id, learner_label="Alice")
        play_id = uuid.UUID(resp.json()["play_id"])
        play = PlayRepository(db).get_play(play_id)
        assert play.learner_label == "Alice"

    def test_learner_label_defaults_none(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id)
        play_id = uuid.UUID(resp.json()["play_id"])
        play = PlayRepository(db).get_play(play_id)
        assert play.learner_label is None


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


class TestStartPlayEvents:
    def test_start_event_at_seq_zero(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id)
        play_id = uuid.UUID(resp.json()["play_id"])
        events = PlayRepository(db).get_events(play_id)
        assert events[0].seq == 0
        assert events[0].event_type == EventType.start

    def test_view_scene_event_at_seq_one(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id)
        play_id = uuid.UUID(resp.json()["play_id"])
        events = PlayRepository(db).get_events(play_id)
        assert events[1].seq == 1
        assert events[1].event_type == EventType.view_scene

    def test_view_scene_records_scene_id(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id)
        play_id = uuid.UUID(resp.json()["play_id"])
        events = PlayRepository(db).get_events(play_id)
        view_event = next(e for e in events if e.event_type == EventType.view_scene)
        assert view_event.scene_id == "s1"

    def test_two_events_total(self, client, published_version_id, db: Session):
        resp = start(client, published_version_id)
        play_id = uuid.UUID(resp.json()["play_id"])
        events = PlayRepository(db).get_events(play_id)
        assert len(events) == 2
