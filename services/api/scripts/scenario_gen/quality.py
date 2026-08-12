"""Pre-image quality gate + reviser loop for generated scenarios.

Sits between ``generate_scenario()`` and the image steps in the CLI. Cost-ordered:

1. **Structural gate** (free, instant) — exhaustive path analysis through the
   real engine (``scenario_iterations/analyze.py``). Thresholds:
     * if variables are declared, at least one must be READ by a conditional
     * at least one choice point, and EVERY choice point influential
     * at least 2 distinct outcomes reachable
2. **LLM contradiction judge** (only when needed) — K-sample majority voting
   (``scenario_iterations/stabilize_judge.py``); a single pass is too noisy to
   gate on. Only STABLE (majority-flagged) paths count.
3. **Reviser** — an LLM consumes the findings and rewrites ``scenario_json``,
   with guardrails: every revision is re-validated and re-scored, the best
   scoring version is kept, and iterations are capped.

Acceptance = structural gate passes AND (judge unavailable OR 0 stable
contradictions). Per the cost policy, a scenario that passes the structural
gate *as generated* is accepted without spending judge calls; any *revised*
version must also survive the judge.

The heavy analysis code lives in ``scenario_iterations/`` (proven against the
fdr-korematsu v0→v4 case study) and is imported from there — reuse, don't fork.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import REPO_ROOT, depth, llm

_ITERATIONS_DIR = REPO_ROOT / "scenario_iterations"

DEFAULT_JUDGE_K = 5
DEFAULT_MAX_ITERS = 3
DEFAULT_JUDGE_WORKERS = 6
# Bound on unique transcripts judged per version (K samples each). Big
# scenarios (shaping-the-aca: 243 paths) would otherwise cost >1k calls.
DEFAULT_TRANSCRIPT_CAP = 80


def _harness():
    """Import the analysis harness from scenario_iterations/ (not a package)."""
    p = str(_ITERATIONS_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)
    import analyze  # noqa: PLC0415
    import contradiction_judge  # noqa: PLC0415
    import stabilize_judge  # noqa: PLC0415

    return analyze, contradiction_judge, stabilize_judge


# ---------------------------------------------------------------------------
# Structural gate
# ---------------------------------------------------------------------------


@dataclass
class GateResult:
    ok: bool
    checks: dict[str, dict]
    metrics: dict
    paths: list[dict] = field(repr=False, default_factory=list)


def structural_gate(scenario_json: dict) -> GateResult:
    """Free, deterministic gate over every root-to-end path in the real engine."""
    analyze, _cj, _sj = _harness()
    paths = analyze.enumerate_paths(scenario_json)
    m = analyze.compute_metrics(scenario_json, paths)
    # Informational (not gated): fewest choice scenes on any start→end route,
    # so the report shows whether a --min-decisions floor was met.
    m["decisions_min"] = depth.min_decision_depth(scenario_json)

    declared = m["variables_declared"]
    checks = {
        "variables_read": {
            "ok": not declared or m["variables_read_count"] >= 1,
            "detail": (
                f"{len(declared)} variable(s) declared "
                f"({', '.join(declared) or 'none'}), "
                f"{m['variables_read_count']} read by conditional scenes"
            ),
        },
        "all_choices_influential": {
            "ok": m["choice_points"] >= 1 and not m["inert_choice_scenes"],
            "detail": (
                f"{m['influential_points']}/{m['choice_points']} choice points "
                f"influential; inert: {m['inert_choice_scenes'] or 'none'}"
            ),
        },
        "outcomes_reachable": {
            "ok": len(m["outcomes_reachable"]) >= 2,
            "detail": (
                f"{len(m['outcomes_reachable'])} reachable "
                f"({', '.join(m['outcomes_reachable']) or 'none'}) of "
                f"{len(m['outcomes_declared'])} declared "
                f"({', '.join(m['outcomes_declared']) or 'none'})"
            ),
        },
    }
    return GateResult(
        ok=all(c["ok"] for c in checks.values()),
        checks=checks,
        metrics=m,
        paths=paths,
    )


# ---------------------------------------------------------------------------
# Stabilized LLM judge
# ---------------------------------------------------------------------------


def default_judge_factory(scenario_json: dict):
    """Premise-aware Anthropic judge, or None when SDK/key are missing."""
    _a, cj, _s = _harness()
    try:
        return cj.make_anthropic_judge_fn(scenario_json=scenario_json)
    except cj.JudgeUnavailable:
        return None


def judge_stability(
    scenario_json: dict,
    paths: list[dict],
    judge_fn,
    *,
    k: int = DEFAULT_JUDGE_K,
    workers: int = DEFAULT_JUDGE_WORKERS,
    transcript_cap: int | None = DEFAULT_TRANSCRIPT_CAP,
) -> dict:
    _a, _c, stabilize_judge = _harness()
    return stabilize_judge.stabilize(
        scenario_json, paths, judge_fn, k=k, workers=workers,
        transcript_cap=transcript_cap,
    )


# ---------------------------------------------------------------------------
# Findings → reviser
# ---------------------------------------------------------------------------


def render_findings(gate: GateResult, stability: dict | None) -> str:
    lines = ["STRUCTURAL QUALITY FINDINGS (exhaustive path analysis through the "
             "real engine):"]
    for name, c in gate.checks.items():
        lines.append(f"- {'PASS' if c['ok'] else 'FAIL'} {name}: {c['detail']}")
    m = gate.metrics
    lines.append(
        f"- snapshot: paths={m['paths']}, choice_points={m['choice_points']}, "
        f"influential={m['influential_points']}, "
        f"outcomes_reachable={len(m['outcomes_reachable'])}"
    )
    # End-scene → outcome-code map: distinct outcomes are counted by the
    # `outcome` CODE on end scenes, so a shared generic code (e.g. every
    # ending saying "success") reads as ONE outcome no matter how many end
    # scenes exist. Make any collision visible to the reviser.
    ends: dict[tuple[str, str], int] = {}
    for p in gate.paths:
        key = (p.get("end_scene", "?"), p.get("outcome") or "(none)")
        ends[key] = ends.get(key, 0) + 1
    lines.append("- end scenes reached (distinct outcomes = distinct `outcome` "
                 "codes, NOT distinct scenes):")
    for (sid, outcome), n in sorted(ends.items()):
        lines.append(f"    end scene '{sid}' outcome_code='{outcome}' "
                     f"— reached by {n} path(s)")
    if stability is not None:
        lines.append("")
        if stability["stable_total"]:
            lines.append(
                "STABLE NARRATIVE CONTRADICTIONS (LLM judge, K="
                f"{stability['k']} majority vote — fix ALL of these; "
                "minority-flagged paths are noise and are omitted):"
            )
            for i, r in enumerate(stability["stable"], 1):
                lines.append(
                    f"{i}. path choices={r['choices']} → end scene "
                    f"'{r.get('end_scene', '?')}' (outcome {r['outcome']}), "
                    f"severity {r['modal_severity']}, offending scene "
                    f"'{r['modal_scene']}':\n   {r['example_explanation']}"
                )
        else:
            lines.append("STABLE NARRATIVE CONTRADICTIONS: none.")
    return "\n".join(lines)


_REVISER_ADDENDUM = """\

---

# Revision Mode

You are NOT generating a new scenario. You are given an existing `scenario_json`
plus quality findings from an automated gate, and you must produce a REVISED
`scenario_json` that fixes every finding with the SMALLEST change that works.

Proven repair shapes, in order of preference:

1. **State-gate the endings** (fixes write-only variables AND inert choices at
   once): reroute the final choice/branches into ONE new `conditional` resolver
   scene that reads the accumulated variables and routes to the EXISTING end
   scenes. Reframe those endings' narration as cumulative-arc verdicts (tiers)
   rather than descriptions of a single final action, keeping each ending's
   `outcome` code, `image`, and overall valence.
2. **Give a silently-ignored early choice real downstream consequences**: if an
   early branch converges with no lasting difference, either add variable
   effects that a later conditional reads, or give one branch a genuinely
   different beat (and, only if warranted, a new distinct ending).
3. **Add a state-distinct ending** only when fewer than 2 outcomes are
   reachable and no existing ending can be made reachable by retuning
   thresholds.
4. **Fix over/under-claiming ending narration** (text-only): an ending must be
   accurate for EVERY path that can reach it — never congratulate the learner
   for preventing something a reaching path shows happening, and never condemn
   them for something a reaching path avoided. Prefer arc-scoped wording
   ("the decisions that followed bent toward…") over absolute claims. NEVER
   enumerate hypothetical example decision sequences in an ending ("perhaps you
   co-sponsored early then voted nay, or abstained…") — some path that reaches
   the ending will contradict them. Especially for a conditional's DEFAULT
   (middle-tier) ending, characterize the record only in terms every reaching
   path shares, or in terms of how others PERCEIVE the record, not as claims
   about which specific choices were made.

Hard constraints:

- **Distinct endings are counted by the `outcome` CODE on `end` scenes.** Every
  meaningfully different ending must carry its OWN `outcome` code (e.g.
  `principled_stand`, `hollow_victory`, `broken_trust`) — never one shared
  generic code like `success` across all endings. A choice only counts as
  influential if changing it can change which `outcome` code the path ends on.
- The expression grammar supports ONLY `&&  ||  !  ==  !=  <  <=  >  >=`,
  parentheses, numbers, `true`/`false`. **NO ARITHMETIC** — write per-variable
  thresholds (`A >= 4 && B >= 2`), never `A + B >= 6`.
- Choose thresholds that are ATTAINABLE given the effects on real paths — every
  end scene should be reachable by some combination of choices. Trace the
  variable sums along a few paths to check.
- A `conditional` scene is shown to the learner as a visible story beat: give
  it purposeful title/description/narration (the moment the accumulated record
  is weighed), not filler.
- Preserve everything the findings don't require changing: scene ids, `image`
  filenames, metadata, reflection arrays, choice texts, effects. A NEW scene
  should reuse an existing scene's `image` filename where visually plausible —
  new images are expensive.
- The revised object must satisfy the full Output Format Specification above.

Output ONLY the complete revised `scenario_json` object.
"""


class ReviseError(Exception):
    """Raised when the reviser cannot produce a valid scenario_json."""


def _reviser_system() -> str:
    from . import generate  # local import to avoid cycles at module load

    return generate._load_system_prompt() + _REVISER_ADDENDUM


def revise_scenario(
    scenario_json: dict,
    findings: str,
    model: str,
    *,
    call_fn: Callable[..., str] | None = None,
    validate_fn: Callable[[dict], list[str]] | None = None,
    max_repairs: int = 2,
) -> dict:
    """One reviser pass: findings + current JSON → validated revised JSON.

    Structural-validator failures get a short in-conversation repair loop
    (mirroring ``generate.generate_scenario``); quality re-scoring is the
    caller's job.
    """
    call = call_fn or llm.call_conversation
    if validate_fn is None:
        from engine.validator import validate_scenario

        validate_fn = validate_scenario

    instruction = (
        f"{findings}\n\n"
        "CURRENT scenario_json:\n"
        "```json\n"
        f"{json.dumps(scenario_json, ensure_ascii=False, indent=1)}\n"
        "```\n\n"
        "Revise it per Revision Mode. Output ONLY the complete revised "
        "scenario_json object."
    )
    messages: list[dict] = [{"role": "user", "content": instruction}]
    system = _reviser_system()

    last_errors: list[str] = []
    for attempt in range(max_repairs + 1):
        text = call(system=system, messages=messages, model=model,
                    max_tokens=32000)
        try:
            revised = llm.extract_json(text)
        except ValueError as exc:
            revised = None
            last_errors = [f"Output was not valid JSON: {exc}"]

        if isinstance(revised, dict):
            errors = validate_fn(revised)
            if not errors:
                return revised
            last_errors = errors

        if attempt < max_repairs:
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The revised JSON failed engine validation:\n"
                        + "\n".join(f"- {e}" for e in last_errors)
                        + "\n\nFix every error and output the corrected, "
                        "complete scenario_json object only."
                    ),
                }
            )

    raise ReviseError(
        "Reviser could not produce a valid scenario_json after "
        f"{max_repairs + 1} attempts. Last errors:\n"
        + "\n".join(f"- {e}" for e in last_errors)
    )


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------


@dataclass
class QualityResult:
    scenario_json: dict
    passed: bool
    report: dict


def _score(gate: GateResult, stability: dict | None) -> tuple:
    """Keep-best comparator (higher is better). Structural health dominates;
    stable contradictions break ties among structurally-equal versions."""
    m = gate.metrics
    return (
        int(gate.ok),
        -len(m["inert_choice_scenes"]),
        min(len(m["outcomes_reachable"]), 5),
        min(m["variables_read_count"], 2),
        -(stability["stable_major"] if stability else 0),
        -(stability["stable_total"] if stability else 0),
    )


def run_quality_loop(
    scenario_json: dict,
    *,
    gen_model: str,
    judge_k: int = DEFAULT_JUDGE_K,
    judge_workers: int = DEFAULT_JUDGE_WORKERS,
    transcript_cap: int | None = DEFAULT_TRANSCRIPT_CAP,
    max_iters: int = DEFAULT_MAX_ITERS,
    use_judge: bool = True,
    judge_on_pass: bool = False,
    call_fn: Callable[..., str] | None = None,
    judge_factory: Callable[[dict], Any] | None = None,
    log: Callable[[str], None] = print,
) -> QualityResult:
    """Gate → (judge) → revise → re-score, keeping the best-scoring version.

    ``call_fn`` (reviser LLM) and ``judge_factory`` (scenario → per-path judge
    fn or None) are injectable for tests. Returns the best version seen, its
    pass/fail verdict, and a full JSON-serializable report.
    """
    judge_factory = judge_factory or default_judge_factory
    judge_model = None
    judge_available = use_judge

    versions: list[dict] = []  # report entries
    candidates: list[dict] = []  # scenario_json per version (not in report)
    current = scenario_json

    for it in range(max_iters + 1):
        gate = structural_gate(current)
        stability = None
        # Judge policy: an as-generated structural pass is accepted without
        # judge spend (override with judge_on_pass — e.g. repair runs on
        # existing files, which are suspect by definition); every other judged
        # situation needs stable findings — except a gate-fail on the FINAL
        # iteration, where no reviser call follows and the findings would go
        # unused.
        want_judge = judge_available and (
            (gate.ok and (it > 0 or judge_on_pass))
            or (not gate.ok and it < max_iters)
        )
        if want_judge:
            judge_fn = judge_factory(current)
            if judge_fn is None:
                judge_available = False
                log("  [quality] LLM judge unavailable — structural gate only.")
            else:
                judge_model = getattr(judge_fn, "model", None)
                n_paths = len(gate.paths)
                log(f"  [quality] judging v{it}: {n_paths} paths, K={judge_k} "
                    "majority vote …")
                stability = judge_stability(
                    current, gate.paths, judge_fn,
                    k=judge_k, workers=judge_workers,
                    transcript_cap=transcript_cap,
                )
                log(f"  [quality] v{it}: stable contradictions="
                    f"{stability['stable_total']} "
                    f"(major={stability['stable_major']}, "
                    f"flaky={len(stability['flaky'])}, clean={stability['clean']})")

        judge_vacuous = bool(stability and stability.get("all_errors"))
        if judge_vacuous:
            log("  [quality] every judge sample errored (API outage/billing?) "
                "— verdicts are vacuous; this version cannot be verified.")
        accepted = gate.ok and not judge_vacuous and (
            not judge_available
            or stability is None  # as-generated pass, judge skipped by policy
            or stability["stable_total"] == 0
        )
        versions.append(
            {
                "iteration": it,
                "accepted": accepted,
                "gate_ok": gate.ok,
                "checks": gate.checks,
                "metrics": {k: v for k, v in gate.metrics.items()
                            if not k.startswith("contradiction")
                            and k not in ("monotonicity", "virtue_spread")},
                "stability": (
                    {k: stability[k] for k in
                     ("k", "majority", "judged_transcripts", "capped", "errors",
                      "all_errors", "stable_total", "stable_major", "clean",
                      "stable")}
                    if stability else None
                ),
                "score": _score(gate, stability),
            }
        )
        candidates.append(current)

        failing = [n for n, c in gate.checks.items() if not c["ok"]]
        log(f"  [quality] v{it}: "
            + ("PASS" if accepted else
               f"FAIL ({', '.join(failing) or 'stable contradictions'})"))

        if accepted or it == max_iters:
            break
        if judge_vacuous:
            # The API is unreachable — the reviser call would fail too.
            log("  [quality] stopping early; returning the best version so far.")
            break

        findings = render_findings(gate, stability)
        log(f"  [quality] revising ({gen_model}), iteration {it + 1}/{max_iters} …")
        try:
            current = revise_scenario(current, findings, gen_model,
                                      call_fn=call_fn)
        except ReviseError as exc:
            log(f"  [quality] reviser failed: {exc}")
            break
        except Exception as exc:  # noqa: BLE001 — API/transport errors must
            # not crash the pipeline; keep-best still returns a scored version.
            log(f"  [quality] reviser call errored ({exc}); "
                "returning the best version so far.")
            break

    best_i = max(range(len(versions)), key=lambda i: versions[i]["score"])
    passed = versions[best_i]["accepted"]
    report = {
        "thresholds": {
            "variables_read": ">=1 when variables are declared",
            "all_choices_influential": "every reached choice point can change the outcome",
            "outcomes_reachable": ">=2",
            "stable_contradictions": "0 (K-sample majority vote)"
            if judge_available else "not evaluated (judge unavailable/disabled)",
        },
        "policy": {
            "judge_k": judge_k,
            "transcript_cap": transcript_cap,
            "max_iters": max_iters,
            "judge_model": judge_model,
            "judge_available": judge_available,
            "judge_on_initial_pass": judge_on_pass,
        },
        "versions": versions,
        "best_iteration": best_i,
        "revisions_attempted": len(versions) - 1,
        "passed": passed,
    }
    return QualityResult(
        scenario_json=candidates[best_i], passed=passed, report=report
    )
