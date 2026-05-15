"""
State tests — HistoryEntry immutability, EngineState initialisation,
apply_effects behaviour, and serialisation round-trips.
"""

import pytest

from engine.state import EngineState, HistoryEntry


# ---------------------------------------------------------------------------
# HistoryEntry
# ---------------------------------------------------------------------------


class TestHistoryEntry:
    def test_required_fields(self):
        entry = HistoryEntry(scene_id="1", next_scene_id="2")
        assert entry.scene_id == "1"
        assert entry.next_scene_id == "2"

    def test_optional_fields_default_none(self):
        entry = HistoryEntry(scene_id="1", next_scene_id="2")
        assert entry.choice_index is None
        assert entry.choice_text is None
        assert entry.variables_snapshot is None

    def test_all_fields_stored(self):
        snap = {"confidence": 1.0}
        entry = HistoryEntry(
            scene_id="1",
            next_scene_id="2",
            choice_index=0,
            choice_text="Go left",
            variables_snapshot=snap,
        )
        assert entry.choice_index == 0
        assert entry.choice_text == "Go left"
        assert entry.variables_snapshot == {"confidence": 1.0}

    # Immutability -----------------------------------------------------------

    def test_scene_id_immutable(self):
        entry = HistoryEntry(scene_id="1", next_scene_id="2")
        with pytest.raises(AttributeError):
            entry.scene_id = "changed"  # type: ignore[misc]

    def test_next_scene_id_immutable(self):
        entry = HistoryEntry(scene_id="1", next_scene_id="2")
        with pytest.raises(AttributeError):
            entry.next_scene_id = "changed"  # type: ignore[misc]

    def test_choice_index_immutable(self):
        entry = HistoryEntry(scene_id="1", next_scene_id="2", choice_index=0)
        with pytest.raises(AttributeError):
            entry.choice_index = 1  # type: ignore[misc]

    # to_dict ----------------------------------------------------------------

    def test_to_dict_minimal(self):
        d = HistoryEntry(scene_id="1", next_scene_id="2").to_dict()
        assert d == {"scene_id": "1", "next_scene_id": "2"}

    def test_to_dict_omits_none_choice_index(self):
        d = HistoryEntry(scene_id="1", next_scene_id="2").to_dict()
        assert "choice_index" not in d

    def test_to_dict_omits_none_choice_text(self):
        d = HistoryEntry(scene_id="1", next_scene_id="2").to_dict()
        assert "choice_text" not in d

    def test_to_dict_includes_choice_fields_when_set(self):
        d = HistoryEntry(
            scene_id="1", next_scene_id="2", choice_index=1, choice_text="Option B"
        ).to_dict()
        assert d["choice_index"] == 1
        assert d["choice_text"] == "Option B"

    def test_to_dict_omits_variables_snapshot(self):
        """Snapshot is a diagnostic aid and is never serialised."""
        d = HistoryEntry(
            scene_id="1",
            next_scene_id="2",
            variables_snapshot={"x": 1.0},
        ).to_dict()
        assert "variables_snapshot" not in d

    def test_equality(self):
        a = HistoryEntry(scene_id="1", next_scene_id="2", choice_index=0)
        b = HistoryEntry(scene_id="1", next_scene_id="2", choice_index=0)
        assert a == b

    def test_inequality_different_choice(self):
        a = HistoryEntry(scene_id="1", next_scene_id="2", choice_index=0)
        b = HistoryEntry(scene_id="1", next_scene_id="2", choice_index=1)
        assert a != b


# ---------------------------------------------------------------------------
# EngineState — initialisation
# ---------------------------------------------------------------------------


class TestEngineStateInit:
    def test_current_scene_id(self):
        assert EngineState(current_scene_id="intro").current_scene_id == "intro"

    def test_variables_default_empty(self):
        assert EngineState(current_scene_id="1").variables == {}

    def test_history_default_empty(self):
        assert EngineState(current_scene_id="1").history == []

    def test_variables_provided(self):
        state = EngineState(current_scene_id="1", variables={"confidence": 2.0})
        assert state.variables["confidence"] == 2.0

    def test_history_provided(self):
        entries = [HistoryEntry(scene_id="1", next_scene_id="2")]
        state = EngineState(current_scene_id="2", history=entries)
        assert len(state.history) == 1

    def test_two_states_independent_variables(self):
        """Default factory ensures each instance gets its own dict."""
        a = EngineState(current_scene_id="1")
        b = EngineState(current_scene_id="1")
        a.variables["x"] = 1.0
        assert "x" not in b.variables

    def test_two_states_independent_history(self):
        a = EngineState(current_scene_id="1")
        b = EngineState(current_scene_id="1")
        a.history.append(HistoryEntry(scene_id="1", next_scene_id="2"))
        assert len(b.history) == 0


# ---------------------------------------------------------------------------
# apply_effects
# ---------------------------------------------------------------------------


class TestApplyEffects:
    def test_adds_to_existing_variable(self):
        state = EngineState(current_scene_id="1", variables={"confidence": 0.0})
        state.apply_effects({"confidence": 1.0})
        assert state.variables["confidence"] == 1.0

    def test_initialises_missing_variable_at_zero(self):
        state = EngineState(current_scene_id="1")
        state.apply_effects({"risk": 1.0})
        assert state.variables["risk"] == 1.0

    def test_negative_delta(self):
        state = EngineState(current_scene_id="1", variables={"risk": 3.0})
        state.apply_effects({"risk": -2.0})
        assert state.variables["risk"] == 1.0

    def test_delta_drives_below_zero(self):
        state = EngineState(current_scene_id="1", variables={"score": 0.0})
        state.apply_effects({"score": -1.0})
        assert state.variables["score"] == -1.0

    def test_multiple_keys_in_one_call(self):
        state = EngineState(
            current_scene_id="1", variables={"confidence": 0.0, "risk": 0.0}
        )
        state.apply_effects({"confidence": 1.0, "risk": -1.0})
        assert state.variables["confidence"] == 1.0
        assert state.variables["risk"] == -1.0

    def test_cumulative_across_calls(self):
        state = EngineState(current_scene_id="1", variables={"score": 0.0})
        state.apply_effects({"score": 1.0})
        state.apply_effects({"score": 1.0})
        state.apply_effects({"score": 1.0})
        assert state.variables["score"] == 3.0

    def test_empty_effects_no_change(self):
        state = EngineState(current_scene_id="1", variables={"confidence": 5.0})
        state.apply_effects({})
        assert state.variables["confidence"] == 5.0

    def test_other_variables_untouched(self):
        state = EngineState(
            current_scene_id="1", variables={"confidence": 1.0, "risk": 0.0}
        )
        state.apply_effects({"confidence": 1.0})
        assert state.variables["risk"] == 0.0

    def test_integer_delta_accepted(self):
        """Effects from JSON may carry int values; they should be treated as float."""
        state = EngineState(current_scene_id="1", variables={"x": 0.0})
        state.apply_effects({"x": 1})  # type: ignore[arg-type]
        assert state.variables["x"] == 1.0


# ---------------------------------------------------------------------------
# Serialisation — to_dict
# ---------------------------------------------------------------------------


class TestToDict:
    def test_basic_shape(self):
        state = EngineState(current_scene_id="2", variables={"confidence": 1.0})
        d = state.to_dict()
        assert d["current_scene_id"] == "2"
        assert d["variables"] == {"confidence": 1.0}
        assert d["history"] == []

    def test_history_serialised(self):
        state = EngineState(
            current_scene_id="2",
            history=[HistoryEntry(scene_id="1", next_scene_id="2", choice_index=0)],
        )
        d = state.to_dict()
        assert len(d["history"]) == 1
        assert d["history"][0]["scene_id"] == "1"
        assert d["history"][0]["choice_index"] == 0

    def test_variables_is_copy(self):
        """Mutating the returned dict must not affect the state object."""
        state = EngineState(current_scene_id="1", variables={"x": 1.0})
        d = state.to_dict()
        d["variables"]["x"] = 999.0
        assert state.variables["x"] == 1.0

    def test_multiple_history_entries_ordered(self):
        state = EngineState(
            current_scene_id="3",
            history=[
                HistoryEntry(scene_id="1", next_scene_id="2"),
                HistoryEntry(scene_id="2", next_scene_id="3"),
            ],
        )
        d = state.to_dict()
        assert d["history"][0]["scene_id"] == "1"
        assert d["history"][1]["scene_id"] == "2"


# ---------------------------------------------------------------------------
# Serialisation — from_dict
# ---------------------------------------------------------------------------


class TestFromDict:
    def test_basic(self):
        state = EngineState.from_dict(
            {"current_scene_id": "2", "variables": {"confidence": 1.0}, "history": []}
        )
        assert state.current_scene_id == "2"
        assert state.variables["confidence"] == 1.0
        assert state.history == []

    def test_missing_variables_defaults_empty(self):
        state = EngineState.from_dict({"current_scene_id": "1"})
        assert state.variables == {}

    def test_missing_history_defaults_empty(self):
        state = EngineState.from_dict({"current_scene_id": "1"})
        assert state.history == []

    def test_history_reconstructed(self):
        state = EngineState.from_dict(
            {
                "current_scene_id": "3",
                "variables": {},
                "history": [
                    {
                        "scene_id": "1",
                        "next_scene_id": "2",
                        "choice_index": 0,
                        "choice_text": "Go left",
                    },
                    {"scene_id": "2", "next_scene_id": "3"},
                ],
            }
        )
        assert len(state.history) == 2
        assert state.history[0].scene_id == "1"
        assert state.history[0].choice_index == 0
        assert state.history[0].choice_text == "Go left"
        assert state.history[1].choice_index is None

    def test_history_entries_are_frozen(self):
        state = EngineState.from_dict(
            {
                "current_scene_id": "2",
                "history": [{"scene_id": "1", "next_scene_id": "2"}],
            }
        )
        with pytest.raises(AttributeError):
            state.history[0].scene_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Serialisation — round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_empty_state(self):
        original = EngineState(current_scene_id="1")
        restored = EngineState.from_dict(original.to_dict())
        assert restored.current_scene_id == "1"
        assert restored.variables == {}
        assert restored.history == []

    def test_state_with_variables(self):
        original = EngineState(
            current_scene_id="3a",
            variables={"confidence": 2.0, "risk": -1.0},
        )
        restored = EngineState.from_dict(original.to_dict())
        assert restored.variables == {"confidence": 2.0, "risk": -1.0}

    def test_state_with_history(self):
        original = EngineState(
            current_scene_id="3",
            history=[
                HistoryEntry(
                    scene_id="1", next_scene_id="2", choice_index=0, choice_text="Left"
                ),
                HistoryEntry(scene_id="2", next_scene_id="3"),
            ],
        )
        restored = EngineState.from_dict(original.to_dict())
        assert len(restored.history) == 2
        assert restored.history[0].scene_id == "1"
        assert restored.history[0].choice_index == 0
        assert restored.history[0].choice_text == "Left"
        assert restored.history[1].choice_index is None

    def test_after_apply_effects(self):
        state = EngineState(current_scene_id="1", variables={"confidence": 0.0})
        state.apply_effects({"confidence": 3.0})
        restored = EngineState.from_dict(state.to_dict())
        assert restored.variables["confidence"] == 3.0

    def test_snapshot_not_preserved_across_roundtrip(self):
        """variables_snapshot is diagnostic only and is not serialised."""
        original = EngineState(
            current_scene_id="2",
            history=[
                HistoryEntry(
                    scene_id="1",
                    next_scene_id="2",
                    variables_snapshot={"x": 99.0},
                )
            ],
        )
        restored = EngineState.from_dict(original.to_dict())
        assert restored.history[0].variables_snapshot is None
