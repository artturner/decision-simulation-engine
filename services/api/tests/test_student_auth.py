"""Enforcement matrix for student-token gating on public play routes.

While STUDENT_TOKEN_ENFORCED is False (default) nothing is ever blocked;
when True, class-roll records require a matching token and anonymous
plays stay open.  Representative routes cover each gate helper:
GET /plays/{id} + POST step (require_play_access), reflection grade
(require_play_access on the read-back path), and the per-student status
endpoint + plays/start (require_roll_access).
"""

from __future__ import annotations

import time
import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.scenario import VersionStatus
from app.models.user import User, UserRole
from app.repositories.claim_repo import ClaimRepository
from app.repositories.play_repo import PlayRepository
from app.repositories.roll_repo import RollRepository
from app.repositories.scenario_repo import ScenarioRepository
from app.services.student_tokens import issue_student_token

SCENARIO_JSON: dict = {
    "metadata": {"title": "Gate Scenario", "description": "For auth tests."},
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
        email="gate-teacher@example.com",
        role=UserRole.teacher,
        is_approved=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client(db: Session):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def roll(db: Session, teacher: User):
    roll = RollRepository(db).create(teacher.id, "Period 1", ["Lee, Amy", "Ng, Ben"])
    db.flush()
    return roll


@pytest.fixture()
def other_roll(db: Session, teacher: User):
    roll = RollRepository(db).create(teacher.id, "Period 2", ["Lee, Amy"])
    db.flush()
    return roll


@pytest.fixture()
def version(db: Session, roll):
    repo = ScenarioRepository(db)
    scenario = repo.create_scenario("gate-scenario", "Gate Scenario")
    version = repo.create_version(scenario.id, SCENARIO_JSON, status=VersionStatus.published)
    RollRepository(db).assign_scenario(scenario.id, roll.id, visible=True, sort_order=1)
    db.flush()
    return version


def token_for(db: Session, roll, name: str) -> str:
    claims = ClaimRepository(db).ensure_for_roll(roll)
    db.flush()
    claim = next(c for c in claims if c.student_name == name)
    token, _exp = issue_student_token(claim, roll.owner_id)
    return token


def hdr(token: str | None) -> dict:
    return {"X-Student-Token": token} if token else {}


@pytest.fixture()
def class_play(db: Session, roll, version):
    play = PlayRepository(db).create_play(
        version.id, learner_label="Lee, Amy", class_roll_id=roll.id
    )
    db.flush()
    return play


@pytest.fixture()
def anon_play(db: Session, version):
    play = PlayRepository(db).create_play(version.id)
    db.flush()
    return play


def get_play(client, play, token=None):
    return client.get(f"/api/v1/public/plays/{play.id}", headers=hdr(token))


def step_play(client, play, token=None):
    return client.post(
        f"/api/v1/public/plays/{play.id}/step",
        json={"choice_index": 0},
        headers=hdr(token),
    )


def status_for(client, roll, name, token=None):
    return client.get(
        f"/api/v1/public/classes/code/{roll.join_code}/students/{name}",
        headers=hdr(token),
    )


class TestUnenforcedNothingBlocks:
    def test_class_play_without_token(self, client, class_play):
        assert get_play(client, class_play).status_code == 200
        assert step_play(client, class_play).status_code == 200

    def test_status_without_token(self, client, roll, version):
        assert status_for(client, roll, "Lee, Amy").status_code == 200

    def test_bad_token_never_blocks(self, client, class_play):
        assert get_play(client, class_play, "garbage").status_code == 200

    def test_other_students_token_never_blocks(self, client, db, roll, class_play):
        ben = token_for(db, roll, "Ng, Ben")
        assert get_play(client, class_play, ben).status_code == 200


class TestEnforced:
    def test_class_play_without_token_401(self, client, class_play, enforced):
        resp = get_play(client, class_play)
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "student_token_required"
        assert step_play(client, class_play).status_code == 401

    def test_matching_token_200(self, client, db, roll, class_play, enforced):
        token = token_for(db, roll, "Lee, Amy")
        assert get_play(client, class_play, token).status_code == 200
        assert step_play(client, class_play, token).status_code == 200

    def test_name_order_variant_matches(self, client, db, roll, version, enforced):
        """Token holds the roster spelling; the play label may be flipped."""
        play = PlayRepository(db).create_play(
            version.id, learner_label="Amy Lee", class_roll_id=roll.id
        )
        db.flush()
        token = token_for(db, roll, "Lee, Amy")
        assert get_play(client, play, token).status_code == 200

    def test_other_student_same_roll_403(self, client, db, roll, class_play, enforced):
        ben = token_for(db, roll, "Ng, Ben")
        resp = get_play(client, class_play, ben)
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "student_token_mismatch"

    def test_same_name_other_roll_403(
        self, client, db, other_roll, class_play, enforced
    ):
        token = token_for(db, other_roll, "Lee, Amy")
        assert get_play(client, class_play, token).status_code == 403

    def test_bad_signature_401_invalid(self, client, class_play, enforced):
        forged = jwt.encode(
            {"jti": str(uuid.uuid4()), "roll_id": str(class_play.class_roll_id),
             "name": "Lee, Amy", "iss": settings.STUDENT_TOKEN_ISSUER,
             "exp": int(time.time()) + 3600},
            "wrong-secret",
            algorithm="HS256",
        )
        resp = get_play(client, class_play, forged)
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "student_token_invalid"

    def test_expired_token_401_invalid(self, client, db, roll, class_play, enforced):
        claims = ClaimRepository(db).ensure_for_roll(roll)
        db.flush()
        claim = next(c for c in claims if c.student_name == "Lee, Amy")
        expired = jwt.encode(
            {"jti": str(claim.id), "roll_id": str(roll.id), "name": "Lee, Amy",
             "owner": str(roll.owner_id), "iss": settings.STUDENT_TOKEN_ISSUER,
             "exp": int(time.time()) - 10},
            settings.STUDENT_TOKEN_SECRET,
            algorithm="HS256",
        )
        resp = get_play(client, class_play, expired)
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "student_token_invalid"

    def test_regenerated_claim_401_revoked(
        self, client, db, roll, class_play, enforced
    ):
        token = token_for(db, roll, "Lee, Amy")
        ClaimRepository(db).regenerate(roll, "Lee, Amy")
        db.flush()
        resp = get_play(client, class_play, token)
        assert resp.status_code == 401
        assert resp.json()["detail"]["code"] == "student_token_revoked"

    def test_anonymous_play_stays_open(self, client, anon_play, enforced):
        assert get_play(client, anon_play).status_code == 200
        assert step_play(client, anon_play).status_code == 200

    def test_status_endpoint_gated(self, client, db, roll, version, enforced):
        assert status_for(client, roll, "Lee, Amy").status_code == 401
        token = token_for(db, roll, "Lee, Amy")
        assert status_for(client, roll, "Lee, Amy", token).status_code == 200
        assert status_for(client, roll, "Ng, Ben", token).status_code == 403

    def test_start_play_with_roll_gated(self, client, db, roll, version, enforced):
        body = {
            "scenario_version_id": str(version.id),
            "learner_label": "Lee, Amy",
            "class_roll_id": str(roll.id),
        }
        resp = client.post("/api/v1/public/plays/start", json=body)
        assert resp.status_code == 401
        token = token_for(db, roll, "Lee, Amy")
        resp = client.post(
            "/api/v1/public/plays/start", json=body, headers=hdr(token)
        )
        assert resp.status_code == 201

    def test_start_anonymous_play_stays_open(self, client, version, enforced):
        resp = client.post(
            "/api/v1/public/plays/start",
            json={"scenario_version_id": str(version.id)},
        )
        assert resp.status_code == 201

    def test_grade_endpoint_gated(self, client, db, roll, version, enforced):
        """The grade read-back path denies before any quota/AI logic runs."""
        repo = PlayRepository(db)
        play = repo.create_play(
            version.id, learner_label="Lee, Amy", class_roll_id=roll.id
        )
        repo.complete_play(play.id, outcome="ok")
        db.flush()
        resp = client.post(
            f"/api/v1/public/plays/{play.id}/reflection/grade",
            json={"responses": {"reflection_1": "text"}},
        )
        assert resp.status_code == 401

    def test_class_picker_stays_open(self, client, roll, enforced):
        resp = client.get(f"/api/v1/public/classes/code/{roll.join_code}")
        assert resp.status_code == 200
