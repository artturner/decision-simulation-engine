"""Quantitative quality metrics for a branching scenario.

Walks every root-to-end path through the REAL engine (so conditional routing,
effects, and outcomes are evaluated exactly as a learner would experience them)
and reports metrics that make "is the state model actually doing work?" and
"do outcomes follow from accumulated state?" measurable.

Usage (from repo root):
    PYTHONPATH="packages/engine/src;packages/expr/src" \
        python scenario_iterations/analyze.py <import_or_scenario.json> [--json out.json]

Metrics
-------
variables_read        distinct variables referenced by any conditional expression
                      (0 == the state model is write-only / decorative)
choice_points         number of choice scenes on the reachable graph
influential_points    choice points where changing ONLY that choice (holding the
                      others fixed) can change the final outcome, over all combos
inert_choice_scenes   the reached choice scenes that are NOT influential
outcomes_reachable    every declared end outcome that some path actually reaches
outcomes_declared     every outcome declared on an end scene (reachable or not)
paths                 total root-to-end paths enumerated

Valence metrics (require a per-scenario-family config — see --config):
monotonicity          over all terminal paths, pairwise (virtue, outcome-rank)
  .inversions         inversions: pairs where higher virtue → worse outcome
  .pairs              total comparable pairs
  .disagreement       inversions / pairs  (0 == outcomes perfectly track virtue)
contradiction_paths   paths hitting an explicit contradiction predicate

The config is a JSON object:
    {"virtue_vars": ["VarA", "VarB"],
     "outcome_rank": {"worst_outcome": 0, "middle": 1, "best": 2}}
Which variables count as accumulated "virtue" and how outcomes rank is a
scenario-family judgment, so it lives in a config file, not in code (the
fdr-korematsu config is at fdr-korematsu/metrics_config.json). Without a
config the valence metrics are skipped; everything else is generic.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from engine.engine import ScenarioEngine
from engine.models import ChoiceScene
from engine.validator import validate_scenario


def _load_scenario_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    return obj["scenario_json"] if "scenario_json" in obj else obj


def enumerate_paths(scenario_json: dict) -> list[dict]:
    """Return one record per root-to-end path.

    Each record: {choices: [int...], choice_texts: [...], variables: {...},
    outcome: str|None}. Non-choice scenes (auto_advance / conditional) advance
    deterministically via the engine; choice scenes branch over every option.
    """
    engine = ScenarioEngine(scenario_json)
    results: list[dict] = []

    def walk(state, chosen: list[int], texts: list[str], decisions: list,
             seq: list[str]) -> None:
        sid = state.current_scene_id
        scene = engine.scenario.scenes[sid]
        if scene.__class__.__name__ == "EndScene":
            _, _, _done, outcome_info = engine.step(state)
            results.append(
                {
                    "choices": list(chosen),
                    "choice_texts": list(texts),
                    # (scene_id, choice_index) per decision — depth-agnostic influence
                    "decisions": list(decisions),
                    # ordered scene_ids visited (incl. auto/conditional/end) — the
                    # transcript backbone the contradiction judge replays.
                    "scene_seq": seq + [sid],
                    "variables": dict(state.variables),
                    "outcome": (outcome_info or {}).get("outcome"),
                    "end_scene": sid,
                }
            )
            return
        if isinstance(scene, ChoiceScene):
            for i, ch in enumerate(scene.choices):
                new_state, _dto, _done, _oi = engine.step(state, i)
                walk(new_state, chosen + [i], texts + [ch.text[:60]],
                     decisions + [(sid, i)], seq + [sid])
        else:
            # auto_advance or conditional — deterministic given current state
            new_state, _dto, _done, _oi = engine.step(state)
            walk(new_state, chosen, texts, decisions, seq + [sid])

    start_state, _ = engine.start()
    walk(start_state, [], [], [], [])
    return results


def _virtue(variables: dict, virtue_vars) -> float:
    return sum(variables.get(v, 0.0) for v in virtue_vars)


def compute_metrics(scenario_json: dict, paths: list[dict],
                    config: dict | None = None) -> dict:
    """Compute quality metrics. All metrics are generic except the valence
    block (monotonicity + contradiction predicate), which needs ``config`` =
    ``{"virtue_vars": [...], "outcome_rank": {...}}`` and is skipped without it.
    """
    scenes = scenario_json.get("scenes", {})

    # variables_read: distinct identifiers named in any conditional expression
    read_vars: set[str] = set()
    declared_vars = set(scenario_json.get("variables", {}).keys())
    for scene in scenes.values():
        if scene.get("type") == "conditional":
            for cond in scene.get("conditions", []):
                expr = cond.get("condition", "")
                for var in declared_vars:
                    if var in expr:
                        read_vars.add(var)

    # choice scenes actually reached on some path
    reached_choice_scenes = sorted({sid for p in paths for (sid, _i) in p["decisions"]})

    # influential_points (depth-agnostic): a choice scene S is influential if,
    # holding the decisions made BEFORE S fixed, changing the choice at S changes
    # the set of reachable final outcomes. Handles branching / uneven depth.
    influential_scenes: set[str] = set()
    positions = len(reached_choice_scenes)
    for S in reached_choice_scenes:
        by_prefix: dict[tuple, dict[int, set]] = {}
        for p in paths:
            dec = p["decisions"]
            pos = next((k for k, (sid, _i) in enumerate(dec) if sid == S), None)
            if pos is None:
                continue
            prefix = tuple(dec[:pos])
            choice_at_S = dec[pos][1]
            by_prefix.setdefault(prefix, {}).setdefault(choice_at_S, set()).add(
                p["outcome"]
            )
        # influential if some prefix has two choices with differing outcome sets
        for bychoice in by_prefix.values():
            sets = {frozenset(outs) for outs in bychoice.values()}
            if len(bychoice) > 1 and len(sets) > 1:
                influential_scenes.add(S)
                break

    # outcomes: reachable on some path vs declared on any end scene
    reachable_outcomes = sorted({p["outcome"] for p in paths if p["outcome"]})
    declared_outcomes = sorted(
        {s.get("outcome") for s in scenes.values()
         if s.get("type") == "end" and s.get("outcome")}
    )

    metrics = {
        "paths": len(paths),
        "variables_declared": sorted(declared_vars),
        "variables_read": sorted(read_vars),
        "variables_read_count": len(read_vars),
        "choice_points": len(reached_choice_scenes),
        "influential_points": len(influential_scenes),
        "influential_of": positions,
        "inert_choice_scenes": sorted(set(reached_choice_scenes) - influential_scenes),
        "outcomes_reachable": reachable_outcomes,
        "outcomes_declared": declared_outcomes,
    }

    # ------------------------------------------------------------------
    # Valence metrics — need the per-scenario-family config
    # ------------------------------------------------------------------
    if not config:
        metrics["monotonicity"] = None  # skipped: no valence config
        metrics["contradiction_path_count"] = None
        metrics["contradiction_paths"] = None
        metrics["virtue_spread"] = None
        return metrics

    virtue_vars = tuple(config["virtue_vars"])
    outcome_rank = dict(config["outcome_rank"])

    # monotonicity: pairwise inversions between virtue and outcome rank
    inversions = 0
    comparable = 0
    for a, b in itertools.combinations(paths, 2):
        va = _virtue(a["variables"], virtue_vars)
        vb = _virtue(b["variables"], virtue_vars)
        if va == vb:
            continue
        comparable += 1
        hi, lo = (a, b) if va > vb else (b, a)
        rhi = outcome_rank.get(hi["outcome"], 1)
        rlo = outcome_rank.get(lo["outcome"], 1)
        if rhi < rlo:  # higher virtue but strictly worse outcome
            inversions += 1

    # explicit contradiction predicates (relative to the observed virtue spread)
    virtues = sorted(_virtue(p["variables"], virtue_vars) for p in paths)
    lo_cut = virtues[len(virtues) // 4]          # 25th pct
    hi_cut = virtues[(3 * len(virtues)) // 4]    # 75th pct
    contradiction_paths = []
    best_rank = max(outcome_rank.values(), default=2)
    worst_rank = min(outcome_rank.values(), default=0)
    for p in paths:
        v = _virtue(p["variables"], virtue_vars)
        rank = outcome_rank.get(p["outcome"], 1)
        if rank == best_rank and v <= lo_cut:
            contradiction_paths.append(
                {**_slim(p, virtue_vars), "kind": "undeserved_triumph"}
            )
        elif rank == worst_rank and v >= hi_cut:
            contradiction_paths.append(
                {**_slim(p, virtue_vars), "kind": "unjust_condemnation"}
            )

    metrics["monotonicity"] = {
        "inversions": inversions,
        "pairs": comparable,
        "disagreement": round(inversions / comparable, 4) if comparable else 0.0,
    }
    metrics["contradiction_path_count"] = len(contradiction_paths)
    metrics["contradiction_paths"] = contradiction_paths
    metrics["virtue_spread"] = {
        "min": virtues[0], "p25": lo_cut, "p75": hi_cut, "max": virtues[-1],
    }
    return metrics


def _slim(p: dict, virtue_vars=None) -> dict:
    rec = {
        "choices": p["choices"],
        "variables": p["variables"],
        "outcome": p["outcome"],
    }
    if virtue_vars is not None:
        rec["virtue"] = _virtue(p["variables"], virtue_vars)
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", help="path to <slug>-import.json or bare scenario_json")
    ap.add_argument("--json", help="write full metrics to this path")
    ap.add_argument("--dump-paths", action="store_true", help="print every path record")
    ap.add_argument(
        "--config",
        help="JSON file with {'virtue_vars': [...], 'outcome_rank': {...}} enabling "
        "the valence metrics (monotonicity + contradiction predicate); "
        "e.g. fdr-korematsu/metrics_config.json",
    )
    ap.add_argument(
        "--judge",
        choices=["none", "mock", "llm"],
        default="none",
        help="narrative-contradiction judge: 'llm' = real Anthropic judge "
        "(needs SDK + ANTHROPIC_API_KEY); 'mock' = deterministic offline stand-in.",
    )
    args = ap.parse_args(argv)

    scenario_json = _load_scenario_json(Path(args.scenario))
    errors = validate_scenario(scenario_json)
    if errors:
        print("VALIDATION ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    config = None
    if args.config:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))

    paths = enumerate_paths(scenario_json)
    metrics = compute_metrics(scenario_json, paths, config)

    if args.judge != "none":
        import contradiction_judge as cj

        if args.judge == "llm":
            try:
                judge_fn = cj.make_anthropic_judge_fn(scenario_json=scenario_json)
                backend = "llm"
            except cj.JudgeUnavailable as exc:
                print(f"[judge] LLM judge unavailable ({exc}); skipping.", file=sys.stderr)
                judge_fn = None
        else:
            judge_fn = cj.make_heuristic_judge_fn(scenario_json)
            backend = "heuristic(offline stand-in)"
        if judge_fn is not None:
            metrics["narrative_contradictions"] = cj.judge_paths(
                scenario_json, paths, judge_fn, backend
            )

    virtue_vars = tuple(config["virtue_vars"]) if config else None
    print(json.dumps(metrics, indent=2))
    if args.dump_paths:
        print("\n--- PATHS ---")
        for p in paths:
            virtue = (f"virtue={_virtue(p['variables'], virtue_vars):+.0f} "
                      if virtue_vars else "")
            print(f"  choices={p['choices']} outcome={p['outcome']:>24} "
                  f"{virtue}vars={p['variables']}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"metrics": metrics,
                 "paths": [_slim(p, virtue_vars) for p in paths]},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
