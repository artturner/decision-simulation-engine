"""
Integration tests for ScenarioRepository.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for full isolation.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.scenario import Scenario, ScenarioVersion, VersionStatus
from app.repositories.scenario_repo import ScenarioRepository

SAMPLE_JSON: dict = {
    "metadata": {"title": "Test"},
    "variables": {},
    "start_scene_id": "1",
    "scenes": {
        "1": {"type": "choice", "choices": [{"text": "Go", "next": "end"}]},
        "end": {"type": "end", "outcome": "success", "outcome_message": "Done."},
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def repo(db) -> ScenarioRepository:
    return ScenarioRepository(db)


def unique_slug(prefix: str = "scenario") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# create_scenario
# ---------------------------------------------------------------------------


class TestCreateScenario:
    def test_returns_scenario_instance(self, db):
        s = repo(db).create_scenario(unique_slug(), "My Title")
        assert isinstance(s, Scenario)

    def test_id_is_assigned(self, db):
        s = repo(db).create_scenario(unique_slug(), "T")
        assert s.id is not None
        assert isinstance(s.id, uuid.UUID)

    def test_slug_stored(self, db):
        slug = unique_slug()
        s = repo(db).create_scenario(slug, "T")
        db.expire(s)
        assert db.get(Scenario, s.id).slug == slug

    def test_title_stored(self, db):
        s = repo(db).create_scenario(unique_slug(), "My Scenario")
        db.expire(s)
        assert db.get(Scenario, s.id).title == "My Scenario"

    def test_description_defaults_to_empty(self, db):
        s = repo(db).create_scenario(unique_slug(), "T")
        assert s.description == ""

    def test_description_stored(self, db):
        s = repo(db).create_scenario(unique_slug(), "T", description="About this.")
        db.expire(s)
        assert db.get(Scenario, s.id).description == "About this."

    def test_duplicate_slug_raises(self, db):
        slug = unique_slug()
        repo(db).create_scenario(slug, "First")
        with pytest.raises(IntegrityError):
            repo(db).create_scenario(slug, "Second")


# ---------------------------------------------------------------------------
# get_by_slug
# ---------------------------------------------------------------------------


class TestGetBySlug:
    def test_returns_scenario(self, db):
        r = repo(db)
        slug = unique_slug()
        r.create_scenario(slug, "T")
        found = r.get_by_slug(slug)
        assert found is not None
        assert found.slug == slug

    def test_returns_none_for_unknown_slug(self, db):
        assert repo(db).get_by_slug("does-not-exist") is None

    def test_versions_eagerly_loaded(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON)
        r.create_version(s.id, SAMPLE_JSON)
        found = r.get_by_slug(s.slug)
        # Access versions without triggering a lazy load error
        assert len(found.versions) == 2

    def test_versions_ordered_by_version_number(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON)
        r.create_version(s.id, SAMPLE_JSON)
        found = r.get_by_slug(s.slug)
        numbers = [v.version_number for v in found.versions]
        assert numbers == sorted(numbers)


# ---------------------------------------------------------------------------
# create_version
# ---------------------------------------------------------------------------


class TestCreateVersion:
    def test_returns_scenario_version(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        assert isinstance(v, ScenarioVersion)

    def test_first_version_number_is_one(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        assert v.version_number == 1

    def test_second_version_number_is_two(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON)
        v2 = r.create_version(s.id, SAMPLE_JSON)
        assert v2.version_number == 2

    def test_version_numbers_increment_monotonically(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        versions = [r.create_version(s.id, SAMPLE_JSON) for _ in range(5)]
        numbers = [v.version_number for v in versions]
        assert numbers == list(range(1, 6))

    def test_version_numbers_independent_per_scenario(self, db):
        """Two different scenarios each start their version counter at 1."""
        r = repo(db)
        s1 = r.create_scenario(unique_slug("alpha"), "T")
        s2 = r.create_scenario(unique_slug("beta"), "T")
        v1 = r.create_version(s1.id, SAMPLE_JSON)
        v2 = r.create_version(s2.id, SAMPLE_JSON)
        assert v1.version_number == 1
        assert v2.version_number == 1

    def test_default_status_is_draft(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        assert v.status == VersionStatus.draft

    def test_explicit_status_stored(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)
        assert v.status == VersionStatus.published

    def test_scenario_json_stored(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        db.expire(v)
        loaded = db.get(ScenarioVersion, v.id)
        assert loaded.scenario_json["metadata"]["title"] == "Test"

    def test_scenario_id_linked(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        assert v.scenario_id == s.id


# ---------------------------------------------------------------------------
# get_published_version
# ---------------------------------------------------------------------------


class TestGetPublishedVersion:
    def test_returns_none_when_no_published(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON)  # draft
        assert r.get_published_version(s.slug) is None

    def test_returns_published_version(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)
        found = r.get_published_version(s.slug)
        assert found is not None
        assert found.id == v.id

    def test_returns_none_for_unknown_slug(self, db):
        assert repo(db).get_published_version("no-such-slug") is None

    def test_ignores_draft_versions(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.draft)
        r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.archived)
        assert r.get_published_version(s.slug) is None

    def test_returns_highest_version_number_when_multiple_published(self, db):
        """If somehow two versions are published, the highest number wins."""
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)
        v2 = r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)
        found = r.get_published_version(s.slug)
        assert found.id == v2.id


# ---------------------------------------------------------------------------
# publish_version
# ---------------------------------------------------------------------------


class TestPublishVersion:
    def test_returns_version(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        result = r.publish_version(v.id)
        assert result is not None
        assert result.id == v.id

    def test_status_becomes_published(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON)
        r.publish_version(v.id)
        db.expire(v)
        assert db.get(ScenarioVersion, v.id).status == VersionStatus.published

    def test_returns_none_for_unknown_id(self, db):
        result = repo(db).publish_version(uuid.uuid4())
        assert result is None

    def test_previous_published_version_archived(self, db):
        """Publishing v2 should archive the previously published v1."""
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v1 = r.create_version(s.id, SAMPLE_JSON)
        v2 = r.create_version(s.id, SAMPLE_JSON)

        r.publish_version(v1.id)
        r.publish_version(v2.id)

        db.expire(v1)
        db.expire(v2)
        assert db.get(ScenarioVersion, v1.id).status == VersionStatus.archived
        assert db.get(ScenarioVersion, v2.id).status == VersionStatus.published

    def test_only_one_published_after_publish(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        versions = [r.create_version(s.id, SAMPLE_JSON) for _ in range(3)]
        for v in versions:
            r.publish_version(v.id)  # publish each in turn

        db.expire_all()
        found = r.get_by_slug(s.slug)
        published = [v for v in found.versions if v.status == VersionStatus.published]
        assert len(published) == 1
        assert published[0].id == versions[-1].id


# ---------------------------------------------------------------------------
# archive_version
# ---------------------------------------------------------------------------


class TestArchiveVersion:
    def test_status_becomes_archived(self, db):
        r = repo(db)
        s = r.create_scenario(unique_slug(), "T")
        v = r.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)
        r.archive_version(v.id)
        db.expire(v)
        assert db.get(ScenarioVersion, v.id).status == VersionStatus.archived

    def test_returns_none_for_unknown_id(self, db):
        assert repo(db).archive_version(uuid.uuid4()) is None
