"""Data access for class rolls and scenario-roll assignments."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.assignment import ScenarioRollAssignment
from app.models.user import ClassRoll, generate_join_code


class RollRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # ClassRoll CRUD
    # ------------------------------------------------------------------

    def create(self, owner_id: uuid.UUID, name: str, student_names: list[str]) -> ClassRoll:
        for _ in range(10):
            join_code = generate_join_code()
            if self.get_by_join_code(join_code) is not None:
                continue
            roll = ClassRoll(
                owner_id=owner_id,
                name=name,
                student_names=student_names,
                join_code=join_code,
            )
            self._db.add(roll)
            self._db.flush()
            return roll
        raise RuntimeError("Could not generate a unique join code")

    def get(self, roll_id: uuid.UUID) -> ClassRoll | None:
        return self._db.get(ClassRoll, roll_id)

    def get_by_join_code(self, code: str) -> ClassRoll | None:
        normalized = code.strip().upper()
        stmt = select(ClassRoll).where(func.upper(ClassRoll.join_code) == normalized)
        return self._db.scalars(stmt).first()

    def list_for_owner(self, owner_id: uuid.UUID) -> list[ClassRoll]:
        stmt = select(ClassRoll).where(ClassRoll.owner_id == owner_id).order_by(ClassRoll.name)
        return list(self._db.scalars(stmt))

    def update(
        self,
        roll: ClassRoll,
        *,
        name: str | None = None,
        student_names: list[str] | None = None,
    ) -> ClassRoll:
        if name is not None:
            roll.name = name
        if student_names is not None:
            roll.student_names = student_names
        self._db.flush()
        return roll

    def delete(self, roll: ClassRoll) -> None:
        self._db.delete(roll)
        self._db.flush()

    # ------------------------------------------------------------------
    # ScenarioRollAssignment CRUD
    # ------------------------------------------------------------------

    def assign_scenario(
        self,
        scenario_id: uuid.UUID,
        roll_id: uuid.UUID,
        *,
        visible: bool = False,
        sort_order: int | None = None,
    ) -> ScenarioRollAssignment:
        assignment = ScenarioRollAssignment(
            scenario_id=scenario_id,
            class_roll_id=roll_id,
            visible=visible,
            sort_order=sort_order,
        )
        self._db.add(assignment)
        self._db.flush()
        return assignment

    def get_assignment(
        self, scenario_id: uuid.UUID, roll_id: uuid.UUID
    ) -> ScenarioRollAssignment | None:
        stmt = select(ScenarioRollAssignment).where(
            ScenarioRollAssignment.scenario_id == scenario_id,
            ScenarioRollAssignment.class_roll_id == roll_id,
        )
        return self._db.scalars(stmt).first()

    def list_assignments_for_roll(self, roll_id: uuid.UUID) -> list[ScenarioRollAssignment]:
        stmt = (
            select(ScenarioRollAssignment)
            .where(ScenarioRollAssignment.class_roll_id == roll_id)
            .order_by(ScenarioRollAssignment.sort_order.nulls_last(), ScenarioRollAssignment.created_at)
        )
        return list(self._db.scalars(stmt))

    def update_assignment(
        self,
        assignment: ScenarioRollAssignment,
        *,
        visible: bool | None = None,
        sort_order: int | None = None,
    ) -> ScenarioRollAssignment:
        if visible is not None:
            assignment.visible = visible
        if sort_order is not None:
            assignment.sort_order = sort_order
        self._db.flush()
        return assignment

    def remove_assignment(self, assignment: ScenarioRollAssignment) -> None:
        self._db.delete(assignment)
        self._db.flush()

    def visible_assignments_for_roll(self, roll_id: uuid.UUID) -> list[ScenarioRollAssignment]:
        """Return assignments where visible=True, ordered for the class picker."""
        stmt = (
            select(ScenarioRollAssignment)
            .where(
                ScenarioRollAssignment.class_roll_id == roll_id,
                ScenarioRollAssignment.visible.is_(True),
            )
            .order_by(ScenarioRollAssignment.sort_order.nulls_last(), ScenarioRollAssignment.created_at)
        )
        return list(self._db.scalars(stmt))
