"""
Integration tests for PlayRepository.

Requires a running Postgres instance (docker compose up -d db).
Each test runs inside a rolled-back transaction for full isolation.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.play import Event, EventType, Play, Reflection
from app.models.scenario import Scenario, ScenarioVersion, VersionStatus
from app.repositories.play_repo import PlayRepository
from app.repositories.scenario_repo import ScenarioRepository

SAMPLE_JSON: dict = {
    "metadata": {"title": "Test"},
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {"type": "choice", "choices": [{"text": "Go", "next": "s2"}]},
        "s2": {"type": "end", "outcome": "success", "outcome_message": "Done."},
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_version(db) -> ScenarioVersion:
    sr = ScenarioRepository(db)
    s = sr.create_scenario(f"slug-{uuid.uuid4().hex[:8]}", "T")
    return sr.create_version(s.id, SAMPLE_JSON, status=VersionStatus.published)


def repo(db) -> PlayRepository:
    return PlayRepository(db)


# ---------------------------------------------------------------------------
# create_play
# ---------------------------------------------------------------------------


class TestCreatePlay:
    def test_returns_play(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        assert isinstance(play, Play)

    def test_id_assigned(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        assert isinstance(play.id, uuid.UUID)

    def test_scenario_version_id_stored(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        assert play.scenario_version_id == v.id

    def test_learner_label_stored(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id, learner_label="Alice")
        assert play.learner_label == "Alice"

    def test_learner_label_defaults_to_none(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        assert play.learner_label is None

    def test_completed_defaults_false(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        db.expire(play)
        assert db.get(Play, play.id).completed is False

    def test_start_event_created_at_seq_zero(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        events = r.get_events(play.id)
        assert len(events) == 1
        assert events[0].seq == 0
        assert events[0].event_type == EventType.start

    def test_invalid_version_id_raises(self, db):
        with pytest.raises(Exception):  # IntegrityError (FK violation)
            repo(db).create_play(uuid.uuid4())


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------


class TestAppendEvent:
    def test_returns_event(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        event = repo(db).append_event(play.id, EventType.view_scene, scene_id="s1")
        assert isinstance(event, Event)

    def test_first_appended_event_is_seq_one(self, db):
        """start event is seq=0; first append gives seq=1."""
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e = r.append_event(play.id, EventType.view_scene, scene_id="s1")
        assert e.seq == 1

    def test_seq_increments(self, db):
        """Events numbered 0, 1, 2, …"""
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e1 = r.append_event(play.id, EventType.view_scene, scene_id="s1")
        e2 = r.append_event(play.id, EventType.choose, scene_id="s1",
                             choice_index=0, next_scene_id="s2")
        assert e1.seq == 1
        assert e2.seq == 2

    def test_event_type_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e = r.append_event(play.id, EventType.choose, scene_id="s1",
                           choice_index=0, choice_text="Go", next_scene_id="s2")
        db.expire(e)
        loaded = db.get(Event, e.id)
        assert loaded.event_type == EventType.choose

    def test_choice_fields_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e = r.append_event(play.id, EventType.choose, scene_id="s1",
                           choice_index=0, choice_text="Go", next_scene_id="s2")
        db.expire(e)
        loaded = db.get(Event, e.id)
        assert loaded.choice_index == 0
        assert loaded.choice_text == "Go"
        assert loaded.next_scene_id == "s2"

    def test_delta_json_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e = r.append_event(play.id, EventType.choose, delta_json={"score": 1})
        db.expire(e)
        assert db.get(Event, e.id).delta_json == {"score": 1}

    def test_optional_fields_default_none(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        e = r.append_event(play.id, EventType.auto_advance)
        assert e.scene_id is None
        assert e.choice_index is None
        assert e.choice_text is None
        assert e.next_scene_id is None
        assert e.delta_json is None


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------


class TestGetEvents:
    def test_returns_list(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        events = repo(db).get_events(play.id)
        assert isinstance(events, list)

    def test_start_event_included(self, db):
        v = make_version(db)
        play = repo(db).create_play(v.id)
        events = repo(db).get_events(play.id)
        assert events[0].event_type == EventType.start

    def test_ordered_by_seq(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        r.append_event(play.id, EventType.choose)
        events = r.get_events(play.id)
        seqs = [e.seq for e in events]
        assert seqs == sorted(seqs)

    def test_correct_count(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        r.append_event(play.id, EventType.choose)
        # start(0) + view(1) + choose(2) = 3
        assert len(r.get_events(play.id)) == 3

    def test_empty_for_unknown_play(self, db):
        assert repo(db).get_events(uuid.uuid4()) == []


# ---------------------------------------------------------------------------
# get_play / get_play_with_events
# ---------------------------------------------------------------------------


class TestGetPlay:
    def test_get_play_returns_play(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        assert r.get_play(play.id).id == play.id

    def test_get_play_returns_none_for_unknown(self, db):
        assert repo(db).get_play(uuid.uuid4()) is None

    def test_get_play_with_events_loads_events(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        loaded = r.get_play_with_events(play.id)
        # Access events without triggering lazy-load error
        assert len(loaded.events) == 2  # start + view_scene

    def test_get_play_with_events_none_for_unknown(self, db):
        assert repo(db).get_play_with_events(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# complete_play
# ---------------------------------------------------------------------------


class TestCompletePlay:
    def test_returns_play(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        result = r.complete_play(play.id, outcome="success", outcome_message="Done!")
        assert result is not None
        assert result.id == play.id

    def test_completed_set_true(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.complete_play(play.id)
        db.expire(play)
        assert db.get(Play, play.id).completed is True

    def test_outcome_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.complete_play(play.id, outcome="success")
        db.expire(play)
        assert db.get(Play, play.id).outcome == "success"

    def test_outcome_message_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.complete_play(play.id, outcome_message="Well done!")
        db.expire(play)
        assert db.get(Play, play.id).outcome_message == "Well done!"

    def test_ended_at_set(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.complete_play(play.id)
        db.expire(play)
        assert db.get(Play, play.id).ended_at is not None

    def test_complete_event_appended(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.complete_play(play.id, scene_id="s2")
        events = r.get_events(play.id)
        types = [e.event_type for e in events]
        assert EventType.complete in types

    def test_returns_none_for_unknown_play(self, db):
        assert repo(db).complete_play(uuid.uuid4()) is None


# ---------------------------------------------------------------------------
# truncate_events_after
# ---------------------------------------------------------------------------


class TestTruncateEventsAfter:
    def test_removes_events_beyond_seq(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)           # seq=0
        r.append_event(play.id, EventType.view_scene)  # seq=1
        r.append_event(play.id, EventType.choose)      # seq=2
        r.append_event(play.id, EventType.auto_advance) # seq=3

        r.truncate_events_after(play.id, seq=1)
        remaining = r.get_events(play.id)
        seqs = [e.seq for e in remaining]
        assert seqs == [0, 1]

    def test_returns_deleted_count(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        r.append_event(play.id, EventType.choose)
        deleted = r.truncate_events_after(play.id, seq=0)
        assert deleted == 2

    def test_seq_kept_is_not_deleted(self, db):
        """Event at exactly the given seq is preserved."""
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        r.truncate_events_after(play.id, seq=1)
        remaining = r.get_events(play.id)
        assert any(e.seq == 1 for e in remaining)

    def test_truncate_all_after_zero(self, db):
        """Keeping only the start event restores to initial state."""
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.view_scene)
        r.append_event(play.id, EventType.choose)
        r.truncate_events_after(play.id, seq=0)
        remaining = r.get_events(play.id)
        assert len(remaining) == 1
        assert remaining[0].event_type == EventType.start

    def test_no_op_when_no_events_beyond_seq(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        deleted = r.truncate_events_after(play.id, seq=99)
        assert deleted == 0


# ---------------------------------------------------------------------------
# events_for_engine
# ---------------------------------------------------------------------------


class TestEventsForEngine:
    def test_excludes_start_event(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        engine_events = r.events_for_engine(play.id)
        assert all(e.get("event_type") != "start" for e in engine_events)
        # With only a start event, result should be empty
        assert engine_events == []

    def test_includes_choose_event(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.choose, scene_id="s1",
                       choice_index=0, next_scene_id="s2")
        engine_events = r.events_for_engine(play.id)
        assert len(engine_events) == 1
        assert engine_events[0]["scene_id"] == "s1"
        assert engine_events[0]["choice_index"] == 0
        assert engine_events[0]["next_scene_id"] == "s2"

    def test_excludes_complete_event(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.choose, scene_id="s1",
                       choice_index=0, next_scene_id="s2")
        r.complete_play(play.id, scene_id="s2")
        engine_events = r.events_for_engine(play.id)
        # Only the choose event should appear
        assert len(engine_events) == 1
        assert engine_events[0]["scene_id"] == "s1"

    def test_dict_has_required_keys(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.append_event(play.id, EventType.auto_advance, scene_id="s1",
                       next_scene_id="s2")
        engine_events = r.events_for_engine(play.id)
        assert len(engine_events) == 1
        assert set(engine_events[0].keys()) == {
            "scene_id", "next_scene_id", "choice_index", "choice_text"
        }


# ---------------------------------------------------------------------------
# add_reflection / get_reflection
# ---------------------------------------------------------------------------


class TestReflection:
    def test_add_reflection_returns_reflection(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        ref = r.add_reflection(play.id, {"q1": "Great experience."})
        assert isinstance(ref, Reflection)

    def test_responses_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.add_reflection(play.id, {"q1": "Learned a lot."})
        ref = r.get_reflection(play.id)
        assert ref.responses_json == {"q1": "Learned a lot."}

    def test_student_name_stored(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.add_reflection(play.id, {}, student_name="Charlie")
        ref = r.get_reflection(play.id)
        assert ref.student_name == "Charlie"

    def test_get_reflection_returns_none_when_absent(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        assert r.get_reflection(play.id) is None

    def test_duplicate_reflection_raises(self, db):
        v = make_version(db)
        r = repo(db)
        play = r.create_play(v.id)
        r.add_reflection(play.id, {"q1": "First."})
        with pytest.raises(IntegrityError):
            r.add_reflection(play.id, {"q1": "Second."})
