"""Teacher-side claim-code management: lazy creation, regenerate, roster sync."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.admin import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.claim import StudentClaimCode
from app.models.user import User, UserRole
from app.repositories.roll_repo import RollRepository


@pytest.fixture()
def teacher(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="codes-teacher@example.com",
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
        email="codes-other@example.com",
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
    roll = RollRepository(db).create(teacher.id, "Period 6", ["Lee, Amy", "Ng, Ben"])
    db.flush()
    return roll


def list_codes(client, roll_id):
    return client.get(f"/api/v1/teacher/rolls/{roll_id}/claim-codes")


class TestListClaimCodes:
    def test_lazily_creates_in_roster_order(self, client, roll):
        resp = list_codes(client, roll.id)
        assert resp.status_code == 200
        body = resp.json()
        assert [c["student_name"] for c in body] == ["Lee, Amy", "Ng, Ben"]
        for c in body:
            assert len(c["code"]) == 8
            assert c["last_claimed_at"] is None
            assert c["claim_count"] == 0

    def test_second_fetch_is_idempotent(self, client, roll):
        first = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        second = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        assert first == second

    def test_cross_owner_404(self, client, db, other_teacher):
        foreign = RollRepository(db).create(other_teacher.id, "Not mine", ["X Y"])
        db.flush()
        assert list_codes(client, foreign.id).status_code == 404


class TestRegenerate:
    def regen(self, client, roll_id, student_name=None):
        return client.post(
            f"/api/v1/teacher/rolls/{roll_id}/claim-codes/regenerate",
            json={"student_name": student_name},
        )

    def test_single_student_changes_only_their_code(self, client, roll):
        before = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        after = {c["student_name"]: c["code"]
                 for c in self.regen(client, roll.id, "Lee, Amy").json()}
        assert after["Lee, Amy"] != before["Lee, Amy"]
        assert after["Ng, Ben"] == before["Ng, Ben"]

    def test_all_students(self, client, roll):
        before = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        after = {c["student_name"]: c["code"] for c in self.regen(client, roll.id).json()}
        assert set(after) == set(before)
        assert all(after[name] != before[name] for name in before)


class TestRosterSync:
    def patch_roster(self, client, roll_id, names):
        return client.patch(
            f"/api/v1/teacher/rolls/{roll_id}", json={"student_names": names}
        )

    def test_removed_name_loses_its_row(self, client, db, roll):
        list_codes(client, roll.id)
        assert self.patch_roster(client, roll.id, ["Lee, Amy"]).status_code == 200
        rows = db.query(StudentClaimCode).filter_by(class_roll_id=roll.id).all()
        assert [r.student_name for r in rows] == ["Lee, Amy"]

    def test_respelling_keeps_row_and_code(self, client, db, roll):
        before = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        # Name-order flip is a formatting fix, not a different student.
        assert self.patch_roster(client, roll.id, ["Amy Lee", "Ng, Ben"]).status_code == 200
        after = {c["student_name"]: c["code"] for c in list_codes(client, roll.id).json()}
        assert after["Amy Lee"] == before["Lee, Amy"]

    def test_added_name_appears_on_next_fetch(self, client, db, roll):
        list_codes(client, roll.id)
        self.patch_roster(client, roll.id, ["Lee, Amy", "Ng, Ben", "New Kid"])
        names = [c["student_name"] for c in list_codes(client, roll.id).json()]
        assert names == ["Lee, Amy", "Ng, Ben", "New Kid"]

    def test_roll_delete_cascades(self, client, db, roll):
        list_codes(client, roll.id)
        assert client.delete(f"/api/v1/teacher/rolls/{roll.id}").status_code == 204
        assert db.query(StudentClaimCode).filter_by(class_roll_id=roll.id).count() == 0
