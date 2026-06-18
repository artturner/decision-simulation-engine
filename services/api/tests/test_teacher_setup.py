from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.admin import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.scenario import VersionStatus
from app.models.user import User, UserRole
from app.repositories.play_repo import PlayRepository
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository


SCENARIO_JSON: dict = {
    "metadata": {"title": "Published Scenario", "description": "Assignable."},
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
def other_teacher(db: Session) -> User:
    user = User(id=uuid.uuid4(), email="other@example.com", role=UserRole.teacher)
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
def roll(db: Session, teacher: User):
    created = RollRepository(db).create(
        teacher.id,
        "Period 1",
        ["Alice Adams", "Ben Brown", "Cara Cruz"],
    )
    db.flush()
    return created


def _scenario(db: Session, slug: str, status: VersionStatus, owner_id=None):
    repo = ScenarioRepository(db)
    scenario = repo.create_scenario(slug, slug.title(), "")
    scenario.owner_id = owner_id
    version = repo.create_version(scenario.id, SCENARIO_JSON, status=status)
    db.flush()
    return scenario, version


class TestPublishedScenarios:
    def test_includes_global_published_scenarios(self, client, db: Session):
        scenario, version = _scenario(db, "global-published", VersionStatus.published)
        resp = client.get("/api/v1/teacher/scenarios/published")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["id"] == str(scenario.id)
        assert body[0]["published_version_id"] == str(version.id)

    def test_excludes_draft_scenarios(self, client, db: Session):
        _scenario(db, "draft-only", VersionStatus.draft)
        resp = client.get("/api/v1/teacher/scenarios/published")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_excludes_other_teacher_owned_scenarios(
        self, client, db: Session, other_teacher: User
    ):
        _scenario(
            db,
            "other-owned",
            VersionStatus.published,
            owner_id=other_teacher.id,
        )
        resp = client.get("/api/v1/teacher/scenarios/published")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRollAssignments:
    def test_teacher_lists_assignments_for_owned_roll(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "assigned", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        db.flush()

        resp = client.get(f"/api/v1/teacher/rolls/{roll.id}/scenarios")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["scenario_id"] == str(scenario.id)
        assert body[0]["slug"] == "assigned"
        assert body[0]["visible"] is True

    def test_teacher_cannot_list_other_teacher_roll(
        self, client, db: Session, other_teacher: User
    ):
        other_roll = RollRepository(db).create(other_teacher.id, "Other", ["Student"])
        db.flush()
        resp = client.get(f"/api/v1/teacher/rolls/{other_roll.id}/scenarios")
        assert resp.status_code == 404


class TestRollGradebook:
    def test_includes_roster_students_with_no_attempts(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "gradebook-empty", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 200
        students = resp.json()["students"]
        assert [student["student_name"] for student in students] == [
            "Alice Adams",
            "Ben Brown",
            "Cara Cruz",
        ]
        assert students[0]["status"] == "not_started"

    def test_reports_in_progress_completed_and_reflection(
        self, client, db: Session, roll
    ):
        scenario, version = _scenario(db, "gradebook-full", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        repo = PlayRepository(db)

        in_progress = repo.create_play(
            version.id,
            learner_label="Alice Adams",
            class_roll_id=roll.id,
        )
        completed = repo.create_play(
            version.id,
            learner_label="Ben Brown",
            class_roll_id=roll.id,
        )
        repo.complete_play(completed.id, outcome="ok")
        repo.add_reflection(
            completed.id,
            responses_json={"reflection_1": "I learned."},
            student_name="Ben Brown",
        )
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 200
        students = {student["student_name"]: student for student in resp.json()["students"]}

        assert students["Alice Adams"]["status"] == "in_progress"
        assert students["Alice Adams"]["in_progress_play_id"] == str(in_progress.id)
        assert students["Ben Brown"]["status"] == "completed"
        assert students["Ben Brown"]["submitted_count"] == 1
        assert students["Ben Brown"]["best_attempt"]["play_id"] == str(completed.id)
        assert students["Ben Brown"]["attempts"][0]["reflection"]["responses"] == {
            "reflection_1": "I learned."
        }

    def test_best_attempt_is_latest_completed_attempt(self, client, db: Session, roll):
        scenario, version = _scenario(db, "gradebook-best", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        repo = PlayRepository(db)

        first = repo.create_play(
            version.id,
            learner_label="Ben Brown",
            class_roll_id=roll.id,
        )
        repo.complete_play(first.id, outcome="first")
        second = repo.create_play(
            version.id,
            learner_label="Ben Brown",
            class_roll_id=roll.id,
        )
        repo.complete_play(second.id, outcome="second")
        repo.add_reflection(
            second.id,
            responses_json={"reflection_1": "Latest answer."},
            student_name="Ben Brown",
        )
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )

        assert resp.status_code == 200
        students = {student["student_name"]: student for student in resp.json()["students"]}
        assert students["Ben Brown"]["submitted_count"] == 2
        assert students["Ben Brown"]["best_attempt"]["play_id"] == str(second.id)
        assert students["Ben Brown"]["best_attempt"]["outcome"] == "second"
        assert students["Ben Brown"]["best_attempt"]["reflection"]["responses"] == {
            "reflection_1": "Latest answer."
        }

    def test_exports_roll_gradebook_csv(self, client, db: Session, roll):
        scenario, version = _scenario(db, "gradebook-export", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id,
            learner_label="Ben Brown",
            class_roll_id=roll.id,
        )
        repo.complete_play(play.id, outcome="ok")
        repo.add_reflection(
            play.id,
            responses_json={"reflection_1": "I learned."},
            student_name="Ben Brown",
        )
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook.csv"
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "student_name,status,submitted_count" in resp.text
        assert "Alice Adams,not_started,0" in resp.text
        assert "Ben Brown,completed,1" in resp.text
        assert "I learned." in resp.text

    def test_requires_scenario_assigned_to_roll(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "not-assigned", VersionStatus.published)
        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 404

    def test_teacher_cannot_grade_other_teacher_roll(
        self, client, db: Session, other_teacher: User
    ):
        other_roll = RollRepository(db).create(other_teacher.id, "Other", ["Student"])
        scenario, _version = _scenario(db, "other-grade", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, other_roll.id, visible=True)
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{other_roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 404
