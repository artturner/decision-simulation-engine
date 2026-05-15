"""
Scene executors — one function per scene type.

Each executor accepts the *current* scene object and the *current* engine
state, works on a defensive copy of the state (so the caller's state is
never mutated), and returns an ``ExecutorResult`` NamedTuple.

``ExecutorResult`` fields
-------------------------
state            EngineState  The new state after the transition.
done             bool         True only for end scenes.
outcome          str | None   Only populated for end scenes.
outcome_message  str | None   Only populated for end scenes.

Dependency injection
--------------------
``execute_conditional`` accepts an optional ``evaluate_fn`` argument
(signature: ``(expression: str, variables: dict) -> bool``).  This
defaults to ``expr.safe_evaluate`` but can be replaced in tests with a
simple lambda, removing the need for real expression strings in fixtures.
"""

from __future__ import annotations

from typing import Callable, NamedTuple

from engine.models import AutoAdvanceScene, ChoiceScene, ConditionalScene, EndScene
from engine.state import EngineState, HistoryEntry


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class ExecutorResult(NamedTuple):
    """Return value shared by all executor functions."""

    state: EngineState
    done: bool
    outcome: str | None = None
    outcome_message: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _copy_state(state: EngineState) -> EngineState:
    """Return a shallow-but-safe copy of *state*.

    * ``variables`` dict is copied (float values are immutable scalars).
    * ``history`` list is copied (``HistoryEntry`` objects are frozen).

    Avoids the overhead of ``copy.deepcopy`` while still guaranteeing
    the caller's state is never mutated by an executor.
    """
    return EngineState(
        current_scene_id=state.current_scene_id,
        variables=dict(state.variables),
        history=list(state.history),
    )


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def execute_choice(
    scene: ChoiceScene,
    state: EngineState,
    choice_index: int,
) -> ExecutorResult:
    """Advance from a choice scene by selecting one of its options.

    Effects from the chosen choice are applied to variables *before* the
    history entry is recorded, so ``variables_snapshot`` captures the
    post-effect state.

    Raises:
        ValueError: ``choice_index`` is out of range for this scene.
    """
    if not (0 <= choice_index < len(scene.choices)):
        raise ValueError(
            f"choice_index {choice_index} is out of range"
            f" for scene with {len(scene.choices)} choice(s)"
        )

    choice = scene.choices[choice_index]
    new_state = _copy_state(state)

    # Apply variable deltas from the chosen option
    new_state.apply_effects(choice.effects)

    new_state.history.append(
        HistoryEntry(
            scene_id=state.current_scene_id,
            next_scene_id=choice.next,
            choice_index=choice_index,
            choice_text=choice.text,
            variables_snapshot=dict(new_state.variables),  # post-effect snapshot
        )
    )
    new_state.current_scene_id = choice.next

    return ExecutorResult(state=new_state, done=False)


def execute_auto_advance(
    scene: AutoAdvanceScene,
    state: EngineState,
) -> ExecutorResult:
    """Advance from an auto-advance scene (no player input required)."""
    new_state = _copy_state(state)
    new_state.history.append(
        HistoryEntry(
            scene_id=state.current_scene_id,
            next_scene_id=scene.next,
        )
    )
    new_state.current_scene_id = scene.next
    return ExecutorResult(state=new_state, done=False)


def execute_conditional(
    scene: ConditionalScene,
    state: EngineState,
    evaluate_fn: Callable[[str, dict[str, float]], bool] | None = None,
) -> ExecutorResult:
    """Advance from a conditional scene by evaluating its branches.

    Conditions are tested *in order*; the first one that evaluates to
    ``True`` wins.  If none match, ``scene.default`` is used.

    Args:
        scene:       The conditional scene to execute.
        state:       Current engine state (variables are the evaluation context).
        evaluate_fn: Expression evaluator with signature
                     ``(expr_str, variables) -> bool``.  Defaults to
                     ``expr.safe_evaluate`` (fail-closed).

    Raises:
        ValueError: No condition matched *and* ``scene.default`` is ``None``.
    """
    if evaluate_fn is None:
        from expr.evaluator import safe_evaluate

        evaluate_fn = safe_evaluate

    next_scene_id: str | None = None
    for condition in scene.conditions:
        if evaluate_fn(condition.condition, state.variables):
            next_scene_id = condition.next
            break

    if next_scene_id is None:
        next_scene_id = scene.default

    if next_scene_id is None:
        raise ValueError(
            f"Conditional scene {state.current_scene_id!r}: no condition matched"
            " and no default is set"
        )

    new_state = _copy_state(state)
    new_state.history.append(
        HistoryEntry(
            scene_id=state.current_scene_id,
            next_scene_id=next_scene_id,
        )
    )
    new_state.current_scene_id = next_scene_id
    return ExecutorResult(state=new_state, done=False)


def execute_end(
    scene: EndScene,
    state: EngineState,
) -> ExecutorResult:
    """Handle an end scene.

    The state is copied but not mutated — end scenes have no outgoing
    transitions or variable effects.  ``done=True`` signals the engine
    that the play session is complete.
    """
    new_state = _copy_state(state)
    return ExecutorResult(
        state=new_state,
        done=True,
        outcome=scene.outcome,
        outcome_message=scene.outcome_message,
    )
