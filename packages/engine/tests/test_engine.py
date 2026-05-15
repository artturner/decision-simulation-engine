"""
ScenarioEngine integration tests.

Covers full play walkthroughs, all scene types, rewind, validation errors,
and edge cases the executor-level tests cannot reach.
"""

import pytest

from engine.engine import ScenarioEngine
from engine.state import EngineState


# ---------------------------------------------------------------------------
# Shared scenario fixtures
# ---------------------------------------------------------------------------

# Minimal 2-scene scenario: choice → end
SIMPLE: dict = {
    "metadata": {"title": "Simple"},
    "variables": {"confidence": 0},
    "start_scene_id": "1",
    "scenes": {
        "1": {
            "type": "choice",
            "title": "Opening",
            "choices": [
                {"text": "Brave", "next": "end", "effects": {"confidence": 1}},
                {"text": "Cautious", "next": "end"},
            ],
        },
        "end": {
            "type": "end",
            "title": "Done",
            "outcome": "success",
            "outcome_message": "You finished!",
        },
    },
}

# Full scenario exercising every scene type:
# choice → auto_advance → conditional → end (two outcomes)
FULL: dict = {
    "metadata": {"title": "Full", "completion_tracking": True},
    "variables": {"confidence": 0, "risk": 0},
    "start_scene_id": "start",
    "scenes": {
        "start": {
            "type": "choice",
            "title": "Choose",
            "choices": [
                {"text": "Bold", "next": "mid", "effects": {"confidence": 2}},
                {"text": "Safe", "next": "mid", "effects": {"risk": 1}},
            ],
        },
        "mid": {
            "type": "auto_advance",
            "title": "Transition",
            "next": "branch",
        },
        "branch": {
            "type": "conditional",
            "title": "Branch",
            "conditions": [
                {"condition": "confidence >= 2", "next": "good_end"},
            ],
            "default": "bad_end",
        },
        "good_end": {
            "type": "end",
            "outcome": "success",
            "outcome_message": "You succeeded!",
        },
        "bad_end": {
            "type": "end",
            "outcome": "failure",
            "outcome_message": "Better luck next time.",
        },
    },
}

# Linear 3-scene scenario for rewind tests: choice → choice → end
REWIND: dict = {
    "metadata": {"title": "Rewind"},
    "variables": {"score": 0},
    "start_scene_id": "s1",
    "scenes": {
        "s1": {
            "type": "choice",
            "choices": [{"text": "A", "next": "s2", "effects": {"score": 1}}],
        },
        "s2": {
            "type": "choice",
            "choices": [{"text": "B", "next": "s3", "effects": {"score": 1}}],
        },
        "s3": {
            "type": "end",
            "outcome": "done",
            "outcome_message": "All done.",
        },
    },
}


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_valid_scenario_constructs(self):
        engine = ScenarioEngine(SIMPLE)
        assert engine.scenario.metadata.title == "Simple"

    def test_invalid_scenario_raises_value_error(self):
        bad = {
            "metadata": {"title": "X"},
            "scenes": {
                "1": {
                    "type": "choice",
                    "choices": [{"text": "Go", "next": "missing"}],
                },
            },
        }
        with pytest.raises(ValueError, match="Invalid scenario"):
            ScenarioEngine(bad)

    def test_error_message_lists_problems(self):
        bad = {
            "metadata": {"title": "X"},
            "scenes": {
                "1": {
                    "type": "choice",
                    "choices": [{"text": "A", "next": "gone_a"},
                                {"text": "B", "next": "gone_b"}],
                },
            },
        }
        with pytest.raises(ValueError) as exc_info:
            ScenarioEngine(bad)
        msg = str(exc_info.value)
        assert "gone_a" in msg or "gone_b" in msg


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    def test_returns_initial_state(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        assert state.current_scene_id == "1"

    def test_variables_copied_from_scenario(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        assert state.variables == {"confidence": 0.0}

    def test_history_empty_at_start(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        assert state.history == []

    def test_scene_dto_has_scene_id(self):
        engine = ScenarioEngine(SIMPLE)
        _, dto = engine.start()
        assert dto["scene_id"] == "1"

    def test_scene_dto_has_type(self):
        engine = ScenarioEngine(SIMPLE)
        _, dto = engine.start()
        assert dto["type"] == "choice"

    def test_scene_dto_has_title(self):
        engine = ScenarioEngine(SIMPLE)
        _, dto = engine.start()
        assert dto["title"] == "Opening"

    def test_two_starts_are_independent(self):
        engine = ScenarioEngine(SIMPLE)
        state_a, _ = engine.start()
        state_b, _ = engine.start()
        state_a.variables["confidence"] = 99.0
        assert state_b.variables["confidence"] == 0.0


# ---------------------------------------------------------------------------
# step() — ChoiceScene
# ---------------------------------------------------------------------------


class TestStepChoice:
    def setup_method(self):
        self.engine = ScenarioEngine(SIMPLE)
        self.state, _ = self.engine.start()

    def test_transitions_to_next_scene(self):
        new_state, _, _, _ = self.engine.step(self.state, choice_index=0)
        assert new_state.current_scene_id == "end"

    def test_applies_effects(self):
        new_state, _, _, _ = self.engine.step(self.state, choice_index=0)
        assert new_state.variables["confidence"] == 1.0

    def test_no_effects_on_second_choice(self):
        new_state, _, _, _ = self.engine.step(self.state, choice_index=1)
        assert new_state.variables["confidence"] == 0.0

    def test_done_is_false_after_choice(self):
        _, _, done, _ = self.engine.step(self.state, choice_index=0)
        assert done is False

    def test_outcome_info_none_after_choice(self):
        _, _, _, outcome_info = self.engine.step(self.state, choice_index=0)
        assert outcome_info is None

    def test_scene_dto_is_next_scene(self):
        _, dto, _, _ = self.engine.step(self.state, choice_index=0)
        assert dto["scene_id"] == "end"
        assert dto["type"] == "end"

    def test_missing_choice_index_raises(self):
        with pytest.raises(ValueError, match="choice_index"):
            self.engine.step(self.state)

    def test_history_appended(self):
        new_state, _, _, _ = self.engine.step(self.state, choice_index=0)
        assert len(new_state.history) == 1
        assert new_state.history[0].scene_id == "1"
        assert new_state.history[0].choice_index == 0


# ---------------------------------------------------------------------------
# step() — EndScene
# ---------------------------------------------------------------------------


class TestStepEnd:
    def setup_method(self):
        self.engine = ScenarioEngine(SIMPLE)
        state0, _ = self.engine.start()
        self.state_at_end, _, _, _ = self.engine.step(state0, choice_index=0)

    def test_done_is_true(self):
        _, _, done, _ = self.engine.step(self.state_at_end)
        assert done is True

    def test_outcome_info_populated(self):
        _, _, _, outcome_info = self.engine.step(self.state_at_end)
        assert outcome_info is not None
        assert outcome_info["outcome"] == "success"
        assert outcome_info["outcome_message"] == "You finished!"

    def test_scene_dto_is_end_scene(self):
        _, dto, _, _ = self.engine.step(self.state_at_end)
        assert dto["type"] == "end"

    def test_current_scene_unchanged_on_end(self):
        new_state, _, _, _ = self.engine.step(self.state_at_end)
        assert new_state.current_scene_id == "end"


# ---------------------------------------------------------------------------
# step() — AutoAdvanceScene
# ---------------------------------------------------------------------------


class TestStepAutoAdvance:
    def setup_method(self):
        self.engine = ScenarioEngine(FULL)
        state0, _ = self.engine.start()
        # Advance past choice to land on auto_advance scene
        self.state_at_mid, _, _, _ = self.engine.step(state0, choice_index=0)
        assert self.state_at_mid.current_scene_id == "mid"

    def test_transitions_without_choice_index(self):
        new_state, _, _, _ = self.engine.step(self.state_at_mid)
        assert new_state.current_scene_id == "branch"

    def test_done_is_false(self):
        _, _, done, _ = self.engine.step(self.state_at_mid)
        assert done is False

    def test_scene_dto_is_next(self):
        _, dto, _, _ = self.engine.step(self.state_at_mid)
        assert dto["type"] == "conditional"


# ---------------------------------------------------------------------------
# step() — ConditionalScene
# ---------------------------------------------------------------------------


class TestStepConditional:
    def setup_method(self):
        self.engine = ScenarioEngine(FULL)

    def _reach_branch(self, choice: int) -> EngineState:
        state, _ = self.engine.start()
        state, _, _, _ = self.engine.step(state, choice_index=choice)  # choice → mid
        state, _, _, _ = self.engine.step(state)                        # mid → branch
        return state

    def test_condition_true_takes_matching_branch(self):
        """Bold choice sets confidence=2, condition 'confidence >= 2' is True."""
        state = self._reach_branch(choice=0)
        new_state, _, _, _ = self.engine.step(state)
        assert new_state.current_scene_id == "good_end"

    def test_condition_false_takes_default(self):
        """Safe choice sets risk=1 (not confidence), condition False → default."""
        state = self._reach_branch(choice=1)
        new_state, _, _, _ = self.engine.step(state)
        assert new_state.current_scene_id == "bad_end"

    def test_done_is_false_after_conditional(self):
        state = self._reach_branch(choice=0)
        _, _, done, _ = self.engine.step(state)
        assert done is False


# ---------------------------------------------------------------------------
# Full walkthrough: start → choice → auto → conditional → end
# ---------------------------------------------------------------------------


class TestFullWalkthrough:
    def test_bold_path_leads_to_success(self):
        engine = ScenarioEngine(FULL)

        state, dto = engine.start()
        assert dto["type"] == "choice"

        # Choice 0: "Bold" → confidence +2
        state, dto, done, _ = engine.step(state, choice_index=0)
        assert dto["type"] == "auto_advance"
        assert state.variables["confidence"] == 2.0
        assert done is False

        # Auto-advance → branch
        state, dto, done, _ = engine.step(state)
        assert dto["type"] == "conditional"
        assert done is False

        # Conditional: confidence >= 2 → good_end
        state, dto, done, _ = engine.step(state)
        assert dto["type"] == "end"
        assert state.current_scene_id == "good_end"
        assert done is False

        # Execute end scene
        state, dto, done, outcome_info = engine.step(state)
        assert done is True
        assert outcome_info["outcome"] == "success"

    def test_safe_path_leads_to_failure(self):
        engine = ScenarioEngine(FULL)
        state, _ = engine.start()

        state, _, _, _ = engine.step(state, choice_index=1)  # "Safe" → risk +1
        state, _, _, _ = engine.step(state)                   # auto_advance
        state, _, _, _ = engine.step(state)                   # conditional (default)
        assert state.current_scene_id == "bad_end"

        _, _, done, outcome_info = engine.step(state)
        assert done is True
        assert outcome_info["outcome"] == "failure"

    def test_state_history_length_matches_steps(self):
        engine = ScenarioEngine(FULL)
        state, _ = engine.start()
        state, _, _, _ = engine.step(state, choice_index=0)   # step 1
        state, _, _, _ = engine.step(state)                    # step 2
        state, _, _, _ = engine.step(state)                    # step 3
        # 3 transitions logged (end scene not yet executed)
        assert len(state.history) == 3

    def test_variable_effects_accumulate(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        new_state, _, _, _ = engine.step(state, choice_index=0)
        assert new_state.variables["confidence"] == 1.0


# ---------------------------------------------------------------------------
# rewind()
# ---------------------------------------------------------------------------


class TestRewind:
    def setup_method(self):
        self.engine = ScenarioEngine(REWIND)

    def _play_two_steps(self) -> EngineState:
        state, _ = self.engine.start()
        state, _, _, _ = self.engine.step(state, choice_index=0)  # s1 → s2
        state, _, _, _ = self.engine.step(state, choice_index=0)  # s2 → s3
        return state

    def test_rewind_one_step_returns_to_previous_scene(self):
        state_at_s3 = self._play_two_steps()
        # Pass history without the last entry (simulate API truncation)
        truncated_events = state_at_s3.to_dict()["history"][:-1]
        state_back, _ = self.engine.rewind(state_at_s3, truncated_events)
        assert state_back.current_scene_id == "s2"

    def test_rewind_restores_variable_state(self):
        """After one choice (score +1), rewind should restore score to 1, not 2."""
        state_at_s3 = self._play_two_steps()
        assert state_at_s3.variables["score"] == 2.0

        truncated_events = state_at_s3.to_dict()["history"][:-1]
        state_back, _ = self.engine.rewind(state_at_s3, truncated_events)
        assert state_back.variables["score"] == 1.0

    def test_rewind_restores_history_length(self):
        state_at_s3 = self._play_two_steps()
        truncated_events = state_at_s3.to_dict()["history"][:-1]
        state_back, _ = self.engine.rewind(state_at_s3, truncated_events)
        assert len(state_back.history) == 1

    def test_rewind_to_start_with_empty_events(self):
        state_at_s3 = self._play_two_steps()
        state_back, dto = self.engine.rewind(state_at_s3, [])
        assert state_back.current_scene_id == "s1"
        assert state_back.variables["score"] == 0.0
        assert state_back.history == []

    def test_rewind_scene_dto_correct(self):
        state_at_s3 = self._play_two_steps()
        truncated_events = state_at_s3.to_dict()["history"][:-1]
        _, dto = self.engine.rewind(state_at_s3, truncated_events)
        assert dto["scene_id"] == "s2"
        assert dto["type"] == "choice"

    def test_rewind_two_steps_returns_to_start(self):
        state_at_s3 = self._play_two_steps()
        state_back, _ = self.engine.rewind(state_at_s3, [])
        assert state_back.current_scene_id == "s1"

    def test_rewind_is_deterministic(self):
        """Rewinding twice with the same events yields the same result."""
        state_at_s3 = self._play_two_steps()
        events = state_at_s3.to_dict()["history"][:-1]
        state_a, _ = self.engine.rewind(state_at_s3, events)
        state_b, _ = self.engine.rewind(state_at_s3, events)
        assert state_a.current_scene_id == state_b.current_scene_id
        assert state_a.variables == state_b.variables

    def test_rewind_does_not_mutate_original_state(self):
        state_at_s3 = self._play_two_steps()
        original_scene = state_at_s3.current_scene_id
        events = state_at_s3.to_dict()["history"][:-1]
        self.engine.rewind(state_at_s3, events)
        assert state_at_s3.current_scene_id == original_scene

    def test_rewind_skips_unknown_scene_ids(self):
        """Malformed events with bad scene_ids are silently skipped."""
        state_at_s3 = self._play_two_steps()
        bad_events = [{"scene_id": "nonexistent", "next_scene_id": "s2", "choice_index": 0}]
        state_back, _ = self.engine.rewind(state_at_s3, bad_events)
        # Falls back to initial state (nothing replayed)
        assert state_back.current_scene_id == "s1"


# ---------------------------------------------------------------------------
# step() edge cases
# ---------------------------------------------------------------------------


class TestStepEdgeCases:
    def test_unknown_scene_id_raises(self):
        engine = ScenarioEngine(SIMPLE)
        bad_state = EngineState(current_scene_id="does_not_exist")
        with pytest.raises(ValueError, match="not found"):
            engine.step(bad_state)

    def test_choice_index_out_of_range_raises(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        with pytest.raises(ValueError):
            engine.step(state, choice_index=99)

    def test_scene_dto_includes_scene_id_key(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        new_state, dto, _, _ = engine.step(state, choice_index=0)
        assert "scene_id" in dto

    def test_step_does_not_mutate_input_state(self):
        engine = ScenarioEngine(SIMPLE)
        state, _ = engine.start()
        original_scene = state.current_scene_id
        engine.step(state, choice_index=0)
        assert state.current_scene_id == original_scene
