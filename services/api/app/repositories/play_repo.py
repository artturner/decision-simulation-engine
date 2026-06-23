"""
Repository for play sessions, event sourcing, and reflections.

Design
------
``PlayRepository`` receives a SQLAlchemy ``Session`` at construction time.
All methods ``flush()`` after writes; the caller owns the transaction.

Event sequence numbers
----------------------
``seq`` is monotonically increasing per play and assigned here.
``create_play`` inserts a ``start`` event at ``seq=0``.
Every subsequent ``append_event`` call increments from the current max,
so events are numbered 0, 1, 2, …

Go-back (rewind)
----------------
``truncate_events_after(play_id, seq)`` deletes all events with
``seq > seq`` so the engine can replay the surviving events to rebuild
the previous ``EngineState``.  The API layer decides which seq to keep.

Engine replay format
--------------------
``events_for_engine(play_id)`` converts the event rows to the dict
format expected by ``ScenarioEngine.rewind()``:
  {scene_id, next_scene_id, choice_index, choice_text}
``start`` and ``complete`` events are excluded — they carry no state
transition information the engine needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.play import Event, EventType, Play, Reflection


class PlayRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Play lifecycle
    # ------------------------------------------------------------------

    def create_play(
        self,
        scenario_version_id: uuid.UUID,
        learner_label: str | None = None,
        class_roll_id: uuid.UUID | None = None,
    ) -> Play:
        """Create a new play session and record the initial ``start`` event.

        The ``start`` event is always at ``seq=0``.

        Raises:
            sqlalchemy.exc.IntegrityError: ``scenario_version_id`` does not exist.
        """
        play = Play(
            scenario_version_id=scenario_version_id,
            learner_label=learner_label,
            class_roll_id=class_roll_id,
        )
        self.db.add(play)
        self.db.flush()  # populate play.id

        # Record the start event at seq=0
        start_event = Event(
            play_id=play.id,
            seq=0,
            event_type=EventType.start,
        )
        self.db.add(start_event)
        self.db.flush()
        return play

    def get_play(self, play_id: uuid.UUID) -> Play | None:
        """Return the play for *play_id*, or ``None``."""
        return self.db.get(Play, play_id)

    def get_play_with_events(self, play_id: uuid.UUID) -> Play | None:
        """Return the play with its events eagerly loaded, or ``None``."""
        return self.db.scalar(
            select(Play)
            .options(selectinload(Play.events))
            .where(Play.id == play_id)
        )

    def find_in_progress(
        self,
        *,
        class_roll_id: uuid.UUID,
        learner_label: str,
        scenario_version_id: uuid.UUID,
    ) -> Play | None:
        """Return the most recent unfinished play for a roll student/version."""
        stmt = (
            select(Play)
            .where(
                Play.class_roll_id == class_roll_id,
                Play.learner_label == learner_label,
                Play.scenario_version_id == scenario_version_id,
                Play.completed.is_(False),
            )
            .order_by(Play.started_at.desc())
        )
        return self.db.scalars(stmt).first()

    def count_completed_attempts(
        self,
        *,
        class_roll_id: uuid.UUID,
        learner_label: str,
        scenario_version_id: uuid.UUID,
    ) -> int:
        """Count completed plays for a roll student/version."""
        stmt = select(func.count()).select_from(Play).where(
            Play.class_roll_id == class_roll_id,
            Play.learner_label == learner_label,
            Play.scenario_version_id == scenario_version_id,
            Play.completed.is_(True),
        )
        return int(self.db.scalar(stmt) or 0)

    def latest_completed_attempt(
        self,
        *,
        class_roll_id: uuid.UUID,
        learner_label: str,
        scenario_version_id: uuid.UUID,
    ) -> Play | None:
        """Return the most recently completed play for a roll student/version."""
        stmt = (
            select(Play)
            .where(
                Play.class_roll_id == class_roll_id,
                Play.learner_label == learner_label,
                Play.scenario_version_id == scenario_version_id,
                Play.completed.is_(True),
            )
            .order_by(Play.ended_at.desc().nulls_last(), Play.started_at.desc())
        )
        return self.db.scalars(stmt).first()

    def complete_play(
        self,
        play_id: uuid.UUID,
        outcome: str | None = None,
        outcome_message: str | None = None,
        scene_id: str | None = None,
    ) -> Play | None:
        """Mark a play as completed and append a ``complete`` event.

        Returns:
            The updated ``Play``, or ``None`` if not found.
        """
        play = self.db.get(Play, play_id)
        if play is None:
            return None

        play.completed = True
        play.outcome = outcome
        play.outcome_message = outcome_message
        play.ended_at = datetime.now(timezone.utc)
        self.db.flush()

        self.append_event(
            play_id=play_id,
            event_type=EventType.complete,
            scene_id=scene_id,
        )
        return play

    # ------------------------------------------------------------------
    # Event sourcing
    # ------------------------------------------------------------------

    def append_event(
        self,
        play_id: uuid.UUID,
        event_type: EventType,
        scene_id: str | None = None,
        choice_index: int | None = None,
        choice_text: str | None = None,
        next_scene_id: str | None = None,
        delta_json: dict | None = None,
    ) -> Event:
        """Append a new event to the play's event log.

        ``seq`` is set to ``current_max_seq + 1`` (the ``start`` event at
        seq=0 is always present, so the first appended event gets seq=1).
        """
        current_max: int | None = self.db.scalar(
            select(func.max(Event.seq)).where(Event.play_id == play_id)
        )
        next_seq = (current_max if current_max is not None else -1) + 1

        event = Event(
            play_id=play_id,
            seq=next_seq,
            event_type=event_type,
            scene_id=scene_id,
            choice_index=choice_index,
            choice_text=choice_text,
            next_scene_id=next_scene_id,
            delta_json=delta_json,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def get_events(self, play_id: uuid.UUID) -> list[Event]:
        """Return all events for *play_id* ordered by ``seq`` ascending."""
        return list(
            self.db.scalars(
                select(Event)
                .where(Event.play_id == play_id)
                .order_by(Event.seq)
            ).all()
        )

    def truncate_events_after(self, play_id: uuid.UUID, seq: int) -> int:
        """Delete all events with ``seq > seq`` for *play_id*.

        Used by the go-back endpoint to remove the last step before
        replaying remaining events through the engine.

        Returns:
            The number of rows deleted.
        """
        result = self.db.execute(
            delete(Event).where(
                Event.play_id == play_id,
                Event.seq > seq,
            )
        )
        self.db.flush()
        return result.rowcount

    def events_for_engine(self, play_id: uuid.UUID) -> list[dict]:
        """Return events in the dict format expected by ``ScenarioEngine.rewind()``.

        Excluded event types:
        - ``start``      — no scene transition, just marks session open
        - ``complete``   — no scene transition, marks session closed
        - ``view_scene`` — observational only; replaying it would incorrectly
                           advance AutoAdvance/Conditional scenes past the scene
                           the player is currently viewing
        """
        excluded = {EventType.start, EventType.complete, EventType.view_scene}
        return [
            {
                "scene_id": e.scene_id,
                "next_scene_id": e.next_scene_id,
                "choice_index": e.choice_index,
                "choice_text": e.choice_text,
            }
            for e in self.get_events(play_id)
            if e.event_type not in excluded
        ]

    # ------------------------------------------------------------------
    # Reflection
    # ------------------------------------------------------------------

    def add_reflection(
        self,
        play_id: uuid.UUID,
        responses_json: dict,
        student_name: str | None = None,
    ) -> Reflection:
        """Record a learner reflection for a completed play.

        Raises:
            sqlalchemy.exc.IntegrityError: A reflection already exists for
                this play (unique constraint on ``play_id``).
        """
        reflection = Reflection(
            play_id=play_id,
            responses_json=responses_json,
            student_name=student_name,
        )
        self.db.add(reflection)
        self.db.flush()
        return reflection

    def get_reflection(self, play_id: uuid.UUID) -> Reflection | None:
        """Return the reflection for *play_id*, or ``None``."""
        return self.db.scalar(
            select(Reflection).where(Reflection.play_id == play_id)
        )

    def upsert_reflection(
        self,
        play_id: uuid.UUID,
        responses_json: dict,
        student_name: str | None = None,
    ) -> Reflection:
        """Create or update the (unaccepted) reflection for *play_id*.

        Used by the grade endpoint, where the learner may revise and re-grade
        their answers until they accept the score.  Callers must check
        ``accepted`` before mutating — an accepted reflection is locked.
        """
        reflection = self.get_reflection(play_id)
        if reflection is None:
            reflection = Reflection(
                play_id=play_id,
                responses_json=responses_json,
                student_name=student_name,
            )
            self.db.add(reflection)
        else:
            reflection.responses_json = responses_json
            if student_name is not None:
                reflection.student_name = student_name
        self.db.flush()
        return reflection

    def save_grade(
        self,
        reflection: Reflection,
        *,
        grade_total: int,
        grade_breakdown: dict,
        feedback: str,
        grader_model: str,
        graded_at,
    ) -> Reflection:
        """Persist grade fields and increment the attempt counter."""
        reflection.grade_total = grade_total
        reflection.grade_breakdown = grade_breakdown
        reflection.feedback = feedback
        reflection.grader_model = grader_model
        reflection.graded_at = graded_at
        reflection.grade_attempts = (reflection.grade_attempts or 0) + 1
        self.db.flush()
        return reflection

    def accept_reflection(self, reflection: Reflection, accepted_at) -> Reflection:
        """Mark a reflection as accepted (locks further edits/grading)."""
        reflection.accepted = True
        reflection.accepted_at = accepted_at
        self.db.flush()
        return reflection
