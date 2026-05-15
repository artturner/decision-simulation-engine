"""
ScenarioEngine — the single public entry-point for the engine package.

This is the interface the FastAPI service uses.  The engine is stateless
between calls: every method receives or returns an ``EngineState`` object
so that the API layer owns persistence.

step() design
-------------
``step()`` executes exactly the *current* scene (whatever its type) and
returns the state/scene that the player is now on:

* **ChoiceScene** — choice_index required; applies effects, transitions.
* **AutoAdvanceScene** — transitions automatically; no choice_index needed.
* **ConditionalScene** — evaluates conditions, transitions.
* **EndScene** — returns done=True; current_scene_id is unchanged.

This means the caller must make a second ``step()`` call when it transitions
*into* an end scene (the API layer does this automatically).

rewind() design
---------------
The API layer is responsible for truncating the last step event from the
database.  It then passes the *remaining* events (in original seq order) to
``rewind()``, which replays them from the scenario's initial state to
reconstruct the previous ``EngineState``.

The event dicts use the same format as ``HistoryEntry.to_dict()``:
  scene_id, next_scene_id, choice_index (optional), choice_text (optional)
"""

from __future__ import annotations

from engine.executors import (
    execute_auto_advance,
    execute_choice,
    execute_conditional,
    execute_end,
)
from engine.models import (
    AutoAdvanceScene,
    ChoiceScene,
    ConditionalScene,
    EndScene,
    Scenario,
)
from engine.state import EngineState, HistoryEntry
from engine.validator import validate_scenario


class ScenarioEngine:
    def __init__(self, scenario_json: dict) -> None:
        """Validate and load a scenario.

        Raises:
            ValueError: The scenario JSON fails structural or semantic validation.
        """
        errors = validate_scenario(scenario_json)
        if errors:
            raise ValueError(
                "Invalid scenario JSON:\n" + "\n".join(f"  • {e}" for e in errors)
            )
        self.scenario: Scenario = Scenario.model_validate(scenario_json)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> tuple[EngineState, dict]:
        """Initialise a new play session.

        Returns:
            state:     Fresh ``EngineState`` set to the scenario's start scene
                       with initial variable values copied from the scenario.
            scene_dto: Serialisable dict for the start scene (includes scene_id).
        """
        state = EngineState(
            current_scene_id=self.scenario.start_scene_id,
            variables=dict(self.scenario.variables),
        )
        return state, self._scene_to_dto(self.scenario.start_scene_id)

    def step(
        self,
        state: EngineState,
        choice_index: int | None = None,
    ) -> tuple[EngineState, dict, bool, dict | None]:
        """Execute the current scene and advance the state.

        Args:
            state:        Current play state (current_scene_id drives dispatch).
            choice_index: Required when the current scene is a ChoiceScene.

        Returns:
            new_state:    Updated ``EngineState`` (new current_scene_id etc.).
            scene_dto:    Serialisable dict for the scene the player is now on.
            done:         ``True`` if the player has reached an end scene.
            outcome_info: ``{"outcome": …, "outcome_message": …}`` when done,
                          else ``None``.

        Raises:
            ValueError: Unknown scene_id, wrong scene type for choice_index,
                        or invalid choice_index.
        """
        scene_id = state.current_scene_id
        if scene_id not in self.scenario.scenes:
            raise ValueError(
                f"Scene {scene_id!r} not found in this scenario"
            )

        scene = self.scenario.scenes[scene_id]

        if isinstance(scene, ChoiceScene):
            if choice_index is None:
                raise ValueError(
                    f"choice_index is required for choice scene {scene_id!r}"
                )
            result = execute_choice(scene, state, choice_index)

        elif isinstance(scene, AutoAdvanceScene):
            result = execute_auto_advance(scene, state)

        elif isinstance(scene, ConditionalScene):
            result = execute_conditional(scene, state)

        elif isinstance(scene, EndScene):
            result = execute_end(scene, state)

        else:
            raise ValueError(
                f"Unhandled scene type {type(scene).__name__!r} at {scene_id!r}"
            )

        new_state = result.state
        done = result.done
        outcome_info: dict | None = None

        if done:
            outcome_info = {
                "outcome": result.outcome,
                "outcome_message": result.outcome_message,
            }

        return new_state, self._scene_to_dto(new_state.current_scene_id), done, outcome_info

    def rewind(
        self,
        state: EngineState,
        events: list[dict],
    ) -> tuple[EngineState, dict]:
        """Rebuild state by replaying a (pre-truncated) event list.

        The API layer removes the last step event before calling this method.
        The engine starts from the scenario's initial state and replays every
        remaining event in order.

        Expected event dict keys (matches ``HistoryEntry.to_dict()``):
          * ``scene_id``      — scene where the action was taken
          * ``next_scene_id`` — scene transitioned to
          * ``choice_index``  — present for choice events
          * ``choice_text``   — present for choice events

        For ConditionalScene events the stored ``next_scene_id`` is used
        directly (avoids re-evaluating expressions, which is safer for replay).

        Args:
            state:  Current state (used only to signal that a play is in
                    progress; actual variables are rebuilt from scratch).
            events: Truncated event list from the API layer.

        Returns:
            new_state: Reconstructed ``EngineState``.
            scene_dto: Serialisable dict for the scene the player is now on.
        """
        rebuilt = EngineState(
            current_scene_id=self.scenario.start_scene_id,
            variables=dict(self.scenario.variables),
        )

        for event in events:
            scene_id = event.get("scene_id")
            if not scene_id or scene_id not in self.scenario.scenes:
                continue  # defensive: skip unknown or malformed events

            scene = self.scenario.scenes[scene_id]

            if isinstance(scene, ChoiceScene) and event.get("choice_index") is not None:
                result = execute_choice(scene, rebuilt, event["choice_index"])
                rebuilt = result.state

            elif isinstance(scene, AutoAdvanceScene):
                result = execute_auto_advance(scene, rebuilt)
                rebuilt = result.state

            elif isinstance(scene, ConditionalScene):
                # Re-use stored outcome — avoids expression re-evaluation edge cases
                next_id = event.get("next_scene_id")
                if next_id and next_id in self.scenario.scenes:
                    rebuilt = EngineState(
                        current_scene_id=next_id,
                        variables=dict(rebuilt.variables),
                        history=list(rebuilt.history) + [
                            HistoryEntry(
                                scene_id=scene_id,
                                next_scene_id=next_id,
                            )
                        ],
                    )
            # EndScene events are not replayed (the session ended; rewind
            # cannot go past the end)

        return rebuilt, self._scene_to_dto(rebuilt.current_scene_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scene_to_dto(self, scene_id: str) -> dict:
        """Return a JSON-serialisable dict for *scene_id*.

        Includes ``scene_id`` as a top-level key.  Media URL resolution is
        intentionally left to the API layer.
        """
        scene = self.scenario.scenes[scene_id]
        dto = scene.model_dump()
        dto["scene_id"] = scene_id
        return dto
