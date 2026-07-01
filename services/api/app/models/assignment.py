from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScenarioRollAssignment(Base):
    """Junction between a scenario and a class roll.

    Controls which scenarios appear in a class picker (visible=True) and
    in what order (sort_order).  The same scenario can be assigned to
    multiple rolls, and the same roll can contain many scenarios.
    """

    __tablename__ = "scenario_roll_assignments"

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
    class_roll_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("class_rolls.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the scenario appears in this roll's class picker",
    )
    sort_order: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Display order within the picker; lower numbers appear first",
    )
    grading_difficulty: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="standard",
        default="standard",
        comment="AI reflection grading leniency: strict | standard | lenient",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    scenario: Mapped[Scenario] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Scenario",
        back_populates="roll_assignments",
    )
    class_roll: Mapped[ClassRoll] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ClassRoll",
        back_populates="assignments",
    )

    __table_args__ = (
        UniqueConstraint(
            "scenario_id",
            "class_roll_id",
            name="uq_scenario_roll_assignments_scenario_roll",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ScenarioRollAssignment"
            f" scenario={self.scenario_id}"
            f" roll={self.class_roll_id}"
            f" visible={self.visible}>"
        )
