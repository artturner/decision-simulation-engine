"""Minimum decision depth: fewest choice scenes on any start→end route.

Prompt-level depth instructions under-deliver (asking for 3 decision beats
repeatedly yielded 2); surfacing the shortfall as a *validation error* through
the generator's self-repair loop fixed it on the first retry. This module
measures the floor (``min_decision_depth``) and packages it as a
``validate_fn`` for ``generate.generate_scenario``
(``min_decisions_validator``).
"""

from __future__ import annotations

from collections.abc import Callable


def min_decision_depth(scenario_json: dict) -> int:
    """Fewest choice scenes on any route from ``start_scene_id`` to an end.

    DFS over scenes: a ``choice`` counts 1 and branches over its options,
    ``auto_advance`` passes through, ``conditional`` fans out over every
    condition target plus the default. A per-route visited set breaks cycles
    (a route that loops is never shorter than its loop-free reduction, so
    simple paths suffice for the minimum). Dead routes — cycles, dangling
    refs, no reachable end — are ignored; returns 0 when no end is reachable
    at all (that failure belongs to the engine validator).
    """
    scenes = scenario_json.get("scenes") or {}

    def walk(sid, visited: frozenset) -> int | None:
        if not sid or sid in visited or sid not in scenes:
            return None
        scene = scenes[sid] or {}
        stype = scene.get("type")
        if stype == "end":
            return 0
        visited = visited | {sid}
        if stype == "choice":
            nexts = [c.get("next") for c in scene.get("choices") or []]
            cost = 1
        elif stype == "conditional":
            nexts = [c.get("next") for c in scene.get("conditions") or []]
            nexts.append(scene.get("default"))
            cost = 0
        else:  # auto_advance
            nexts = [scene.get("next")]
            cost = 0
        depths = [d for d in (walk(n, visited) for n in nexts) if d is not None]
        return cost + min(depths) if depths else None

    depth = walk(scenario_json.get("start_scene_id"), frozenset())
    return depth if depth is not None else 0


def min_decisions_validator(min_decisions: int) -> Callable[[dict], list[str]]:
    """Build a ``validate_fn`` enforcing a decision-depth floor.

    Engine validator errors are returned first, alone — the depth error is
    appended only when the scenario is otherwise valid, so the self-repair
    loop fixes structure before depth.
    """

    def validate(scenario_json: dict) -> list[str]:
        from engine.validator import validate_scenario

        errors = validate_scenario(scenario_json)
        if errors:
            return errors
        depth = min_decision_depth(scenario_json)
        if depth < min_decisions:
            return [
                "Decision depth too shallow: the shortest route from "
                f"'{scenario_json.get('start_scene_id')}' to an ending passes "
                f"through only {depth} choice scene(s); every route must pass "
                f"through at least {min_decisions}. Add another decision beat "
                "(a `choice` scene) on EVERY branch — including the shortest "
                "one — with options distinct to that branch's situation, not "
                "one generic beat repeated verbatim across branches."
            ]
        return []

    return validate
