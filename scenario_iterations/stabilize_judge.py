"""Multi-sample contradiction judging with majority voting.

A single LLM judge pass is noisy (run-to-run variance). This judges every path
K times and partitions paths into:

  * STABLE  — flagged by a MAJORITY of runs (the trustworthy contradiction set)
  * FLAKY   — flagged by some runs but not a majority (variance; do NOT act on)
  * CLEAN   — never flagged

Only STABLE paths should drive a fix. ``stabilize()`` is the reusable core the
automated pre-image quality loop calls; the CLI below is a thin wrapper.

Cost note: paths with IDENTICAL transcripts share one K-sample vote (judging
the same text twice is pure waste), and ``transcript_cap`` bounds the number of
unique transcripts judged — capped-out paths are reported as skipped, never
silently dropped.

Run from services/api (so .env loads) with engine/expr/services-api on PYTHONPATH:
    PYTHONUTF8=1 PYTHONPATH="...engine;...expr;...services/api" \
        py -3.11 scenario_iterations/stabilize_judge.py <import.json> -k 5
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import contradiction_judge as cj
from analyze import _load_scenario_json, enumerate_paths


def stabilize(
    scenario_json: dict,
    paths: list[dict],
    judge_fn: cj.JudgeFn,
    k: int = 5,
    workers: int = 6,
    transcript_cap: int | None = None,
) -> dict:
    """Judge every unique transcript K times and majority-vote per path.

    Returns a dict with ``stable`` / ``flaky`` / ``clean`` path records plus
    bookkeeping (k, majority, errors, judged_transcripts, capped). Each stable
    record carries a modal severity/scene and one sample explanation so a
    reviser can act on it.
    """
    majority = k // 2 + 1
    transcripts = [cj.build_transcript(scenario_json, p) for p in paths]

    # Deduplicate: one K-sample vote per unique transcript.
    rep_path: dict[str, dict] = {}
    for i, t in enumerate(transcripts):
        rep_path.setdefault(t, paths[i])
    keys = list(rep_path)
    capped = transcript_cap is not None and len(keys) > transcript_cap
    if capped:
        keys = keys[:transcript_cap]

    votes: dict[str, list] = {t: [] for t in keys}
    errors = 0

    def one(t: str):
        return t, judge_fn(rep_path[t], t)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(one, t) for t in keys for _ in range(k)]
        for fut in as_completed(futs):
            try:
                t, v = fut.result()
                votes[t].append(v)
            except Exception:  # noqa: BLE001 — a lost sample is a non-flag vote
                errors += 1

    stable, flaky, skipped = [], [], []
    clean = 0
    per_path = []
    for i, p in enumerate(paths):
        vs = votes.get(transcripts[i])
        if vs is None:  # transcript_cap cut this one — report, don't hide
            rec = {"choices": p["choices"], "outcome": p["outcome"],
                   "flagged": None, "samples": 0, "skipped": True}
            per_path.append(rec)
            skipped.append(rec)
            continue
        flagged_vs = [v for v in vs if v.get("contradiction")]
        nflag = len(flagged_vs)
        sev = Counter(v.get("severity") for v in flagged_vs).most_common(1)
        scene = Counter(v.get("offending_scene") for v in flagged_vs).most_common(1)
        rec = {
            "choices": p["choices"],
            "outcome": p["outcome"],
            "end_scene": p.get("end_scene"),
            "flagged": nflag,
            "samples": len(vs),
            "modal_severity": sev[0][0] if sev else "none",
            "modal_scene": scene[0][0] if scene else "",
            "example_explanation": (
                flagged_vs[0].get("explanation", "") if flagged_vs else ""
            ),
        }
        per_path.append(rec)
        if nflag >= majority:
            stable.append(rec)
        elif nflag > 0:
            flaky.append(rec)
        else:
            clean += 1

    return {
        "k": k,
        "majority": majority,
        "paths": len(paths),
        "judged_transcripts": len(keys),
        "capped": capped,
        "errors": errors,
        # Every sample errored (API outage/billing): verdicts are VACUOUS —
        # "clean" here means "unjudged". Callers must not gate on this.
        "all_errors": bool(keys) and all(not votes[t] for t in keys),
        "stable": stable,
        "stable_total": len(stable),
        "stable_major": sum(1 for r in stable if r["modal_severity"] == "major"),
        "flaky": flaky,
        "clean": clean,
        "skipped": len(skipped),
        "per_path": per_path,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("-k", type=int, default=5, help="samples per path")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--cap", type=int, default=None,
                    help="max unique transcripts to judge (skipped ones reported)")
    ap.add_argument("--json", help="write full per-path tallies here")
    args = ap.parse_args(argv)

    sj = _load_scenario_json(Path(args.scenario))
    paths = enumerate_paths(sj)
    # raises JudgeUnavailable if no key/SDK; premise-aware judge prompt
    judge = cj.make_anthropic_judge_fn(scenario_json=sj)
    res = stabilize(sj, paths, judge, k=args.k, workers=args.workers,
                    transcript_cap=args.cap)

    print(f"K={res['k']} samples/path, majority>={res['majority']}, "
          f"paths={res['paths']}, unique transcripts judged="
          f"{res['judged_transcripts']}{' (CAPPED)' if res['capped'] else ''}, "
          f"total judge calls={res['judged_transcripts'] * res['k']}, "
          f"sample errors={res['errors']}")
    print(f"\nSTABLE (majority-flagged — act on these): {res['stable_total']}")
    for r in sorted(res["stable"], key=lambda r: -r["flagged"]):
        print(f"   {str(r['choices']):16s} {r['flagged']}/{r['samples']} "
              f"{r['modal_severity']:5s} {r['outcome']:22s} :: {r['modal_scene'][:60]}")
    print(f"\nFLAKY (minority — variance, do NOT act): {len(res['flaky'])}")
    for r in sorted(res["flaky"], key=lambda r: -r["flagged"]):
        print(f"   {str(r['choices']):16s} {r['flagged']}/{r['samples']} "
              f"{r['modal_severity']:5s} {r['outcome']:22s} :: {r['modal_scene'][:60]}")
    print(f"\nCLEAN (never flagged): {res['clean']}")
    if res["skipped"]:
        print(f"SKIPPED (over --cap, not judged): {res['skipped']}")

    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
