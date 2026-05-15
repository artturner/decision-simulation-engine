"""
Integration tests for Play, Event, and Reflection ORM models.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a transaction rolled back on teardown.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.scenario import Scenario, ScenarioVersion, VersionStatus
from app.models.play import Event, EventType, Play, Reflection

SAMPLE_JSON: dict = {
    "metadata": {"title": "Test"},
    "variables": {},
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


def make_version(db) -> ScenarioVersion:
    scenario = Scenario(slug=f"s-{uuid.uuid4().hex[:8]}", title="T")
    db.add(scenario)
    db.flush()
    version = ScenarioVersion(
        scenario_id=scenario.id,
        version_number=1,
        status=VersionStatus.published,
        scenario_json=SAMPLE_JSON,
    )
    db.add(version)
    db.flush()
    return version


def make_play(db, version: ScenarioVersion | None = None, **kwargs) -> Play:
    if version is None:
        version = make_version(db)
    play = Play(scenario_version_id=version.id, **kwargs)
    db.add(play)
    db.flush()
    return play


def make_event(
    db,
    play: Play,
    seq: int = 1,
    event_type: EventType = EventType.start,
    scene_id: str = "1",
    **kwargs,
) -> Event:
    event = Event(
        play_id=play.id,
        seq=seq,
        event_type=event_type,
        scene_id=scene_id,
        **kwargs,
    )
    db.add(event)
    db.flush()
    return event


def make_reflection(
    db,
    play: Play,
    responses: dict | None = None,
) -> Reflection:
    reflection = Reflection(
        play_id=play.id,
        responses_json=responses or {"q1": "answer"},
    )
    db.add(reflection)
    db.flush()
    return reflection


# ---------------------------------------------------------------------------
# Play model
# ---------------------------------------------------------------------------


class TestPlayModel:
    def test_create_play(self, db):
        play = make_play(db)
        assert play.id is not None
        assert isinstance(play.id, uuid.UUID)

    def test_completed_defaults_false(self, db):
        play = make_play(db)
        db.expire(play)
        loaded = db.get(Play, play.id)
        assert loaded.completed is False

    def test_learner_label_stored(self, db):
        play = make_play(db, learner_label="Alice")
        db.expire(play)
        loaded = db.get(Play, play.id)
        assert loaded.learner_label == "Alice"

    def test_learner_label_nullable(self, db):
        play = make_play(db)
        assert play.learner_label is None

    def test_started_at_set_by_db(self, db):
        play = make_play(db)
        db.expire(play)
        loaded = db.get(Play, play.id)
        assert loaded.started_at is not None

    def test_ended_at_nullable(self, db):
        play = make_play(db)
        assert play.ended_at is None

    def test_outcome_nullable(self, db):
        play = make_play(db)
        assert play.outcome is None

    def test_scenario_version_relationship(self, db):
        version = make_version(db)
        play = make_play(db, version=version)
        assert play.scenario_version.id == version.id

    def test_events_empty_initially(self, db):
        play = make_play(db)
        assert play.events == []

    def test_reflection_none_initially(self, db):
        play = make_play(db)
        assert play.reflection is None

    def test_repr(self, db):
        play = make_play(db)
        assert "Play" in repr(play)
        assert "completed=False" in repr(play)


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------


class TestEventModel:
    def test_create_event(self, db):
        play = make_play(db)
        event = make_event(db, play)
        assert event.id is not None

    def test_event_type_stored(self, db):
        play = make_play(db)
        event = make_event(db, play, event_type=EventType.choose)
        db.expire(event)
        loaded = db.get(Event, event.id)
        assert loaded.event_type == EventType.choose

    def test_all_event_types_valid(self, db):
        play = make_play(db)
        for i, et in enumerate(EventType, start=1):
            e = make_event(db, play, seq=i, event_type=et)
            assert e.event_type == et

    def test_choice_fields_stored(self, db):
        play = make_play(db)
        event = make_event(
            db,
            play,
            event_type=EventType.choose,
            choice_index=2,
            choice_text="Bold move",
            next_scene_id="end",
        )
        db.expire(event)
        loaded = db.get(Event, event.id)
        assert loaded.choice_index == 2
        assert loaded.choice_text == "Bold move"
        assert loaded.next_scene_id == "end"

    def test_delta_json_stored(self, db):
        play = make_play(db)
        event = make_event(db, play, delta_json={"confidence": 1.0})
        db.expire(event)
        loaded = db.get(Event, event.id)
        assert loaded.delta_json == {"confidence": 1.0}

    def test_nullable_fields_default_to_none(self, db):
        play = make_play(db)
        event = make_event(db, play)
        assert event.choice_index is None
        assert event.choice_text is None
        assert event.next_scene_id is None
        assert event.delta_json is None

    def test_ts_set_by_db(self, db):
        play = make_play(db)
        event = make_event(db, play)
        db.expire(event)
        loaded = db.get(Event, event.id)
        assert loaded.ts is not None

    def test_play_relationship(self, db):
        play = make_play(db)
        event = make_event(db, play)
        assert event.play.id == play.id

    def test_events_ordered_by_seq(self, db):
        play = make_play(db)
        make_event(db, play, seq=3, event_type=EventType.choose)
        make_event(db, play, seq=1, event_type=EventType.start)
        make_event(db, play, seq=2, event_type=EventType.view_scene)
        db.expire(play)
        loaded = db.get(Play, play.id)
        seqs = [e.seq for e in loaded.events]
        assert seqs == [1, 2, 3]

    def test_unique_constraint_play_seq(self, db):
        """(play_id, seq) must be unique."""
        play = make_play(db)
        make_event(db, play, seq=1)
        with pytest.raises(IntegrityError):
            make_event(db, play, seq=1)

    def test_cascade_delete_with_play(self, db):
        play = make_play(db)
        event = make_event(db, play, seq=1)
        event_id = event.id
        db.delete(play)
        db.flush()
        assert db.get(Event, event_id) is None

    def test_repr(self, db):
        play = make_play(db)
        event = make_event(db, play, event_type=EventType.start, scene_id="intro")
        assert "start" in repr(event)
        assert "intro" in repr(event)


# ---------------------------------------------------------------------------
# Reflection model
# ---------------------------------------------------------------------------


class TestReflectionModel:
    def test_create_reflection(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        assert ref.id is not None

    def test_responses_json_round_trips(self, db):
        play = make_play(db)
        responses = {"q1": "Because it mattered.", "q2": "I felt confident."}
        ref = make_reflection(db, play, responses=responses)
        db.expire(ref)
        loaded = db.get(Reflection, ref.id)
        assert loaded.responses_json == responses

    def test_student_name_stored(self, db):
        play = make_play(db)
        ref = Reflection(
            play_id=play.id,
            student_name="Bob",
            responses_json={},
        )
        db.add(ref)
        db.flush()
        db.expire(ref)
        loaded = db.get(Reflection, ref.id)
        assert loaded.student_name == "Bob"

    def test_student_name_nullable(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        assert ref.student_name is None

    def test_submitted_at_set_by_db(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        db.expire(ref)
        loaded = db.get(Reflection, ref.id)
        assert loaded.submitted_at is not None

    def test_play_relationship(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        assert ref.play.id == play.id

    def test_play_reflection_back_relationship(self, db):
        play = make_play(db)
        make_reflection(db, play)
        db.expire(play)
        loaded = db.get(Play, play.id)
        assert loaded.reflection is not None

    def test_unique_constraint_one_reflection_per_play(self, db):
        """A play can have at most one reflection."""
        play = make_play(db)
        make_reflection(db, play)
        with pytest.raises(IntegrityError):
            make_reflection(db, play)

    def test_cascade_delete_with_play(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        ref_id = ref.id
        db.delete(play)
        db.flush()
        assert db.get(Reflection, ref_id) is None

    def test_repr(self, db):
        play = make_play(db)
        ref = make_reflection(db, play)
        assert "Reflection" in repr(ref)
