"""
Repository for scenario and scenario-version data access.

Design
------
``ScenarioRepository`` receives a SQLAlchemy ``Session`` at construction
time (dependency-injection pattern).  All methods ``flush()`` after
writes so that the caller controls when the transaction is committed or
rolled back — no ``commit()`` calls here.

Version numbering
-----------------
``version_number`` is monotonically increasing per scenario and is
assigned here rather than in the database.  ``func.max()`` + 1 inside
the same transaction is safe for a synchronous, single-writer model
(the API runs one process; no concurrent import workers are expected at
MVP scale).  A DB-level sequence can replace this trivially later.

Publishing
----------
``publish_version`` archives any previously published version for the
same scenario before marking the target as published, so at most one
version is live at any time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.scenario import Scenario, ScenarioVersion, VersionStatus


class ScenarioRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Scenario CRUD
    # ------------------------------------------------------------------

    def create_scenario(
        self,
        slug: str,
        title: str,
        description: str = "",
    ) -> Scenario:
        """Insert a new top-level scenario record.

        Raises:
            sqlalchemy.exc.IntegrityError: ``slug`` already exists.
        """
        scenario = Scenario(slug=slug, title=title, description=description)
        self.db.add(scenario)
        self.db.flush()
        return scenario

    def get_by_slug(self, slug: str) -> Scenario | None:
        """Return the scenario for *slug* with its versions eagerly loaded,
        or ``None`` if no such slug exists."""
        return self.db.scalar(
            select(Scenario)
            .options(selectinload(Scenario.versions))
            .where(Scenario.slug == slug)
        )

    def get_by_id(self, scenario_id: uuid.UUID) -> Scenario | None:
        """Return the scenario for *scenario_id*, or ``None``."""
        return self.db.get(Scenario, scenario_id)

    # ------------------------------------------------------------------
    # Version CRUD
    # ------------------------------------------------------------------

    def create_version(
        self,
        scenario_id: uuid.UUID,
        scenario_json: dict,
        status: VersionStatus = VersionStatus.draft,
    ) -> ScenarioVersion:
        """Create a new version for *scenario_id* with an auto-incremented
        ``version_number``.

        The first version for a scenario receives ``version_number=1``.

        Raises:
            sqlalchemy.exc.IntegrityError: ``scenario_id`` does not exist.
        """
        current_max: int | None = self.db.scalar(
            select(func.max(ScenarioVersion.version_number)).where(
                ScenarioVersion.scenario_id == scenario_id
            )
        )
        next_number = (current_max or 0) + 1

        version = ScenarioVersion(
            scenario_id=scenario_id,
            version_number=next_number,
            status=status,
            scenario_json=scenario_json,
        )
        self.db.add(version)
        self.db.flush()
        return version

    def get_version_by_id(self, version_id: uuid.UUID) -> ScenarioVersion | None:
        """Return the version for *version_id*, or ``None``."""
        return self.db.get(ScenarioVersion, version_id)

    def get_published_version(self, slug: str) -> ScenarioVersion | None:
        """Return the published version with the highest version_number for
        *slug*, or ``None`` if no published version exists."""
        return self.db.scalar(
            select(ScenarioVersion)
            .join(Scenario, ScenarioVersion.scenario_id == Scenario.id)
            .where(
                Scenario.slug == slug,
                ScenarioVersion.status == VersionStatus.published,
            )
            .order_by(ScenarioVersion.version_number.desc())
            .limit(1)
        )

    def publish_version(self, version_id: uuid.UUID) -> ScenarioVersion | None:
        """Mark *version_id* as published.

        Any previously published version for the same scenario is
        automatically archived so at most one version is live at a time.

        Returns:
            The updated ``ScenarioVersion``, or ``None`` if not found.
        """
        version = self.db.get(ScenarioVersion, version_id)
        if version is None:
            return None

        # Archive any existing published version(s) for this scenario.
        previously_published = self.db.scalars(
            select(ScenarioVersion).where(
                ScenarioVersion.scenario_id == version.scenario_id,
                ScenarioVersion.status == VersionStatus.published,
                ScenarioVersion.id != version_id,
            )
        ).all()
        for old in previously_published:
            old.status = VersionStatus.archived

        version.status = VersionStatus.published
        self.db.flush()
        return version

    def archive_version(self, version_id: uuid.UUID) -> ScenarioVersion | None:
        """Mark *version_id* as archived.

        Returns:
            The updated ``ScenarioVersion``, or ``None`` if not found.
        """
        version = self.db.get(ScenarioVersion, version_id)
        if version is None:
            return None
        version.status = VersionStatus.archived
        self.db.flush()
        return version
