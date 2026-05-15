"""
Integration tests for GET /api/v1/public/scenarios/{slug}.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.repositories.scenario_repo import ScenarioRepository
from app.models.scenario import VersionStatus

ADMIN_HEADERS = {"X-Admin-Key": settings.ADMIN_API_KEY}

# ---------------------------------------------------------------------------
# A valid scenario JSON with rich metadata for assertion checks
# ---------------------------------------------------------------------------

VALID_JSON: dict = {
    "metadata": {
        "title": "My Scenario",
        "description": "A test description.",
        "page_title": "Page Title",
        "page_icon": "🎓",
        "author": "Tester",
        "completion_tracking": True,
    },
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "reflection_questions": ["What did you learn?", "What would you do differently?"],
    "reflection_prompts": ["Think broadly.", "Be specific."],
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Scene 1",
            "choices": [{"text": "Go", "next": "s2"}],
        },
        "s2": {
            "type": "end",
            "title": "Done",
            "outcome": "success",
            "outcome_message": "Well done.",
        },
    },
}

MINIMAL_JSON: dict = {
    "metadata": {"title": "Minimal"},
    "variables": {},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {"type": "end", "title": "End", "outcome": "done", "outcome_message": ""},
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
def published_slug(db: Session) -> str:
    """Seed a published scenario and return its slug."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("pub-slug", "Published Scenario")
    v = repo.create_version(s.id, VALID_JSON, status=VersionStatus.published)
    db.flush()
    return "pub-slug"


@pytest.fixture()
def draft_only_slug(db: Session) -> str:
    """Seed a scenario with only a draft version and return its slug."""
    repo = ScenarioRepository(db)
    s = repo.create_scenario("draft-slug", "Draft Scenario")
    repo.create_version(s.id, MINIMAL_JSON, status=VersionStatus.draft)
    db.flush()
    return "draft-slug"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetPublicScenario:
    def test_returns_200_for_published(self, client, published_slug):
        resp = client.get(f"/api/v1/public/scenarios/{published_slug}")
        assert resp.status_code == 200

    def test_slug_in_response(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["slug"] == published_slug

    def test_version_id_is_uuid(self, client, published_slug):
        import uuid
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert uuid.UUID(body["scenario_version_id"])

    def test_version_number_returned(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["version_number"] == 1

    def test_start_scene_id(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["start_scene_id"] == "s1"

    def test_metadata_title(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["metadata"]["title"] == "My Scenario"

    def test_metadata_description(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["metadata"]["description"] == "A test description."

    def test_metadata_completion_tracking(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["metadata"]["completion_tracking"] is True

    def test_reflection_questions(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["reflection_questions"] == [
            "What did you learn?",
            "What would you do differently?",
        ]

    def test_reflection_prompts(self, client, published_slug):
        body = client.get(f"/api/v1/public/scenarios/{published_slug}").json()
        assert body["reflection_prompts"] == ["Think broadly.", "Be specific."]

    def test_404_for_unknown_slug(self, client):
        resp = client.get("/api/v1/public/scenarios/does-not-exist")
        assert resp.status_code == 404

    def test_404_for_draft_only_scenario(self, client, draft_only_slug):
        resp = client.get(f"/api/v1/public/scenarios/{draft_only_slug}")
        assert resp.status_code == 404

    def test_returns_highest_published_version(self, client, db: Session):
        """When multiple published versions exist, highest version_number wins."""
        repo = ScenarioRepository(db)
        s = repo.create_scenario("multi-slug", "Multi Version")
        v1 = repo.create_version(s.id, MINIMAL_JSON, status=VersionStatus.published)
        # publish v2 — repo archives v1 automatically
        v2 = repo.create_version(s.id, VALID_JSON, status=VersionStatus.draft)
        repo.publish_version(v2.id)
        db.flush()

        body = client.get("/api/v1/public/scenarios/multi-slug").json()
        assert body["version_number"] == 2
        assert body["start_scene_id"] == "s1"

    def test_no_auth_required(self, client, published_slug):
        """Public endpoint must not require X-Admin-Key."""
        resp = client.get(f"/api/v1/public/scenarios/{published_slug}")
        assert resp.status_code == 200

    def test_missing_reflection_fields_default_to_empty(self, client, db: Session):
        """scenario_json with no reflection keys returns empty lists."""
        repo = ScenarioRepository(db)
        s = repo.create_scenario("no-reflect", "No Reflect")
        repo.create_version(s.id, MINIMAL_JSON, status=VersionStatus.published)
        db.flush()

        body = client.get("/api/v1/public/scenarios/no-reflect").json()
        assert body["reflection_questions"] == []
        assert body["reflection_prompts"] == []
