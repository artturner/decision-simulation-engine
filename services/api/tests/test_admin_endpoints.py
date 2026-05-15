"""
Integration tests for the admin scenario endpoints.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.

The TestClient is constructed with a dependency override that injects the
per-test ``db`` session, so all writes happen inside the same transaction
and are rolled back after each test.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.main import app
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Minimal valid scenario JSON for reuse across tests
# ---------------------------------------------------------------------------

VALID_JSON: dict = {
    "metadata": {"title": "Test Scenario"},
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Scene 1",
            "choices": [{"text": "Go", "next": "s2"}],
        },
        "s2": {
            "type": "end",
            "title": "The End",
            "outcome": "success",
            "outcome_message": "Done.",
        },
    },
}

INVALID_JSON: dict = {
    "metadata": {"title": "Bad"},
    "variables": {},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Scene 1",
            "choices": [{"text": "Go", "next": "MISSING"}],  # dangling reference
        },
    },
}

ADMIN_HEADERS = {"X-Admin-Key": settings.ADMIN_API_KEY}


# ---------------------------------------------------------------------------
# Fixture: TestClient with DB session override
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(db: Session):
    """TestClient that routes DB calls through the test transaction."""

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def import_scenario(client, slug="test-slug", json_body=None, status="draft"):
    """POST /api/v1/admin/scenarios/import and return the response."""
    return client.post(
        "/api/v1/admin/scenarios/import",
        json={
            "slug": slug,
            "title": "Test",
            "description": "",
            "status": status,
            "scenario_json": json_body or VALID_JSON,
        },
        headers=ADMIN_HEADERS,
    )


# ---------------------------------------------------------------------------
# POST /api/v1/admin/scenarios/import
# ---------------------------------------------------------------------------


class TestImportScenario:
    def test_returns_201(self, client):
        resp = import_scenario(client)
        assert resp.status_code == 201

    def test_response_has_ids(self, client):
        data = import_scenario(client).json()
        assert uuid.UUID(data["scenario_id"])
        assert uuid.UUID(data["version_id"])

    def test_version_number_is_one(self, client):
        data = import_scenario(client).json()
        assert data["version_number"] == 1

    def test_status_stored(self, client):
        data = import_scenario(client, status="published").json()
        assert data["status"] == "published"

    def test_invalid_json_returns_400(self, client):
        resp = import_scenario(client, json_body=INVALID_JSON)
        assert resp.status_code == 400

    def test_invalid_json_returns_errors_list(self, client):
        resp = import_scenario(client, json_body=INVALID_JSON)
        body = resp.json()
        assert "errors" in body["detail"]
        assert len(body["detail"]["errors"]) > 0

    def test_duplicate_slug_returns_409(self, client):
        import_scenario(client, slug="unique-slug")
        resp = import_scenario(client, slug="unique-slug")
        assert resp.status_code == 409

    def test_missing_key_returns_403(self, client):
        resp = client.post(
            "/api/v1/admin/scenarios/import",
            json={
                "slug": "x",
                "title": "X",
                "status": "draft",
                "scenario_json": VALID_JSON,
            },
        )
        assert resp.status_code == 403

    def test_invalid_status_returns_422(self, client):
        resp = import_scenario(client, status="nonexistent")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/admin/scenarios/{scenario_id}
# ---------------------------------------------------------------------------


class TestGetScenario:
    def test_returns_200(self, client):
        data = import_scenario(client).json()
        resp = client.get(
            f"/api/v1/admin/scenarios/{data['scenario_id']}",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    def test_response_has_versions(self, client):
        data = import_scenario(client).json()
        resp = client.get(
            f"/api/v1/admin/scenarios/{data['scenario_id']}",
            headers=ADMIN_HEADERS,
        )
        body = resp.json()
        assert isinstance(body["versions"], list)
        assert len(body["versions"]) == 1

    def test_unknown_id_returns_404(self, client):
        resp = client.get(
            f"/api/v1/admin/scenarios/{uuid.uuid4()}",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    def test_missing_key_returns_403(self, client):
        data = import_scenario(client).json()
        resp = client.get(f"/api/v1/admin/scenarios/{data['scenario_id']}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/v1/admin/scenarios/{scenario_id}/versions
# ---------------------------------------------------------------------------


class TestCreateVersion:
    def test_returns_201(self, client):
        scenario_id = import_scenario(client).json()["scenario_id"]
        resp = client.post(
            f"/api/v1/admin/scenarios/{scenario_id}/versions",
            json={"status": "draft", "scenario_json": VALID_JSON},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 201

    def test_version_number_increments(self, client):
        scenario_id = import_scenario(client).json()["scenario_id"]
        resp = client.post(
            f"/api/v1/admin/scenarios/{scenario_id}/versions",
            json={"status": "draft", "scenario_json": VALID_JSON},
            headers=ADMIN_HEADERS,
        )
        assert resp.json()["version_number"] == 2

    def test_invalid_json_returns_400(self, client):
        scenario_id = import_scenario(client).json()["scenario_id"]
        resp = client.post(
            f"/api/v1/admin/scenarios/{scenario_id}/versions",
            json={"status": "draft", "scenario_json": INVALID_JSON},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 400

    def test_unknown_scenario_returns_404(self, client):
        resp = client.post(
            f"/api/v1/admin/scenarios/{uuid.uuid4()}/versions",
            json={"status": "draft", "scenario_json": VALID_JSON},
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/v1/admin/scenarios/{scenario_id}/versions/{version_number}/publish
# ---------------------------------------------------------------------------


class TestPublishVersion:
    def test_returns_200(self, client):
        data = import_scenario(client).json()
        resp = client.post(
            f"/api/v1/admin/scenarios/{data['scenario_id']}/versions/1/publish",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 200

    def test_status_is_published(self, client):
        data = import_scenario(client).json()
        resp = client.post(
            f"/api/v1/admin/scenarios/{data['scenario_id']}/versions/1/publish",
            headers=ADMIN_HEADERS,
        )
        assert resp.json()["status"] == "published"

    def test_previous_published_archived(self, client):
        """Publishing v2 must archive v1."""
        scenario_id = import_scenario(client, status="published").json()["scenario_id"]
        # Create v2
        client.post(
            f"/api/v1/admin/scenarios/{scenario_id}/versions",
            json={"status": "draft", "scenario_json": VALID_JSON},
            headers=ADMIN_HEADERS,
        )
        # Publish v2
        client.post(
            f"/api/v1/admin/scenarios/{scenario_id}/versions/2/publish",
            headers=ADMIN_HEADERS,
        )
        # Fetch scenario and check v1 is now archived
        body = client.get(
            f"/api/v1/admin/scenarios/{scenario_id}",
            headers=ADMIN_HEADERS,
        ).json()
        versions_by_num = {v["version_number"]: v for v in body["versions"]}
        assert versions_by_num[1]["status"] == "archived"
        assert versions_by_num[2]["status"] == "published"

    def test_unknown_version_returns_404(self, client):
        data = import_scenario(client).json()
        resp = client.post(
            f"/api/v1/admin/scenarios/{data['scenario_id']}/versions/99/publish",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404

    def test_unknown_scenario_returns_404(self, client):
        resp = client.post(
            f"/api/v1/admin/scenarios/{uuid.uuid4()}/versions/1/publish",
            headers=ADMIN_HEADERS,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health endpoint (no auth)
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
