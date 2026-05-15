"""
SQLAlchemy ORM models for play sessions, event sourcing, and reflections.

Design decisions
----------------
* ``Play`` pins a specific ``ScenarioVersion`` so edits never corrupt
  in-flight sessions.
* ``Event`` rows are the source of truth for session state.  The engine
  replays them to reconstruct ``EngineState`` on go-back or resume.
  ``seq`` is assigned by the repository layer (monotonically per play).
* ``delta_json`` stores variable deltas (effects) so analytics can
  aggregate variable changes without re-running the engine.
* ``Reflection`` is 1-to-1 with ``Play`` (unique FK).  Submitted once
  after completion; never updated.
* All cascade deletes flow through ``Play`` — deleting a play removes
  its events and reflection automatically.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
# Enums
# ---------------------------------------------------------------------------


class EventType(str, enum.Enum):
    """All event types recorded during a play session."""

    start = "start"
    view_scene = "view_scene"
    choose = "choose"
    auto_advance = "auto_advance"
    conditional_advance = "conditional_advance"
    go_back = "go_back"
    complete = "complete"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Play(Base):
    """A single learner's play session, pinned to one scenario version."""

    __tablename__ = "plays"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    scenario_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("scenario_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Pinned version — never changes after play is created",
    )
    learner_label: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional free-text label supplied by the learner",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    outcome: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Value from EndScene.outcome — populated on completion",
    )
    outcome_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    events: Mapped[list[Event]] = relationship(
        "Event",
        back_populates="play",
        order_by="Event.seq",
        cascade="all, delete-orphan",
    )
    reflection: Mapped[Reflection | None] = relationship(
        "Reflection",
        back_populates="play",
        uselist=False,
        cascade="all, delete-orphan",
    )
    scenario_version: Mapped["ScenarioVersion"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ScenarioVersion",
    )

    def __repr__(self) -> str:
        return (
            f"<Play id={self.id}"
            f" version={self.scenario_version_id}"
            f" completed={self.completed}>"
        )


class Event(Base):
    """One step in the event log for a play session.

    ``seq`` starts at 1 and increments per play.  The repository layer is
    responsible for assigning the next seq value atomically.
    """

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    play_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plays.id", ondelete="CASCADE"),
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing per play, starting at 1",
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="eventtype", create_type=True),
        nullable=False,
    )
    scene_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Scene where the action was taken",
    )
    choice_index: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Populated for 'choose' events",
    )
    choice_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Denormalised text of the chosen option",
    )
    next_scene_id: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Scene transitioned to",
    )
    delta_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Variable deltas applied by this event, e.g. {confidence: 1}",
    )

    # Relationship
    play: Mapped[Play] = relationship("Play", back_populates="events")

    __table_args__ = (
        UniqueConstraint("play_id", "seq", name="uq_events_play_seq"),
        Index("ix_events_play_id_seq", "play_id", "seq"),
    )

    def __repr__(self) -> str:
        return (
            f"<Event play={self.play_id}"
            f" seq={self.seq}"
            f" type={self.event_type.value!r}"
            f" scene={self.scene_id!r}>"
        )


class Reflection(Base):
    """Learner reflection submitted after completing a play.

    One reflection per play (enforced by unique FK).  The ``responses_json``
    field stores answers keyed by question index or prompt text — the schema
    is intentionally flexible to accommodate different scenario formats.
    """

    __tablename__ = "reflections"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    play_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("plays.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="One reflection per play",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    student_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    responses_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Free-form responses keyed by question index or prompt text",
    )

    # Relationship
    play: Mapped[Play] = relationship("Play", back_populates="reflection")

    def __repr__(self) -> str:
        return f"<Reflection id={self.id} play={self.play_id}>"
