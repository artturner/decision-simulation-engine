"""
Executor tests — state transitions, effect application, history recording,
conditional evaluation order, and input-state isolation.
"""

import pytest

from engine.executors import (
    ExecutorResult,
    execute_auto_advance,
    execute_choice,
    execute_conditional,
    execute_end,
)
from engine.models import (
    AutoAdvanceScene,
    Choice,
    ChoiceScene,
    Condition,
    ConditionalScene,
    EndScene,
)
from engine.state import EngineState, HistoryEntry


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def make_choice_scene(choices: list[dict] | None = None) -> ChoiceScene:
    if choices is None:
        choices = [
            {"text": "Option A", "next": "2", "effects": {"confidence": 1.0}},
            {"text": "Option B", "next": "3", "effects": {"risk": 1.0}},
        ]
    return ChoiceScene(
        type="choice",
        choices=[Choice(**c) for c in choices],
    )


def make_auto_scene(next_id: str = "2") -> AutoAdvanceScene:
    return AutoAdvanceScene(type="auto_advance", next=next_id)


def make_conditional_scene(
    conditions: list[dict],
    default: str | None = None,
) -> ConditionalScene:
    return ConditionalScene(
        type="conditional",
        conditions=[Condition(**c) for c in conditions],
        default=default,
    )


def make_end_scene(
    outcome: str | None = "success",
    outcome_message: str | None = "You finished.",
) -> EndScene:
    return EndScene(type="end", outcome=outcome, outcome_message=outcome_message)


def base_state(scene_id: str = "1", variables: dict | None = None) -> EngineState:
    return EngineState(
        current_scene_id=scene_id,
        variables=dict(variables or {}),
    )


# Evaluate functions for conditional tests
_always_true: list[int] = []  # simple call counter hack avoided — use lambdas directly


def always_true(expr: str, variables: dict) -> bool:
    return True


def always_false(expr: str, variables: dict) -> bool:
    return False


def first_only(expr: str, variables: dict) -> bool:
    """Returns True only for expressions starting with 'FIRST'."""
    return expr.startswith("FIRST")


# ---------------------------------------------------------------------------
# ExecutorResult structure
# ---------------------------------------------------------------------------


class TestExecutorResult:
    def test_is_named_tuple(self):
        state = base_state()
        result = ExecutorResult(state=state, done=False)
        assert isinstance(result, tuple)

    def test_defaults(self):
        result = ExecutorResult(state=base_state(), done=False)
        assert result.outcome is None
        assert result.outcome_message is None

    def test_unpacking(self):
        state = base_state()
        result = ExecutorResult(state=state, done=True, outcome="win")
        s, done, outcome, msg = result
        assert s is state
        assert done is True
        assert outcome == "win"
        assert msg is None


# ---------------------------------------------------------------------------
# execute_choice
# ---------------------------------------------------------------------------


class TestExecuteChoice:
    def test_transitions_to_correct_scene(self):
        scene = make_choice_scene()
        result = execute_choice(scene, base_state("1"), choice_index=0)
        assert result.state.current_scene_id == "2"

    def test_transitions_to_second_choice(self):
        scene = make_choice_scene()
        result = execute_choice(scene, base_state("1"), choice_index=1)
        assert result.state.current_scene_id == "3"

    def test_done_is_false(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 0)
        assert result.done is False

    def test_outcome_is_none(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 0)
        assert result.outcome is None

    # Effects ----------------------------------------------------------------

    def test_applies_choice_effects(self):
        scene = make_choice_scene()
        state = base_state("1", {"confidence": 0.0})
        result = execute_choice(scene, state, choice_index=0)
        assert result.state.variables["confidence"] == 1.0

    def test_applies_second_choice_effects(self):
        scene = make_choice_scene()
        state = base_state("1", {"risk": 0.0})
        result = execute_choice(scene, state, choice_index=1)
        assert result.state.variables["risk"] == 1.0

    def test_effects_initialise_missing_variable(self):
        scene = make_choice_scene()
        result = execute_choice(scene, base_state("1"), choice_index=0)
        assert result.state.variables.get("confidence") == 1.0

    def test_no_effects_variables_unchanged(self):
        scene = make_choice_scene(
            [{"text": "Neutral", "next": "2"}]  # no effects key
        )
        state = base_state("1", {"confidence": 5.0})
        result = execute_choice(scene, state, 0)
        assert result.state.variables["confidence"] == 5.0

    # History ----------------------------------------------------------------

    def test_appends_one_history_entry(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 0)
        assert len(result.state.history) == 1

    def test_history_entry_scene_id(self):
        result = execute_choice(make_choice_scene(), base_state("scene_a"), 0)
        assert result.state.history[0].scene_id == "scene_a"

    def test_history_entry_next_scene_id(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 0)
        assert result.state.history[0].next_scene_id == "2"

    def test_history_entry_choice_index(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 1)
        assert result.state.history[0].choice_index == 1

    def test_history_entry_choice_text(self):
        result = execute_choice(make_choice_scene(), base_state("1"), 0)
        assert result.state.history[0].choice_text == "Option A"

    def test_history_entry_variables_snapshot_post_effects(self):
        """Snapshot records variables *after* effects are applied."""
        scene = make_choice_scene()
        state = base_state("1", {"confidence": 0.0})
        result = execute_choice(scene, state, 0)
        snap = result.state.history[0].variables_snapshot
        assert snap is not None
        assert snap["confidence"] == 1.0

    def test_history_accumulates(self):
        """Existing history is preserved and new entry appended."""
        prior = HistoryEntry(scene_id="0", next_scene_id="1")
        state = EngineState(current_scene_id="1", history=[prior])
        result = execute_choice(make_choice_scene(), state, 0)
        assert len(result.state.history) == 2
        assert result.state.history[0].scene_id == "0"

    # State isolation --------------------------------------------------------

    def test_does_not_mutate_input_variables(self):
        state = base_state("1", {"confidence": 0.0})
        execute_choice(make_choice_scene(), state, 0)
        assert state.variables["confidence"] == 0.0

    def test_does_not_mutate_input_current_scene_id(self):
        state = base_state("1")
        execute_choice(make_choice_scene(), state, 0)
        assert state.current_scene_id == "1"

    def test_does_not_mutate_input_history(self):
        state = base_state("1")
        execute_choice(make_choice_scene(), state, 0)
        assert len(state.history) == 0

    # Validation -------------------------------------------------------------

    def test_negative_index_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            execute_choice(make_choice_scene(), base_state("1"), -1)

    def test_index_too_large_raises(self):
        scene = make_choice_scene([{"text": "Only", "next": "2"}])
        with pytest.raises(ValueError, match="out of range"):
            execute_choice(scene, base_state("1"), 1)


# ---------------------------------------------------------------------------
# execute_auto_advance
# ---------------------------------------------------------------------------


class TestExecuteAutoAdvance:
    def test_transitions_to_next(self):
        result = execute_auto_advance(make_auto_scene("end"), base_state("mid"))
        assert result.state.current_scene_id == "end"

    def test_done_is_false(self):
        result = execute_auto_advance(make_auto_scene(), base_state("1"))
        assert result.done is False

    def test_outcome_is_none(self):
        result = execute_auto_advance(make_auto_scene(), base_state("1"))
        assert result.outcome is None

    def test_appends_history_entry(self):
        result = execute_auto_advance(make_auto_scene("2"), base_state("1"))
        assert len(result.state.history) == 1
        entry = result.state.history[0]
        assert entry.scene_id == "1"
        assert entry.next_scene_id == "2"

    def test_history_entry_has_no_choice_fields(self):
        result = execute_auto_advance(make_auto_scene(), base_state("1"))
        entry = result.state.history[0]
        assert entry.choice_index is None
        assert entry.choice_text is None

    def test_variables_unchanged(self):
        state = base_state("1", {"confidence": 3.0})
        result = execute_auto_advance(make_auto_scene(), state)
        assert result.state.variables["confidence"] == 3.0

    def test_does_not_mutate_input_state(self):
        state = base_state("1")
        execute_auto_advance(make_auto_scene(), state)
        assert state.current_scene_id == "1"
        assert len(state.history) == 0


# ---------------------------------------------------------------------------
# execute_conditional
# ---------------------------------------------------------------------------


class TestExecuteConditional:
    def test_first_true_condition_wins(self):
        scene = make_conditional_scene(
            [
                {"condition": "FIRST", "next": "a"},
                {"condition": "second", "next": "b"},
            ]
        )
        result = execute_conditional(scene, base_state("1"), evaluate_fn=first_only)
        assert result.state.current_scene_id == "a"

    def test_second_condition_when_first_false(self):
        scene = make_conditional_scene(
            [
                {"condition": "first", "next": "a"},   # first_only returns False
                {"condition": "FIRST_second", "next": "b"},
            ]
        )
        result = execute_conditional(scene, base_state("1"), evaluate_fn=first_only)
        assert result.state.current_scene_id == "b"

    def test_default_when_no_match(self):
        scene = make_conditional_scene(
            [{"condition": "never_true", "next": "a"}],
            default="fallback",
        )
        result = execute_conditional(scene, base_state("1"), evaluate_fn=always_false)
        assert result.state.current_scene_id == "fallback"

    def test_no_match_no_default_raises(self):
        scene = make_conditional_scene(
            [{"condition": "never_true", "next": "a"}],
            default=None,
        )
        with pytest.raises(ValueError, match="no condition matched"):
            execute_conditional(scene, base_state("1"), evaluate_fn=always_false)

    def test_done_is_false(self):
        scene = make_conditional_scene([{"condition": "x", "next": "end"}])
        result = execute_conditional(scene, base_state("1"), evaluate_fn=always_true)
        assert result.done is False

    def test_appends_history_entry(self):
        scene = make_conditional_scene([{"condition": "x", "next": "next_scene"}])
        result = execute_conditional(scene, base_state("1"), evaluate_fn=always_true)
        assert len(result.state.history) == 1
        assert result.state.history[0].scene_id == "1"
        assert result.state.history[0].next_scene_id == "next_scene"

    def test_history_entry_has_no_choice_fields(self):
        scene = make_conditional_scene([{"condition": "x", "next": "2"}])
        result = execute_conditional(scene, base_state("1"), evaluate_fn=always_true)
        entry = result.state.history[0]
        assert entry.choice_index is None
        assert entry.choice_text is None

    def test_variables_passed_to_evaluate_fn(self):
        """evaluate_fn receives current variables dict."""
        captured: list[dict] = []

        def capturing_fn(expr: str, variables: dict) -> bool:
            captured.append(dict(variables))
            return True

        scene = make_conditional_scene([{"condition": "x > 0", "next": "2"}])
        state = base_state("1", {"confidence": 3.0})
        execute_conditional(scene, state, evaluate_fn=capturing_fn)
        assert captured[0] == {"confidence": 3.0}

    def test_uses_safe_evaluate_by_default(self):
        """Default evaluate_fn resolves real expressions against variables."""
        scene = make_conditional_scene(
            [
                {"condition": "confidence > 0", "next": "high"},
                {"condition": "confidence <= 0", "next": "low"},
            ]
        )
        state = base_state("1", {"confidence": 1.0})
        result = execute_conditional(scene, state)  # no evaluate_fn passed
        assert result.state.current_scene_id == "high"

    def test_evaluation_order_matters(self):
        """First matching condition is chosen even if later ones also match."""
        call_order: list[str] = []

        def track(expr: str, variables: dict) -> bool:
            call_order.append(expr)
            return True  # all match

        scene = make_conditional_scene(
            [
                {"condition": "alpha", "next": "a"},
                {"condition": "beta", "next": "b"},
            ]
        )
        result = execute_conditional(scene, base_state("1"), evaluate_fn=track)
        # Only the first condition should be evaluated (short-circuit once matched)
        assert call_order[0] == "alpha"
        assert result.state.current_scene_id == "a"

    def test_does_not_mutate_input_state(self):
        scene = make_conditional_scene([{"condition": "x", "next": "2"}])
        state = base_state("1")
        execute_conditional(scene, state, evaluate_fn=always_true)
        assert state.current_scene_id == "1"
        assert len(state.history) == 0


# ---------------------------------------------------------------------------
# execute_end
# ---------------------------------------------------------------------------


class TestExecuteEnd:
    def test_done_is_true(self):
        result = execute_end(make_end_scene(), base_state("end"))
        assert result.done is True

    def test_outcome_returned(self):
        result = execute_end(make_end_scene(outcome="success"), base_state("end"))
        assert result.outcome == "success"

    def test_outcome_message_returned(self):
        result = execute_end(
            make_end_scene(outcome_message="Well done!"), base_state("end")
        )
        assert result.outcome_message == "Well done!"

    def test_none_outcome(self):
        result = execute_end(make_end_scene(outcome=None, outcome_message=None), base_state("end"))
        assert result.outcome is None
        assert result.outcome_message is None

    def test_current_scene_id_unchanged(self):
        """End scene doesn't transition — scene_id stays at end scene."""
        result = execute_end(make_end_scene(), base_state("final"))
        assert result.state.current_scene_id == "final"

    def test_no_history_entry_appended(self):
        result = execute_end(make_end_scene(), base_state("end"))
        assert len(result.state.history) == 0

    def test_existing_history_preserved(self):
        prior = HistoryEntry(scene_id="1", next_scene_id="end")
        state = EngineState(current_scene_id="end", history=[prior])
        result = execute_end(make_end_scene(), state)
        assert len(result.state.history) == 1

    def test_variables_unchanged(self):
        state = base_state("end", {"confidence": 2.0})
        result = execute_end(make_end_scene(), state)
        assert result.state.variables["confidence"] == 2.0

    def test_does_not_mutate_input_state(self):
        state = base_state("end")
        execute_end(make_end_scene(), state)
        assert state.current_scene_id == "end"
        assert len(state.history) == 0
