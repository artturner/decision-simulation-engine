"""Access codes for essay-grader classes: link, mirror, roster sync."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.admin import get_current_user
from app.db.session import get_db
from app.main import app
from app.models.user import ClassRoll, User, UserRole
from app.repositories.roll_repo import RollRepository


def make_teacher(db: Session, email: str) -> User:
    user = User(id=uuid.uuid4(), email=email, role=UserRole.teacher, is_approved=True)
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def teacher(db: Session) -> User:
    return make_teacher(db, "links-teacher@example.com")


@pytest.fixture()
def acting(db: Session, teacher: User):
    """Mutable holder for the user the client authenticates as."""
    return {"user": teacher}


@pytest.fixture()
def client(db: Session, acting):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: acting["user"]
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def link(client, essay_roll_id, name, names):
    return client.post(
        "/api/v1/teacher/essay-links",
        json={"essay_roll_id": str(essay_roll_id), "name": name, "student_names": names},
    )


class TestMirror:
    def test_creates_mirror_roll_with_codes_in_essay_order(self, client, db, teacher):
        essay_id = uuid.uuid4()
        resp = link(client, essay_id, "26-27AP_PC", ["Ng, Ben", "Lee, Amy"])
        assert resp.status_code == 200
        body = resp.json()
        assert body["mirrors_essay_roll"] is True
        assert body["roll_name"] == "26-27AP_PC"
        assert [c["student_name"] for c in body["codes"]] == ["Ng, Ben", "Lee, Amy"]
        roll = db.get(ClassRoll, uuid.UUID(body["roll_id"]))
        assert roll.owner_id == teacher.id
        assert roll.essay_roll_id == essay_id

    def test_repeat_call_reuses_roll_and_codes(self, client):
        essay_id = uuid.uuid4()
        first = link(client, essay_id, "AP", ["Lee, Amy"]).json()
        again = link(client, essay_id, "AP", ["Lee, Amy"]).json()
        assert again["roll_id"] == first["roll_id"]
        assert again["codes"][0]["code"] == first["codes"][0]["code"]

    def test_roster_follows_essay_class(self, client, db):
        essay_id = uuid.uuid4()
        first = link(client, essay_id, "AP", ["Lee, Amy", "Ng, Ben"]).json()
        kept = first["codes"][0]["code"]
        body = link(client, essay_id, "AP (renamed)", ["Lee,  Amy", "Cruz, Ana"]).json()
        assert body["roll_name"] == "AP (renamed)"
        # Whitespace fix keeps the code; removed student's code is gone.
        assert [c["student_name"] for c in body["codes"]] == ["Lee, Amy", "Cruz, Ana"]
        assert body["codes"][0]["code"] == kept
        roll = db.get(ClassRoll, uuid.UUID(body["roll_id"]))
        assert roll.student_names == ["Lee,  Amy", "Cruz, Ana"]

    def test_regenerate_via_roll_endpoint(self, client):
        body = link(client, uuid.uuid4(), "AP", ["Lee, Amy"]).json()
        old = body["codes"][0]["code"]
        resp = client.post(
            f"/api/v1/teacher/rolls/{body['roll_id']}/claim-codes/regenerate",
            json={"student_name": "Lee, Amy"},
        )
        assert resp.status_code == 200
        assert resp.json()[0]["code"] != old


class TestLinkExisting:
    @pytest.fixture()
    def scen_roll(self, db, teacher):
        roll = RollRepository(db).create(
            teacher.id, "SGPHS_F26", ["Lee, Amy", "Ng, Ben", "Cruz, Ana", "Diaz, Eva", "Kim, Jo"]
        )
        db.flush()
        return roll

    def test_links_roll_covering_the_roster_and_keeps_codes(self, client, db, scen_roll):
        before = client.get(f"/api/v1/teacher/rolls/{scen_roll.id}/claim-codes").json()
        amy_code = next(c["code"] for c in before if c["student_name"] == "Lee, Amy")
        # Different class name, different name order — roster overlap decides.
        body = link(client, uuid.uuid4(), "Essays SGPHS", ["Amy Lee", "Ben Ng", "Ana Cruz", "Eva Diaz"]).json()
        assert body["roll_id"] == str(scen_roll.id)
        assert body["mirrors_essay_roll"] is False
        assert len(body["codes"]) == 4
        assert body["codes"][0]["code"] == amy_code

    def test_linked_roll_only_gains_names(self, client, db, scen_roll):
        names = ["Lee, Amy", "Ng, Ben", "Cruz, Ana", "Diaz, Eva", "Late, Add"]
        body = link(client, uuid.uuid4(), "SGPHS_F26", names).json()
        assert body["roll_id"] == str(scen_roll.id)
        db.refresh(scen_roll)
        assert scen_roll.name == "SGPHS_F26"
        assert scen_roll.student_names[-1] == "Late, Add"
        assert "Kim, Jo" in scen_roll.student_names  # never removed
        assert [c["student_name"] for c in body["codes"]] == names

    def test_low_overlap_creates_mirror_instead(self, client, scen_roll):
        body = link(client, uuid.uuid4(), "SGPHS_F26", ["Lee, Amy", "X, A", "Y, B", "Z, C"]).json()
        assert body["roll_id"] != str(scen_roll.id)
        assert body["mirrors_essay_roll"] is True

    def test_already_linked_roll_is_not_reused_for_another_class(self, client, scen_roll):
        names = ["Lee, Amy", "Ng, Ben", "Cruz, Ana", "Diaz, Eva", "Kim, Jo"]
        first = link(client, uuid.uuid4(), "A", names).json()
        second = link(client, uuid.uuid4(), "B", names).json()
        assert first["roll_id"] == str(scen_roll.id)
        assert second["roll_id"] != str(scen_roll.id)


class TestOwnership:
    def test_other_teachers_rolls_never_linked(self, client, db, acting):
        other = make_teacher(db, "links-other@example.com")
        RollRepository(db).create(other.id, "AP", ["Lee, Amy"])
        db.flush()
        body = link(client, uuid.uuid4(), "AP", ["Lee, Amy"]).json()
        assert body["mirrors_essay_roll"] is True

    def test_essay_class_linked_by_another_teacher_conflicts(self, client, db, acting):
        essay_id = uuid.uuid4()
        assert link(client, essay_id, "AP", ["Lee, Amy"]).status_code == 200
        acting["user"] = make_teacher(db, "links-intruder@example.com")
        assert link(client, essay_id, "AP", ["Lee, Amy"]).status_code == 409

    def test_unapproved_teacher_blocked(self, client, db, acting):
        user = make_teacher(db, "links-pending@example.com")
        user.is_approved = False
        acting["user"] = user
        assert link(client, uuid.uuid4(), "AP", ["Lee, Amy"]).status_code == 403
