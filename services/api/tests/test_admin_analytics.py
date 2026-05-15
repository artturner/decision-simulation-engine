"""
Integration tests for:
  GET /api/v1/admin/scenarios/{id}/analytics
  GET /api/v1/admin/scenarios/{id}/export.csv

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for isolation.

Blueprint requirements covered:
- Analytics correct for sample data (counts, rates, distributions)
- Version_number filter works correctly
- drop_off_by_scene counts abandoned plays at their last scene
- choice_distribution aggregates choose events per scene / index
- reflection_rate computed against completed plays
- CSV format valid (headers, commas escaped, correct row count)
- CSV filters by version_number correctly
- CSV columns: play_id, learner_label, started_at, completed, outcome,
               path, reflection_1, reflection_2, ...
- 404 for unknown scenario on both endpoints
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models.scenario import VersionStatus
from app.repositories.scenario_repo import ScenarioRepository

HEADERS = {"X-Admin-Key": settings.ADMIN_API_KEY}

# ---------------------------------------------------------------------------
# Scenario JSON used across tests
# ---------------------------------------------------------------------------

# Two-path scenario:  s1 (choice) → s2 (end)  or  s1 → s3 (end)
SCENARIO_JSON: dict = {
    "metadata": {
        "title": "Analytics Test",
        "completion_tracking": True,
    },
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "reflection_questions": ["What did you learn?", "What would you change?"],
    "reflection_prompts": [],
    "scenes": {
        "s1": {
            "type": "choice",
            "title": "Choose",
            "choices": [
                {"text": "Path A", "next": "s2", "effects": {"score": 1}},
                {"text": "Path B", "next": "s3"},
            ],
        },
        "s2": {
            "type": "end",
            "title": "End A",
            "outcome": "success",
            "outcome_message": "Well done!",
        },
        "s3": {
            "type": "end",
            "title": "End B",
            "outcome": "failure",
            "outcome_message": "Try again.",
        },
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


def _import_scenario(client, slug: str, json_body: dict = SCENARIO_JSON) -> dict:
    resp = client.post(
        "/api/v1/admin/scenarios/import",
        json={
            "slug": slug,
            "title": "Test",
            "status": "published",
            "scenario_json": json_body,
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _start_play(client, version_id: str, learner_label: str | None = None) -> str:
    body: dict = {"scenario_version_id": version_id}
    if learner_label:
        body["learner_label"] = learner_label
    resp = client.post("/api/v1/public/plays/start", json=body)
    assert resp.status_code == 201
    return resp.json()["play_id"]


def _step(client, play_id: str, choice_index: int | None = None):
    body = {} if choice_index is None else {"choice_index": choice_index}
    resp = client.post(f"/api/v1/public/plays/{play_id}/step", json=body)
    assert resp.status_code == 200
    return resp.json()


def _reflect(client, play_id: str, responses: dict[str, str], student_name: str | None = None):
    body: dict = {"responses": responses}
    if student_name:
        body["student_name"] = student_name
    resp = client.post(f"/api/v1/public/plays/{play_id}/reflection", json=body)
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture()
def scenario(client, db: Session) -> dict:
    """Seed a scenario; return the import response JSON."""
    return _import_scenario(client, "analytics-test")


@pytest.fixture()
def populated_scenario(client, scenario) -> dict:
    """
    Three plays:
      - play1: completed via choice 0 (Path A) + reflection submitted
      - play2: completed via choice 1 (Path B), no reflection
      - play3: abandoned at s1 (no step taken)
    """
    vid = scenario["version_id"]
    sid = scenario["scenario_id"]

    # play1: complete via Path A + reflection
    p1 = _start_play(client, vid, learner_label="Alice")
    _step(client, p1, choice_index=0)   # s1 → s2 (end, done)
    _reflect(client, p1, {"reflection_1": "Learned lots.", "reflection_2": "Be faster."}, student_name="Alice")

    # play2: complete via Path B, no reflection
    p2 = _start_play(client, vid, learner_label="Bob")
    _step(client, p2, choice_index=1)   # s1 → s3 (end, done)

    # play3: abandoned at s1
    _start_play(client, vid)

    return {"scenario_id": sid, "version_id": vid}


# ---------------------------------------------------------------------------
# Analytics — 404 guard
# ---------------------------------------------------------------------------


class TestAnalytics404:
    def test_unknown_scenario(self, client):
        resp = client.get(
            f"/api/v1/admin/scenarios/{uuid.uuid4()}/analytics",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    def test_requires_admin_key(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/analytics"
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Analytics — empty scenario (no plays)
# ---------------------------------------------------------------------------


class TestAnalyticsEmpty:
    def test_returns_200(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/analytics",
            headers=HEADERS,
        )
        assert resp.status_code == 200

    def test_zeroed_counts(self, client, scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 0
        assert body["completed_plays"] == 0
        assert body["completion_rate"] == 0.0
        assert body["reflection_count"] == 0
        assert body["reflection_rate"] == 0.0
        assert body["drop_off_by_scene"] == {}
        assert body["choice_distribution"] == {}


# ---------------------------------------------------------------------------
# Analytics — populated data
# ---------------------------------------------------------------------------


class TestAnalyticsData:
    def test_total_plays(self, client, populated_scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 3

    def test_completed_plays(self, client, populated_scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        assert body["completed_plays"] == 2

    def test_completion_rate(self, client, populated_scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        # 2 completed / 3 total = 0.6667
        assert abs(body["completion_rate"] - round(2 / 3, 4)) < 1e-6

    def test_drop_off_by_scene(self, client, populated_scenario):
        """play3 abandoned at s1 — should appear in drop_off."""
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        assert body["drop_off_by_scene"].get("s1", 0) == 1

    def test_choice_distribution(self, client, populated_scenario):
        """play1 chose index 0, play2 chose index 1 at s1."""
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        dist = body["choice_distribution"]
        assert dist["s1"]["0"] == 1
        assert dist["s1"]["1"] == 1

    def test_reflection_count(self, client, populated_scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        assert body["reflection_count"] == 1

    def test_reflection_rate(self, client, populated_scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/analytics",
            headers=HEADERS,
        ).json()
        # 1 reflection / 2 completed = 0.5
        assert body["reflection_rate"] == 0.5


# ---------------------------------------------------------------------------
# Analytics — version_number filter
# ---------------------------------------------------------------------------


class TestAnalyticsVersionFilter:
    @pytest.fixture()
    def two_version_scenario(self, client, db: Session, scenario) -> dict:
        """Add a second version; create one play per version."""
        sid = scenario["scenario_id"]
        v1_id = scenario["version_id"]

        # Create version 2 via admin API
        v2_resp = client.post(
            f"/api/v1/admin/scenarios/{sid}/versions",
            json={"scenario_json": SCENARIO_JSON, "status": "published"},
            headers=HEADERS,
        )
        assert v2_resp.status_code == 201
        v2_id = v2_resp.json()["version_id"]

        # One completed play on v1
        p1 = _start_play(client, v1_id)
        _step(client, p1, choice_index=0)

        # One abandoned play on v2
        _start_play(client, v2_id)

        return {"scenario_id": sid, "v1_id": v1_id, "v2_id": v2_id}

    def test_filter_to_v1(self, client, two_version_scenario):
        sid = two_version_scenario["scenario_id"]
        body = client.get(
            f"/api/v1/admin/scenarios/{sid}/analytics?version_number=1",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 1
        assert body["completed_plays"] == 1

    def test_filter_to_v2(self, client, two_version_scenario):
        sid = two_version_scenario["scenario_id"]
        body = client.get(
            f"/api/v1/admin/scenarios/{sid}/analytics?version_number=2",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 1
        assert body["completed_plays"] == 0

    def test_no_filter_aggregates_all(self, client, two_version_scenario):
        sid = two_version_scenario["scenario_id"]
        body = client.get(
            f"/api/v1/admin/scenarios/{sid}/analytics",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 2

    def test_nonexistent_version_returns_zeros(self, client, scenario):
        body = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/analytics?version_number=99",
            headers=HEADERS,
        ).json()
        assert body["total_plays"] == 0


# ---------------------------------------------------------------------------
# CSV export — 404 guard and content-type
# ---------------------------------------------------------------------------


class TestExportBasic:
    def test_unknown_scenario_404(self, client):
        resp = client.get(
            f"/api/v1/admin/scenarios/{uuid.uuid4()}/export.csv",
            headers=HEADERS,
        )
        assert resp.status_code == 404

    def test_requires_admin_key(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/export.csv"
        )
        assert resp.status_code == 403

    def test_content_type_csv(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    def test_content_disposition(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        assert "attachment" in resp.headers["content-disposition"]
        assert ".csv" in resp.headers["content-disposition"]

    def test_empty_scenario_has_header_only(self, client, scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        rows = list(csv.reader(io.StringIO(resp.text)))
        assert len(rows) == 1  # header row only
        assert rows[0][0] == "play_id"


# ---------------------------------------------------------------------------
# CSV export — column structure
# ---------------------------------------------------------------------------


class TestExportColumns:
    def test_standard_headers_present(self, client, populated_scenario):
        resp = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        rows = list(csv.reader(io.StringIO(resp.text)))
        headers = rows[0]
        for col in ("play_id", "learner_label", "started_at", "completed", "outcome", "path"):
            assert col in headers

    def test_reflection_columns_present(self, client, populated_scenario):
        """SCENARIO_JSON has 2 reflection questions → reflection_1 and reflection_2."""
        resp = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        rows = list(csv.reader(io.StringIO(resp.text)))
        headers = rows[0]
        assert "reflection_1" in headers
        assert "reflection_2" in headers

    def test_row_count(self, client, populated_scenario):
        """Header + 3 play rows."""
        resp = client.get(
            f"/api/v1/admin/scenarios/{populated_scenario['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        rows = list(csv.reader(io.StringIO(resp.text)))
        # Filter blank trailing row if present
        data_rows = [r for r in rows[1:] if any(r)]
        assert len(data_rows) == 3


# ---------------------------------------------------------------------------
# CSV export — row content
# ---------------------------------------------------------------------------


class TestExportContent:
    def _get_csv_rows(self, client, scenario_id: str) -> tuple[list[str], list[dict]]:
        resp = client.get(
            f"/api/v1/admin/scenarios/{scenario_id}/export.csv",
            headers=HEADERS,
        )
        reader = csv.DictReader(io.StringIO(resp.text))
        return list(reader)

    def test_completed_flag(self, client, populated_scenario):
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        completed_vals = {r["completed"] for r in rows}
        assert "true" in completed_vals   # play1 and play2
        assert "false" in completed_vals  # play3

    def test_outcome_populated_for_completed(self, client, populated_scenario):
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        outcomes = [r["outcome"] for r in rows if r["completed"] == "true"]
        assert "success" in outcomes
        assert "failure" in outcomes

    def test_path_contains_scenes(self, client, populated_scenario):
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        # All plays started at s1
        for row in rows:
            assert "s1" in row["path"]

    def test_path_arrow_separator(self, client, populated_scenario):
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        # Completed plays visited at least 2 scenes → path has " -> "
        completed_rows = [r for r in rows if r["completed"] == "true"]
        for row in completed_rows:
            assert " -> " in row["path"]

    def test_learner_label(self, client, populated_scenario):
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        labels = {r["learner_label"] for r in rows}
        assert "Alice" in labels
        assert "Bob" in labels

    def test_reflection_answers_in_csv(self, client, populated_scenario):
        """Alice's reflection answers should appear in reflection_1/reflection_2."""
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        alice = next(r for r in rows if r["learner_label"] == "Alice")
        assert alice["reflection_1"] == "Learned lots."
        assert alice["reflection_2"] == "Be faster."

    def test_no_reflection_empty_columns(self, client, populated_scenario):
        """Bob submitted no reflection — columns should be empty strings."""
        rows = self._get_csv_rows(client, populated_scenario["scenario_id"])
        bob = next(r for r in rows if r["learner_label"] == "Bob")
        assert bob["reflection_1"] == ""
        assert bob["reflection_2"] == ""

    def test_comma_in_reflection_escaped(self, client, db: Session, scenario):
        """A comma inside a reflection answer must not corrupt the CSV."""
        vid = scenario["version_id"]
        sid = scenario["scenario_id"]
        p = _start_play(client, vid, learner_label="Comma,Test")
        _step(client, p, choice_index=0)
        _reflect(client, p, {"reflection_1": "Answer, with comma.", "reflection_2": "Normal."})

        rows = self._get_csv_rows(client, sid)
        row = next(r for r in rows if "Comma" in r["learner_label"])
        assert row["reflection_1"] == "Answer, with comma."


# ---------------------------------------------------------------------------
# CSV export — version_number filter
# ---------------------------------------------------------------------------


class TestExportVersionFilter:
    @pytest.fixture()
    def two_version_data(self, client, db: Session, scenario) -> dict:
        sid = scenario["scenario_id"]
        v1_id = scenario["version_id"]

        v2_resp = client.post(
            f"/api/v1/admin/scenarios/{sid}/versions",
            json={"scenario_json": SCENARIO_JSON, "status": "published"},
            headers=HEADERS,
        )
        v2_id = v2_resp.json()["version_id"]

        p1 = _start_play(client, v1_id, learner_label="V1Player")
        _step(client, p1, choice_index=0)

        p2 = _start_play(client, v2_id, learner_label="V2Player")
        _step(client, p2, choice_index=1)

        return {"scenario_id": sid}

    def test_filter_to_v1_row_count(self, client, two_version_data):
        resp = client.get(
            f"/api/v1/admin/scenarios/{two_version_data['scenario_id']}/export.csv?version_number=1",
            headers=HEADERS,
        )
        rows = [r for r in csv.reader(io.StringIO(resp.text)) if any(r)]
        assert len(rows) == 2  # 1 header + 1 data row

    def test_filter_to_v1_content(self, client, two_version_data):
        resp = client.get(
            f"/api/v1/admin/scenarios/{two_version_data['scenario_id']}/export.csv?version_number=1",
            headers=HEADERS,
        )
        rows = list(csv.DictReader(io.StringIO(resp.text)))
        assert rows[0]["learner_label"] == "V1Player"

    def test_no_filter_returns_all(self, client, two_version_data):
        resp = client.get(
            f"/api/v1/admin/scenarios/{two_version_data['scenario_id']}/export.csv",
            headers=HEADERS,
        )
        rows = [r for r in csv.reader(io.StringIO(resp.text)) if any(r)]
        assert len(rows) == 3  # 1 header + 2 data rows
