"""
Integration tests for POST /api/v1/public/plays/{play_id}/restart.

Restart must create a NEW play of the same scenario version while carrying
over the source play's learner_label and class_roll_id — the fix for the
attribution leak where the player's Restart button routed through the
scenario landing page and produced an anonymous play invisible to the
roll gradebook.

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
from app.models.scenario import VersionStatus
from app.models.user import User, UserRole
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository

CHOICE_JSON: dict = {
    "metadata": {"title": "Restart Test"},
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
    repo = ScenarioRepository(db)
    s = repo.create_scenario("restart-test", "Restart Test")
    v = repo.create_version(s.id, CHOICE_JSON, status=VersionStatus.published)
    db.flush()
    return v.id


@pytest.fixture()
def class_roll(db: Session):
    teacher = User(id=uuid.uuid4(), email="restart-teacher@example.com", role=UserRole.teacher)
    db.add(teacher)
    db.flush()
    roll = RollRepository(db).create(teacher.id, "Period 1", ["Alice Adams", "Ben Brown"])
    db.flush()
    return roll


def _start(client, version_id, learner_label=None, class_roll_id=None) -> dict:
    body: dict = {"scenario_version_id": str(version_id)}
    if learner_label is not None:
        body["learner_label"] = learner_label
    if class_roll_id is not None:
        body["class_roll_id"] = str(class_roll_id)
    resp = client.post("/api/v1/public/plays/start", json=body)
    assert resp.status_code == 201
    return resp.json()


def _restart(client, play_id):
    return client.post(f"/api/v1/public/plays/{play_id}/restart")


class TestRestartIdentity:
    def test_carries_learner_label_and_roll(self, client, published_version_id, class_roll):
        started = _start(
            client, published_version_id,
            learner_label="Alice Adams", class_roll_id=class_roll.id,
        )
        resp = _restart(client, started["play_id"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["learner_label"] == "Alice Adams"
        assert body["class_roll_id"] == str(class_roll.id)

    def test_creates_new_play(self, client, published_version_id, class_roll):
        started = _start(
            client, published_version_id,
            learner_label="Alice Adams", class_roll_id=class_roll.id,
        )
        body = _restart(client, started["play_id"]).json()
        assert body["play_id"] != started["play_id"]

    def test_anonymous_play_restarts_anonymous(self, client, published_version_id):
        started = _start(client, published_version_id)
        body = _restart(client, started["play_id"]).json()
        assert body["learner_label"] is None
        assert body["class_roll_id"] is None


class TestRestartState:
    def test_new_play_is_at_start_scene(self, client, published_version_id):
        started = _start(client, published_version_id)
        # Advance the source play past the start scene first.
        step = client.post(
            f"/api/v1/public/plays/{started['play_id']}/step",
            json={"choice_index": 0},
        )
        assert step.status_code == 200
        body = _restart(client, started["play_id"]).json()
        assert body["scene"]["scene_id"] == "s1"
        assert body["progress"]["step_count"] == 0
        assert body["progress"]["choices_made"] == []
        assert body["done"] is False

    def test_404_for_unknown_play(self, client):
        assert _restart(client, uuid.uuid4()).status_code == 404
