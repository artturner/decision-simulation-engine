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
    user = User(
        id=uuid.uuid4(),
        email="teacher@example.com",
        role=UserRole.teacher,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def other_teacher(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        role=UserRole.teacher,
        is_approved=True,
    )
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
        by_slug = {item["slug"]: item for item in resp.json()}
        assert "global-published" in by_slug
        assert by_slug["global-published"]["id"] == str(scenario.id)
        assert by_slug["global-published"]["published_version_id"] == str(version.id)

    def test_excludes_draft_scenarios(self, client, db: Session):
        _scenario(db, "draft-only", VersionStatus.draft)
        resp = client.get("/api/v1/teacher/scenarios/published")
        assert resp.status_code == 200
        assert "draft-only" not in {item["slug"] for item in resp.json()}

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
        assert "other-owned" not in {item["slug"] for item in resp.json()}


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

    def test_assignment_defaults_to_standard_difficulty(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "diff-default", VersionStatus.published)
        db.flush()

        resp = client.post(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios",
            json={"scenario_id": str(scenario.id), "visible": True},
        )
        assert resp.status_code == 201
        assert resp.json()["grading_difficulty"] == "standard"

    def test_teacher_sets_grading_difficulty(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "diff-set", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        db.flush()

        resp = client.patch(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}",
            json={"grading_difficulty": "lenient"},
        )
        assert resp.status_code == 200
        assert resp.json()["grading_difficulty"] == "lenient"

        listed = client.get(f"/api/v1/teacher/rolls/{roll.id}/scenarios")
        assert listed.json()[0]["grading_difficulty"] == "lenient"

    def test_rejects_invalid_grading_difficulty(self, client, db: Session, roll):
        scenario, _version = _scenario(db, "diff-bad", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        db.flush()

        resp = client.patch(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}",
            json={"grading_difficulty": "impossible"},
        )
        assert resp.status_code == 422


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

    def test_matches_plays_despite_whitespace_differences(
        self, client, db: Session, roll
    ):
        """A legacy play stored with a double-space label must still group
        under the roster student (labels are compared whitespace-normalized)."""
        scenario, version = _scenario(db, "gradebook-whitespace", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id,
            learner_label="Alice  Adams",  # legacy double space
            class_roll_id=roll.id,
        )
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 200
        body = resp.json()
        students = {student["student_name"]: student for student in body["students"]}
        assert students["Alice Adams"]["status"] == "in_progress"
        assert students["Alice Adams"]["in_progress_play_id"] == str(play.id)
        assert body["unmatched"] == []

    def test_matches_double_space_roster_entry_to_normalized_play(
        self, client, db: Session, teacher: User
    ):
        """The inverse: the roster still holds the double-space spelling but
        new plays store the normalized label."""
        dirty_roll = RollRepository(db).create(teacher.id, "Period 9", ["Jalen  Doe"])
        scenario, version = _scenario(db, "gradebook-dirty-roster", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, dirty_roll.id, visible=True)
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id,
            learner_label="Jalen Doe",
            class_roll_id=dirty_roll.id,
        )
        repo.complete_play(play.id, outcome="ok")
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{dirty_roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["students"][0]["student_name"] == "Jalen  Doe"
        assert body["students"][0]["status"] == "completed"
        assert body["unmatched"] == []

    def test_lists_unmatched_plays_after_roster_rename(
        self, client, db: Session, roll
    ):
        """Plays whose label matches no current roster name (e.g. the student
        was renamed) must be listed, not silently dropped."""
        scenario, version = _scenario(db, "gradebook-unmatched", VersionStatus.published)
        RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True)
        repo = PlayRepository(db)
        orphan = repo.create_play(
            version.id,
            learner_label="Old Name",
            class_roll_id=roll.id,
        )
        repo.complete_play(orphan.id, outcome="ok")
        matched = repo.create_play(
            version.id,
            learner_label="Ben Brown",
            class_roll_id=roll.id,
        )
        db.flush()

        resp = client.get(
            f"/api/v1/teacher/rolls/{roll.id}/scenarios/{scenario.id}/gradebook"
        )
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["unmatched"]) == 1
        entry = body["unmatched"][0]
        assert entry["play_id"] == str(orphan.id)
        assert entry["label"] == "Old Name"
        assert entry["completed"] is True
        assert entry["started_at"]

        students = {student["student_name"]: student for student in body["students"]}
        assert students["Ben Brown"]["in_progress_play_id"] == str(matched.id)
        assert all(
            attempt["play_id"] != str(orphan.id)
            for student in body["students"]
            for attempt in student["attempts"]
        )

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

    def test_scenario_level_gradebook_route_is_gone(self, client, db: Session):
        """The unscoped /teacher/scenarios/{id}/gradebook endpoint leaked plays
        across all teachers' rolls and was removed; only the roll-scoped
        gradebook may exist."""
        scenario, _version = _scenario(db, "no-global-gradebook", VersionStatus.published)
        resp = client.get(f"/api/v1/teacher/scenarios/{scenario.id}/gradebook")
        assert resp.status_code == 404


@pytest.fixture()
def pending_teacher(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="pending@example.com",
        role=UserRole.teacher,
        is_approved=False,
    )
    db.add(user)
    db.flush()
    return user


class TestApprovalGate:
    def test_unapproved_teacher_blocked(self, client, pending_teacher: User):
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: pending_teacher
        resp = client.get("/api/v1/teacher/rolls")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Account pending approval."

    def test_me_reports_pending_state(self, client, pending_teacher: User):
        from app.main import app

        app.dependency_overrides[get_current_user] = lambda: pending_teacher
        resp = client.get("/api/v1/teacher/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "pending@example.com"
        assert body["is_approved"] is False

    def test_me_reports_approved_state(self, client, teacher: User):
        resp = client.get("/api/v1/teacher/me")
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is True

    def test_admin_can_approve_and_revoke(self, client, pending_teacher: User):
        from app.core.config import settings

        headers = {"X-Admin-Key": settings.ADMIN_API_KEY}

        resp = client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        listed = {u["id"]: u for u in resp.json()}
        assert listed[str(pending_teacher.id)]["is_approved"] is False

        resp = client.post(
            f"/api/v1/admin/users/{pending_teacher.id}/approve", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is True

        resp = client.post(
            f"/api/v1/admin/users/{pending_teacher.id}/revoke", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["is_approved"] is False

    def test_admin_users_requires_key(self, client):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 403
