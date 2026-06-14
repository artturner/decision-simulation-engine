from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.admin import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole
from app.repositories.play_repo import PlayRepository
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.models.scenario import VersionStatus


SCENARIO_JSON: dict = {
    "metadata": {"title": "Class Scenario", "description": "For class use."},
    "variables": {},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Start",
            "choices": [{"text": "Go", "next": "s2"}],
        },
        "s2": {
            "type": "end",
            "title": "Done",
            "outcome": "ok",
            "outcome_message": "",
        },
    },
}


@pytest.fixture()
def teacher(db: Session) -> User:
    user = User(id=uuid.uuid4(), email="teacher@example.com", role=UserRole.teacher)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client(db: Session, teacher: User):
    def override_get_db():
        yield db

    def override_current_user():
        return teacher

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def class_roll(db: Session, teacher: User):
    roll = RollRepository(db).create(
        teacher.id,
        "Period 3",
        ["Alice Adams", "Ben Brown"],
    )
    db.flush()
    return roll


def _published_scenario(db: Session, slug: str = "class-scenario"):
    repo = ScenarioRepository(db)
    scenario = repo.create_scenario(slug, "Class Scenario")
    version = repo.create_version(scenario.id, SCENARIO_JSON, status=VersionStatus.published)
    db.flush()
    return scenario, version


def _assign_visible(db: Session, class_roll, *, slug: str = "class-scenario", visible: bool = True):
    scenario, version = _published_scenario(db, slug)
    RollRepository(db).assign_scenario(
        scenario.id,
        class_roll.id,
        visible=visible,
        sort_order=1,
    )
    db.flush()
    return scenario, version


class TestTeacherRollJoinCode:
    def test_create_roll_response_includes_join_code(self, client):
        resp = client.post(
            "/api/v1/teacher/rolls",
            json={"name": "Period 4", "student_names": ["Alice"]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert len(body["join_code"]) == 6
        assert body["join_code"] == body["join_code"].upper()

    def test_repository_assigns_join_code(self, class_roll):
        assert len(class_roll.join_code) == 6
        assert class_roll.join_code == class_roll.join_code.upper()


class TestClassCodeLookup:
    def test_lookup_by_code_returns_class_picker(self, client, db: Session, class_roll):
        _assign_visible(db, class_roll)
        resp = client.get(f"/api/v1/public/classes/code/{class_roll.join_code}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["roll_id"] == str(class_roll.id)
        assert body["join_code"] == class_roll.join_code
        assert body["student_names"] == ["Alice Adams", "Ben Brown"]
        assert len(body["scenarios"]) == 1

    def test_lookup_is_case_insensitive(self, client, class_roll):
        resp = client.get(f"/api/v1/public/classes/code/{class_roll.join_code.lower()}")
        assert resp.status_code == 200

    def test_unknown_code_returns_404(self, client):
        resp = client.get("/api/v1/public/classes/code/NOPE99")
        assert resp.status_code == 404


class TestStudentStatus:
    def test_rejects_name_not_on_roll(self, client, class_roll):
        resp = client.get(
            f"/api/v1/public/classes/code/{class_roll.join_code}/students/Not%20Here"
        )
        assert resp.status_code == 422

    def test_returns_visible_scenarios_only(self, client, db: Session, class_roll):
        _assign_visible(db, class_roll, slug="visible-scenario", visible=True)
        _assign_visible(db, class_roll, slug="hidden-scenario", visible=False)
        resp = client.get(
            f"/api/v1/public/classes/code/{class_roll.join_code}/students/Alice%20Adams"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["student_name"] == "Alice Adams"
        assert [s["slug"] for s in body["scenarios"]] == ["visible-scenario"]

    def test_returns_in_progress_play_id(self, client, db: Session, class_roll):
        _scenario, version = _assign_visible(db, class_roll)
        play = PlayRepository(db).create_play(
            version.id,
            learner_label="Alice Adams",
            class_roll_id=class_roll.id,
        )
        db.flush()

        resp = client.get(
            f"/api/v1/public/classes/code/{class_roll.join_code}/students/Alice%20Adams"
        )
        scenario = resp.json()["scenarios"][0]
        assert scenario["in_progress_play_id"] == str(play.id)
        assert scenario["submitted_count"] == 0
        assert scenario["latest_submitted_play_id"] is None

    def test_completed_play_is_not_resume_target(self, client, db: Session, class_roll):
        _scenario, version = _assign_visible(db, class_roll)
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id,
            learner_label="Alice Adams",
            class_roll_id=class_roll.id,
        )
        repo.complete_play(play.id, outcome="ok")
        db.flush()

        resp = client.get(
            f"/api/v1/public/classes/code/{class_roll.join_code}/students/Alice%20Adams"
        )
        scenario = resp.json()["scenarios"][0]
        assert scenario["in_progress_play_id"] is None
        assert scenario["submitted_count"] == 1
        assert scenario["latest_submitted_play_id"] == str(play.id)

    def test_new_play_after_completed_attempt_creates_second_attempt(
        self, client, db: Session, class_roll
    ):
        _scenario, version = _assign_visible(db, class_roll)
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id,
            learner_label="Alice Adams",
            class_roll_id=class_roll.id,
        )
        repo.complete_play(play.id, outcome="ok")
        db.flush()

        resp = client.post(
            "/api/v1/public/plays/start",
            json={
                "scenario_version_id": str(version.id),
                "learner_label": "Alice Adams",
                "class_roll_id": str(class_roll.id),
            },
        )
        assert resp.status_code == 201
        new_play_id = uuid.UUID(resp.json()["play_id"])
        assert new_play_id != play.id
        assert repo.count_completed_attempts(
            class_roll_id=class_roll.id,
            learner_label="Alice Adams",
            scenario_version_id=version.id,
        ) == 1
        in_progress = repo.find_in_progress(
            class_roll_id=class_roll.id,
            learner_label="Alice Adams",
            scenario_version_id=version.id,
        )
        assert in_progress is not None
        assert in_progress.id == new_play_id
