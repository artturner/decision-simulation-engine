"""Sweep the existing scenario library for the GENERIC quality signals that
transfer across scenarios (unlike the fdr-korematsu-tuned monotonicity/judge):

  * declared vs READ variables  -> write-only ("decorative") state model
  * conditional-scene count      -> any state-gating at all?
  * influential / choice points  -> do choices actually change the outcome?
  * outcomes reachable, paths

This is the baseline defect profile that motivates the automated quality loop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from analyze import _load_scenario_json, compute_metrics, enumerate_paths
from engine.validator import validate_scenario

# (label, path). fdr uses v0_original = the AS-GENERATED baseline (root is now v4).
ROOT = Path(__file__).resolve().parent.parent
LIB = [
    ("cherokee-nation", ROOT / "cherokee-nation-import.json"),
    ("convention-1787", ROOT / "convention-1787-import.json"),
    ("drawing-the-lines", ROOT / "drawing-the-lines-import.json"),
    ("liberty-park", ROOT / "liberty-park-import.json"),
    ("motor-voter", ROOT / "motor-voter-import.json"),
    ("party-realignment", ROOT / "party-realignment-import.json"),
    ("probable-cause", ROOT / "probable-cause-import.json"),
    ("rio-grande", ROOT / "rio-grande-import.json"),
    ("shaping-the-aca", ROOT / "shaping-the-aca-import.json"),
    ("the-marshall-gambit", ROOT / "the-marshall-gambit-import.json"),
    ("fdr-korematsu (v0 as-gen)", ROOT / "scenario_iterations/fdr-korematsu/v0_original-import.json"),
    ("fdr-korematsu (v4 fixed)", ROOT / "scenario_iterations/fdr-korematsu/v4_ending_fix-import.json"),
]


def summarize(path: Path) -> dict:
    sj = _load_scenario_json(path)
    errors = validate_scenario(sj)
    if errors:
        return {"valid": False, "errors": errors[:2]}
    scenes = sj["scenes"]
    declared = list(sj.get("variables", {}).keys())
    cond_scenes = [k for k, s in scenes.items() if s.get("type") == "conditional"]
    read = set()
    for s in scenes.values():
        if s.get("type") == "conditional":
            for c in s.get("conditions", []):
                expr = c.get("condition", "")
                for v in declared:
                    if v in expr:
                        read.add(v)
    paths = enumerate_paths(sj)
    m = compute_metrics(sj, paths)
    return {
        "valid": True,
        "scenes": len(scenes),
        "vars_declared": len(declared),
        "vars_read": len(read),
        "write_only_vars": len(declared) - len(read),
        "cond_scenes": len(cond_scenes),
        "choice_pts": m["choice_points"],
        "influential": m["influential_points"],
        "paths": m["paths"],
        "outcomes": len(m["outcomes_reachable"]),
    }


def main() -> int:
    rows = []
    for label, path in LIB:
        if not path.is_file():
            rows.append((label, {"valid": False, "errors": ["file not found"]}))
            continue
        try:
            rows.append((label, summarize(path)))
        except Exception as exc:  # noqa: BLE001
            rows.append((label, {"valid": False, "errors": [str(exc)[:80]]}))

    hdr = f"{'scenario':28s} {'scn':>3} {'vars':>4} {'read':>4} {'w-only':>6} {'cond':>4} {'infl/choice':>11} {'paths':>5} {'outc':>4}"
    print(hdr); print("-" * len(hdr))
    n_writeonly = n_nocond = n_choicegap = valid = 0
    for label, r in rows:
        if not r.get("valid"):
            print(f"{label:28s} INVALID: {r.get('errors')}")
            continue
        valid += 1
        wo = r["write_only_vars"] == r["vars_declared"] and r["vars_declared"] > 0
        nc = r["cond_scenes"] == 0
        cg = r["influential"] < r["choice_pts"]
        n_writeonly += wo; n_nocond += nc; n_choicegap += cg
        flags = "".join(["W" if wo else ".", "C" if nc else ".", "G" if cg else "."])
        print(f"{label:28s} {r['scenes']:>3} {r['vars_declared']:>4} {r['vars_read']:>4} "
              f"{r['write_only_vars']:>6} {r['cond_scenes']:>4} "
              f"{str(r['influential'])+'/'+str(r['choice_pts']):>11} {r['paths']:>5} {r['outcomes']:>4}  {flags}")
    print("-" * len(hdr))
    print(f"valid scenarios: {valid}")
    print(f"  [W] ALL variables write-only (decorative state):     {n_writeonly}")
    print(f"  [C] ZERO conditional scenes (no state-gating):        {n_nocond}")
    print(f"  [G] some choice points DON'T change outcome (infl<ch): {n_choicegap}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
