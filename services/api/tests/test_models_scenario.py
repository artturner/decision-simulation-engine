"""
Integration tests for Scenario and ScenarioVersion ORM models.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a transaction that is rolled back on teardown,
so tests are isolated and the database is never left dirty.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.scenario import Scenario, ScenarioVersion, VersionStatus

SAMPLE_JSON: dict = {
    "metadata": {"title": "Test Scenario"},
    "variables": {"confidence": 0},
    "start_scene_id": "1",
    "scenes": {
        "1": {
            "type": "choice",
            "choices": [{"text": "Go", "next": "end"}],
        },
        "end": {"type": "end", "outcome": "success", "outcome_message": "Done."},
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_scenario(db, slug: str = "test-scenario", title: str = "Test") -> Scenario:
    scenario = Scenario(slug=slug, title=title)
    db.add(scenario)
    db.flush()
    return scenario


def make_version(
    db,
    scenario: Scenario,
    version_number: int = 1,
    status: VersionStatus = VersionStatus.draft,
    scenario_json: dict | None = None,
) -> ScenarioVersion:
    version = ScenarioVersion(
        scenario_id=scenario.id,
        version_number=version_number,
        status=status,
        scenario_json=scenario_json or SAMPLE_JSON,
    )
    db.add(version)
    db.flush()
    return version


# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------


class TestScenarioModel:
    def test_create_scenario(self, db):
        scenario = make_scenario(db)
        assert scenario.id is not None
        assert isinstance(scenario.id, uuid.UUID)

    def test_slug_is_stored(self, db):
        scenario = make_scenario(db, slug="my-slug")
        db.expire(scenario)
        loaded = db.get(Scenario, scenario.id)
        assert loaded.slug == "my-slug"

    def test_title_is_stored(self, db):
        scenario = make_scenario(db, title="My Title")
        db.expire(scenario)
        loaded = db.get(Scenario, scenario.id)
        assert loaded.title == "My Title"

    def test_description_defaults_to_empty(self, db):
        scenario = make_scenario(db)
        assert scenario.description == ""

    def test_created_at_set_by_db(self, db):
        scenario = make_scenario(db)
        db.expire(scenario)
        loaded = db.get(Scenario, scenario.id)
        assert loaded.created_at is not None

    def test_slug_unique_constraint(self, db):
        make_scenario(db, slug="duplicate-slug")
        with pytest.raises(IntegrityError):
            make_scenario(db, slug="duplicate-slug")

    def test_versions_relationship_empty_initially(self, db):
        scenario = make_scenario(db)
        assert scenario.versions == []

    def test_repr(self, db):
        scenario = make_scenario(db, slug="repr-slug")
        assert "repr-slug" in repr(scenario)


# ---------------------------------------------------------------------------
# ScenarioVersion model
# ---------------------------------------------------------------------------


class TestScenarioVersionModel:
    def test_create_version(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario)
        assert version.id is not None
        assert isinstance(version.id, uuid.UUID)

    def test_default_status_is_draft(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario)
        db.expire(version)
        loaded = db.get(ScenarioVersion, version.id)
        assert loaded.status == VersionStatus.draft

    def test_publish_status(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario, status=VersionStatus.published)
        db.expire(version)
        loaded = db.get(ScenarioVersion, version.id)
        assert loaded.status == VersionStatus.published

    def test_scenario_json_round_trips(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario, scenario_json=SAMPLE_JSON)
        db.expire(version)
        loaded = db.get(ScenarioVersion, version.id)
        assert loaded.scenario_json["metadata"]["title"] == "Test Scenario"

    def test_version_number_stored(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario, version_number=3)
        db.expire(version)
        loaded = db.get(ScenarioVersion, version.id)
        assert loaded.version_number == 3

    def test_created_at_set_by_db(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario)
        db.expire(version)
        loaded = db.get(ScenarioVersion, version.id)
        assert loaded.created_at is not None

    def test_scenario_relationship(self, db):
        scenario = make_scenario(db, slug="rel-scenario")
        version = make_version(db, scenario)
        assert version.scenario.slug == "rel-scenario"

    def test_scenario_versions_relationship(self, db):
        scenario = make_scenario(db)
        v1 = make_version(db, scenario, version_number=1)
        v2 = make_version(db, scenario, version_number=2)
        db.expire(scenario)
        loaded = db.get(Scenario, scenario.id)
        assert len(loaded.versions) == 2
        assert loaded.versions[0].version_number == 1
        assert loaded.versions[1].version_number == 2

    def test_versions_ordered_by_version_number(self, db):
        scenario = make_scenario(db)
        make_version(db, scenario, version_number=2)
        make_version(db, scenario, version_number=1)
        db.expire(scenario)
        loaded = db.get(Scenario, scenario.id)
        numbers = [v.version_number for v in loaded.versions]
        assert numbers == sorted(numbers)

    def test_repr(self, db):
        scenario = make_scenario(db)
        version = make_version(db, scenario, version_number=7)
        assert "v7" in repr(version)
        assert "draft" in repr(version)

    # Constraints ----------------------------------------------------------

    def test_unique_constraint_scenario_version_number(self, db):
        """(scenario_id, version_number) must be unique."""
        scenario = make_scenario(db)
        make_version(db, scenario, version_number=1)
        with pytest.raises(IntegrityError):
            make_version(db, scenario, version_number=1)

    def test_same_version_number_different_scenarios_allowed(self, db):
        """version_number=1 may exist for multiple distinct scenarios."""
        s1 = make_scenario(db, slug="scenario-alpha")
        s2 = make_scenario(db, slug="scenario-beta")
        v1 = make_version(db, s1, version_number=1)
        v2 = make_version(db, s2, version_number=1)
        assert v1.id != v2.id

    def test_cascade_delete_removes_versions(self, db):
        """Deleting a Scenario cascades to its versions."""
        scenario = make_scenario(db, slug="cascade-test")
        make_version(db, scenario, version_number=1)
        version_id = scenario.versions[0].id

        db.delete(scenario)
        db.flush()

        assert db.get(ScenarioVersion, version_id) is None
