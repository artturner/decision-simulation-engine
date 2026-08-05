"""Run the automated quality loop on an EXISTING import JSON (repair/benchmark).

This is the standalone entry point for the loop that lives in
``services/api/scripts/scenario_gen/quality.py`` (the CLI runs it inline after
generation). Originals are never overwritten: the revised scenario is written
to ``<input>.revised.json`` and the report to ``<input>.quality-report.json``
unless overridden.

Usage (any CWD — the script re-anchors itself to services/api so .env loads):
    PYTHONUTF8=1 py -3.11 scenario_iterations/run_quality_loop.py \
        rio-grande-import.json [-k 5] [--iters 3] [--no-judge] \
        [--out X.json] [--report Y.json] [--model claude-opus-4-8] [--gate-only]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVICE_DIR = REPO_ROOT / "services" / "api"

for p in (SERVICE_DIR, REPO_ROOT / "packages" / "engine" / "src",
          REPO_ROOT / "packages" / "expr" / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", help="path to <slug>-import.json or bare scenario_json")
    ap.add_argument("--out", help="revised import path (default <input>.revised.json)")
    ap.add_argument("--report", help="report path (default <input>.quality-report.json)")
    ap.add_argument("-k", type=int, default=None, help="judge samples per path")
    ap.add_argument("--iters", type=int, default=None, help="max reviser iterations")
    ap.add_argument("--cap", type=int, default=None, help="unique-transcript cap")
    ap.add_argument("--no-judge", action="store_true", help="structural gate only")
    ap.add_argument("--judge-on-pass", action="store_true",
                    help="run the LLM judge even if the input passes the "
                    "structural gate (recommended for repair runs on existing "
                    "files, which skip the as-generated benefit of the doubt)")
    ap.add_argument("--gate-only", action="store_true",
                    help="score, never revise (sets --iters 0)")
    ap.add_argument("--model", help="reviser model (default settings.SCENARIO_GEN_MODEL)")
    args = ap.parse_args(argv)

    src = Path(args.scenario).resolve()
    out = Path(args.out).resolve() if args.out else src.with_suffix(".revised.json")
    report_path = (Path(args.report).resolve() if args.report
                   else src.with_suffix(".quality-report.json"))

    # settings' env_file=".env" resolves relative to CWD → anchor to services/api.
    os.chdir(SERVICE_DIR)
    from app.core.config import settings  # noqa: PLC0415
    from scripts.scenario_gen import quality  # noqa: PLC0415

    obj = json.loads(src.read_text(encoding="utf-8"))
    scenario_json = obj["scenario_json"] if "scenario_json" in obj else obj
    model = args.model or settings.SCENARIO_GEN_MODEL

    kwargs = {}
    if args.k is not None:
        kwargs["judge_k"] = args.k
    if args.cap is not None:
        kwargs["transcript_cap"] = args.cap
    kwargs["max_iters"] = 0 if args.gate_only else (
        args.iters if args.iters is not None else quality.DEFAULT_MAX_ITERS
    )

    result = quality.run_quality_loop(
        scenario_json, gen_model=model, use_judge=not args.no_judge,
        judge_on_pass=args.judge_on_pass, **kwargs
    )

    report_path.write_text(json.dumps(result.report, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(f"\nreport  : {report_path}")

    first = result.report["versions"][0]
    best = result.report["versions"][result.report["best_iteration"]]

    def _row(v):
        m = v["metrics"]
        stab = v["stability"]
        return (f"gate_ok={v['gate_ok']} vars_read={m['variables_read_count']} "
                f"infl={m['influential_points']}/{m['choice_points']} "
                f"outcomes={len(m['outcomes_reachable'])} paths={m['paths']} "
                f"stable_contra={stab['stable_total'] if stab else 'n/a'}")

    print(f"v0    : {_row(first)}")
    print(f"best  : v{result.report['best_iteration']}  {_row(best)}")
    print(f"verdict: {'PASSED' if result.passed else 'FAILED'} "
          f"({result.report['revisions_attempted']} revision(s) attempted)")

    if result.report["best_iteration"] > 0:
        if "scenario_json" in obj:
            obj["scenario_json"] = result.scenario_json
            revised_obj = obj
        else:
            revised_obj = result.scenario_json
        out.write_text(json.dumps(revised_obj, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"revised : {out}")
    else:
        print("revised : (input unchanged — best version is the original)")
    return 0 if result.passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
