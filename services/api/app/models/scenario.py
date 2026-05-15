"""
SQLAlchemy ORM models for scenarios and their versioned snapshots.

Design decisions
----------------
* UUID primary keys — avoids sequential ID enumeration in public URLs.
* ``scenario_versions.scenario_json`` is JSONB so Postgres can index and
  query inside the document without a separate text column.
* ``VersionStatus`` is a native Postgres enum (stored as a type, not
  varchar) so the database enforces the allowed values.
* ``version_number`` is monotonically increasing *per scenario* (managed
  by the repository layer, not the DB).  The unique constraint on
  (scenario_id, version_number) enforces this at the DB level.
* ``updated_at`` on ``Scenario`` tracks the last time *metadata*
  changed; version creation does not bump this column.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------


class VersionStatus(str, enum.Enum):
    """Lifecycle states for a scenario version."""

    draft = "draft"
    published = "published"
    archived = "archived"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Scenario(Base):
    """Top-level scenario record.  Immutable identity — all content lives in
    ``ScenarioVersion`` rows."""

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(200),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-safe identifier used in public links",
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationship — ordered so newest version is last
    versions: Mapped[list[ScenarioVersion]] = relationship(
        "ScenarioVersion",
        back_populates="scenario",
        order_by="ScenarioVersion.version_number",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Scenario id={self.id} slug={self.slug!r}>"


class ScenarioVersion(Base):
    """Immutable snapshot of a scenario's JSON at a point in time.

    Once created a version's ``scenario_json`` must never be updated —
    create a new version instead.  This guarantees in-flight plays are
    not broken by edits.
    """

    __tablename__ = "scenario_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    scenario_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scenarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing per scenario, assigned by repository layer",
    )
    status: Mapped[VersionStatus] = mapped_column(
        SAEnum(VersionStatus, name="versionstatus", create_type=True),
        nullable=False,
        default=VersionStatus.draft,
    )
    scenario_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full scenario document as imported",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationship
    scenario: Mapped[Scenario] = relationship(
        "Scenario",
        back_populates="versions",
    )

    __table_args__ = (
        UniqueConstraint(
            "scenario_id",
            "version_number",
            name="uq_scenario_versions_scenario_version",
        ),
        Index("ix_scenario_versions_status", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<ScenarioVersion id={self.id}"
            f" scenario_id={self.scenario_id}"
            f" v{self.version_number}"
            f" status={self.status.value!r}>"
        )
