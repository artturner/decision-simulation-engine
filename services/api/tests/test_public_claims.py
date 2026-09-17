"""Claim-code redemption and the student-session probe."""

from __future__ import annotations

import uuid
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.ratelimit import RateLimiter
from app.db.session import get_db
from app.main import app
from app.models.claim import StudentClaimCode
from app.models.user import User, UserRole
from app.repositories.claim_repo import ClaimRepository
from app.repositories.roll_repo import RollRepository


@pytest.fixture()
def teacher(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="claims-teacher@example.com",
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
def class_roll(db: Session, teacher: User):
    roll = RollRepository(db).create(
        teacher.id, "Period 3", ["Lee, Amy", "Ng, Ben"]
    )
    db.flush()
    return roll


@pytest.fixture()
def claim(db: Session, class_roll) -> StudentClaimCode:
    claims = ClaimRepository(db).ensure_for_roll(class_roll)
    db.flush()
    return next(c for c in claims if c.student_name == "Lee, Amy")


def redeem(client, code: str, name: str, join_code: str | None = None):
    body = {"claim_code": code, "student_name": name}
    if join_code is not None:
        body["join_code"] = join_code
    return client.post("/api/v1/public/claims/redeem", json=body)


class TestRedeem:
    def test_happy_path_returns_decodable_token(self, client, class_roll, claim):
        resp = redeem(client, claim.code, "Lee, Amy")
        assert resp.status_code == 200
        body = resp.json()
        assert body["student_name"] == "Lee, Amy"
        assert body["roll_id"] == str(class_roll.id)
        claims = jwt.decode(
            body["token"],
            settings.STUDENT_TOKEN_SECRET,
            algorithms=["HS256"],
            issuer=settings.STUDENT_TOKEN_ISSUER,
        )
        assert claims["jti"] == str(claim.id)
        assert claims["roll_id"] == str(class_roll.id)
        assert claims["owner"] == str(class_roll.owner_id)

    def test_multi_use_and_claim_bookkeeping(self, client, db, claim):
        assert claim.last_claimed_at is None
        assert redeem(client, claim.code, "Amy Lee").status_code == 200
        assert redeem(client, claim.code, "Lee, Amy").status_code == 200
        db.refresh(claim)
        assert claim.claim_count == 2
        assert claim.last_claimed_at is not None

    def test_code_is_whitespace_and_case_forgiving(self, client, claim):
        sloppy = f" {claim.code[:4].lower()}-{claim.code[4:].lower()} "
        assert redeem(client, sloppy, "Lee, Amy").status_code == 200

    def test_unknown_code_404(self, client, claim):
        resp = redeem(client, "NOPE2345", "Lee, Amy")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "claim_code_not_found"

    def test_wrong_name_403(self, client, claim):
        resp = redeem(client, claim.code, "Ng, Ben")
        assert resp.status_code == 403
        assert resp.json()["detail"]["code"] == "claim_code_wrong_name"

    def test_join_code_mismatch_is_indistinguishable_from_unknown(
        self, client, claim
    ):
        resp = redeem(client, claim.code, "Lee, Amy", join_code="WRONG1")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "claim_code_not_found"

    def test_matching_join_code_accepted(self, client, class_roll, claim):
        resp = redeem(client, claim.code, "Lee, Amy", join_code=class_roll.join_code.lower())
        assert resp.status_code == 200

    def test_regenerated_code_answers_like_unknown(
        self, client, db, class_roll, claim
    ):
        old_code = claim.code
        ClaimRepository(db).regenerate(class_roll, "Lee, Amy")
        db.flush()
        resp = redeem(client, old_code, "Lee, Amy")
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "claim_code_not_found"

    def test_503_when_secret_unset(self, client, claim, monkeypatch):
        monkeypatch.setattr(settings, "STUDENT_TOKEN_SECRET", "")
        assert redeem(client, claim.code, "Lee, Amy").status_code == 503


class TestStudentSession:
    def probe(self, client, token: str | None):
        headers = {"X-Student-Token": token} if token else {}
        return client.get("/api/v1/public/student-session", headers=headers)

    def test_valid_token(self, client, class_roll, claim):
        token = redeem(client, claim.code, "Lee, Amy").json()["token"]
        body = self.probe(client, token).json()
        assert body == {
            "valid": True,
            "reason": None,
            "student_name": "Lee, Amy",
            "roll_id": str(class_roll.id),
        }

    def test_missing_and_garbage_tokens(self, client):
        assert self.probe(client, None).json()["reason"] == "missing"
        assert self.probe(client, "not-a-jwt").json()["reason"] == "invalid"

    def test_revoked_after_regenerate(self, client, db, class_roll, claim):
        token = redeem(client, claim.code, "Lee, Amy").json()["token"]
        ClaimRepository(db).regenerate(class_roll, "Lee, Amy")
        db.flush()
        assert self.probe(client, token).json()["reason"] == "revoked"


class TestClaimRateLimit:
    def test_claim_bucket_limits_per_ip(self):
        """Unit test on a private limiter (the global one is disabled)."""
        rl = RateLimiter()
        dep = rl.limit("claim", 3, 60)
        request = Mock()
        request.headers = {"x-forwarded-for": "10.0.0.1"}
        for _ in range(3):
            dep(request)
        with pytest.raises(Exception) as exc_info:
            dep(request)
        assert getattr(exc_info.value, "status_code", None) == 429
