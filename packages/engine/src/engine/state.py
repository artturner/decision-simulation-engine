"""
Engine state — the mutable working object for a play session.

``HistoryEntry``  — frozen (immutable) record of one scene transition.
``EngineState``   — mutable session state: current scene, variables, history.

Serialisation
-------------
``EngineState.to_dict()`` produces the canonical JSON-safe shape used by the
event-sourcing API layer (matches the README state schema).
``EngineState.from_dict()`` reconstructs state from that shape.

The ``variables_snapshot`` field on HistoryEntry is an optional diagnostic
aid; it is intentionally excluded from to_dict / from_dict to keep the
serialised state compact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# History entry — immutable record of a single transition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryEntry:
    """Immutable record of one scene → next_scene transition.

    Pass a *copy* of the variables dict to ``variables_snapshot`` if you want
    a diagnostic snapshot; the field itself cannot be reassigned after
    construction (frozen dataclass) but the dict contents are not deep-frozen.
    """

    scene_id: str
    next_scene_id: str
    choice_index: int | None = None
    choice_text: str | None = None
    variables_snapshot: dict[str, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict, omitting None-valued optional fields."""
        d: dict[str, Any] = {
            "scene_id": self.scene_id,
            "next_scene_id": self.next_scene_id,
        }
        if self.choice_index is not None:
            d["choice_index"] = self.choice_index
        if self.choice_text is not None:
            d["choice_text"] = self.choice_text
        return d


# ---------------------------------------------------------------------------
# Engine state — mutable session object
# ---------------------------------------------------------------------------


@dataclass
class EngineState:
    """Mutable working state for one play session.

    ``current_scene_id``  — the scene the player is currently on.
    ``variables``         — scenario variable values updated by choice effects.
    ``history``           — ordered list of completed transitions (append-only
                           during normal play; truncated during rewind).
    """

    current_scene_id: str
    variables: dict[str, float] = field(default_factory=dict)
    history: list[HistoryEntry] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def apply_effects(self, effects: dict[str, float]) -> None:
        """Apply variable deltas from a choice's effects in place.

        Variables not yet present in ``self.variables`` are initialised to
        ``0.0`` before the delta is added (matches scenario default behaviour
        where a variable may be referenced in an effect before its initial
        value is declared).
        """
        for key, delta in effects.items():
            self.variables[key] = self.variables.get(key, 0.0) + delta

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation matching the README state schema.

        Returns a shallow copy of ``variables`` so that callers mutating the
        returned dict do not affect this state object.
        """
        return {
            "current_scene_id": self.current_scene_id,
            "variables": dict(self.variables),
            "history": [entry.to_dict() for entry in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EngineState:
        """Reconstruct an ``EngineState`` from a ``to_dict()`` payload.

        Missing ``variables`` or ``history`` keys default to empty
        collections for forward-compatibility.
        """
        return cls(
            current_scene_id=data["current_scene_id"],
            variables=dict(data.get("variables", {})),
            history=[
                HistoryEntry(
                    scene_id=entry["scene_id"],
                    next_scene_id=entry["next_scene_id"],
                    choice_index=entry.get("choice_index"),
                    choice_text=entry.get("choice_text"),
                )
                for entry in data.get("history", [])
            ],
        )
