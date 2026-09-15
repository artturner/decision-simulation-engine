#!/usr/bin/env python
"""Grade stored-but-ungraded scenario reflections through the production API.

When AI grading is unavailable (no API key, or the teacher's monthly quota is
exhausted) the reflection form silently falls back to plain submission: the
student's answers are stored, but no grade or coaching is ever produced.  This
tool finds those ungraded reflections in every class gradebook and re-submits
the stored answers to the public grade endpoint, so they are graded exactly as
if the student had submitted while grading was up.  Grades land in the
gradebook as attempt 1; students can still revise and accept as usual.

Usage:
    python backfill_reflection_grades.py                 # dry run: list candidates
    python backfill_reflection_grades.py --apply         # grade them (~1 cent/call)
    python backfill_reflection_grades.py --since 2026-09-01
    python backfill_reflection_grades.py --roll "2305" --scenario "Whistle"

Credentials come from the d2l-import tool's .env (SUPABASE_TEACHER_EMAIL /
SUPABASE_TEACHER_PASSWORD) — the same teacher login the grade exporter uses.
Each grading call is counted against the monthly AI grading quota.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

CONFIG_DEFAULTS = {
    # Public by design (shipped in the frontend bundle).
    "SUPABASE_URL": "https://ldtrukooegjbyrlopcfi.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_my65htwaG4yvpVkImjog9g_0lPErJQc",
    "SCENARIO_API_BASE": "https://decision-simulation-engine-production.up.railway.app",
    # Secrets — set in the .env passed via --env:
    "SUPABASE_TEACHER_EMAIL": "",
    "SUPABASE_TEACHER_PASSWORD": "",
}

# The public grade endpoint allows 10 calls per 60 s per IP; stay under it.
SECONDS_BETWEEN_CALLS = 6.5


# ---------------------------------------------------------------------------
# Config + HTTP (stdlib only)
# ---------------------------------------------------------------------------
def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal KEY=VALUE .env parser (no interpolation, strips quotes)."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("'\"")
    return values


def load_config(env_path: Path) -> dict[str, str]:
    cfg = dict(CONFIG_DEFAULTS)
    cfg.update({k: v for k, v in parse_env_file(env_path).items() if k in cfg})
    if not (cfg["SUPABASE_TEACHER_EMAIL"] and cfg["SUPABASE_TEACHER_PASSWORD"]):
        sys.exit(
            "SUPABASE_TEACHER_EMAIL / SUPABASE_TEACHER_PASSWORD not set — "
            f"add them to {env_path} (your scenarios teacher login)"
        )
    return cfg


def http(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
) -> tuple[int, object]:
    """Return (status, parsed JSON body); never raises on HTTP error codes."""
    data = json.dumps(json_body).encode() if json_body is not None else None
    hdrs = dict(headers or {})
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw[:300].decode(errors="replace")}
        return e.code, body
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e}") from None


def get_json(url: str, headers: dict[str, str]) -> object:
    status, body = http(url, headers=headers)
    if status != 200:
        raise RuntimeError(f"HTTP {status} from {url}: {body}")
    return body


def supabase_token(cfg: dict[str, str]) -> str:
    status, out = http(
        f"{cfg['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": cfg["SUPABASE_ANON_KEY"]},
        json_body={
            "email": cfg["SUPABASE_TEACHER_EMAIL"],
            "password": cfg["SUPABASE_TEACHER_PASSWORD"],
        },
    )
    if status != 200:
        raise RuntimeError(f"Supabase login failed (HTTP {status}): {out}")
    return out["access_token"]  # type: ignore[index]


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    roll_name: str
    scenario_title: str
    student_name: str
    play_id: str
    submitted_at: str | None
    responses: dict[str, str]

    @property
    def answered(self) -> int:
        return sum(1 for v in self.responses.values() if str(v).strip())


def find_candidates(
    cfg: dict[str, str],
    token: str,
    *,
    roll_filter: str,
    scenario_filter: str,
    since: date | None,
) -> tuple[list[Candidate], int]:
    """Return (candidates, unmatched_play_count).

    A candidate is a completed play whose reflection was stored without ever
    being graded (no grading attempts, not accepted, at least one non-blank
    answer).  Unmatched plays (student renamed after playing) can't be
    backfilled from the gradebook payload and are only counted.
    """
    base = cfg["SCENARIO_API_BASE"]
    auth = {"Authorization": f"Bearer {token}"}
    candidates: list[Candidate] = []
    unmatched = 0

    for roll in get_json(f"{base}/api/v1/teacher/rolls", auth):
        if roll_filter and roll_filter.lower() not in roll["name"].lower():
            continue
        for sc in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/scenarios", auth):
            if scenario_filter and scenario_filter.lower() not in sc["title"].lower():
                continue
            gradebook = get_json(
                f"{base}/api/v1/teacher/rolls/{roll['id']}"
                f"/scenarios/{sc['scenario_id']}/gradebook",
                auth,
            )
            unmatched += sum(
                1 for p in gradebook.get("unmatched", []) if p["completed"]
            )
            for student in gradebook["students"]:
                for attempt in student["attempts"]:
                    r = attempt.get("reflection")
                    if (
                        not attempt["completed"]
                        or r is None
                        or r.get("graded_at") is not None
                        or (r.get("attempts_used") or 0) > 0
                        or r.get("accepted")
                        or not any(str(v).strip() for v in r["responses"].values())
                    ):
                        continue
                    submitted = r.get("submitted_at") or attempt.get("ended_at")
                    if since and submitted and _as_date(submitted) < since:
                        continue
                    candidates.append(
                        Candidate(
                            roll_name=roll["name"],
                            scenario_title=sc["title"],
                            student_name=r.get("student_name")
                            or student["student_name"],
                            play_id=str(attempt["play_id"]),
                            submitted_at=submitted,
                            responses=r["responses"],
                        )
                    )
    return candidates, unmatched


def _as_date(iso: str) -> date:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------
def grade(cfg: dict[str, str], c: Candidate) -> tuple[str, str]:
    """POST the stored answers to the grade endpoint. Returns (status, note)."""
    status, body = http(
        f"{cfg['SCENARIO_API_BASE']}/api/v1/public/plays/{c.play_id}"
        "/reflection/grade",
        json_body={"responses": c.responses, "student_name": c.student_name},
    )
    detail = body.get("detail", "") if isinstance(body, dict) else ""
    if status == 200:
        return "graded", f"{body['grade_total']}/100"
    if status == 409:
        return "skipped", "already accepted"
    if status == 503:
        return "abort", f"grading unavailable — {detail}"
    return "failed", f"HTTP {status}: {detail}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="actually grade (default is a dry run)")
    ap.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD",
                    help="only reflections submitted on/after this date")
    ap.add_argument("--roll", default="",
                    help="only class rolls whose name contains this text")
    ap.add_argument("--scenario", default="",
                    help="only scenarios whose title contains this text")
    ap.add_argument("--limit", type=int, default=0,
                    help="grade at most N reflections this run (0 = no cap)")
    ap.add_argument("--env", type=Path,
                    default=HERE.parent / "d2l-import" / ".env",
                    help="path to the .env holding the teacher login")
    args = ap.parse_args()

    cfg = load_config(args.env)
    token = supabase_token(cfg)
    candidates, unmatched = find_candidates(
        cfg, token,
        roll_filter=args.roll,
        scenario_filter=args.scenario,
        since=args.since,
    )

    if unmatched:
        print(f"NOTE: {unmatched} completed unmatched play(s) skipped — restore "
              "the old roster spelling to re-link them, then re-run.\n")
    if not candidates:
        print("No ungraded reflections found.")
        return

    candidates.sort(key=lambda c: (c.roll_name, c.scenario_title, c.student_name))
    width = max(len(c.student_name) for c in candidates)
    print(f"{len(candidates)} ungraded reflection(s):\n")
    for c in candidates:
        when = c.submitted_at[:10] if c.submitted_at else "?"
        print(f"  {c.student_name:<{width}}  {when}  {c.answered} answer(s)  "
              f"{c.roll_name} — {c.scenario_title}")

    if args.limit and len(candidates) > args.limit:
        candidates = candidates[: args.limit]
        print(f"\n--limit: only the first {args.limit} will be graded.")

    if not args.apply:
        print(f"\nDry run — nothing graded. Re-run with --apply to grade "
              f"{len(candidates)} reflection(s) (~{len(candidates)} grading "
              "calls, about 1 cent each).")
        return

    print(f"\nGrading {len(candidates)} reflection(s), one every "
          f"{SECONDS_BETWEEN_CALLS:g}s to respect the rate limit…\n")
    counts = {"graded": 0, "skipped": 0, "failed": 0}
    for i, c in enumerate(candidates):
        if i:
            time.sleep(SECONDS_BETWEEN_CALLS)
        outcome, note = grade(cfg, c)
        if outcome == "abort":
            print(f"  {c.student_name}: ABORTING — {note}")
            print(f"\nStopped after {sum(counts.values())} of {len(candidates)}. "
                  "Check the AI grading quota/config and re-run; already-graded "
                  "reflections are filtered out automatically.")
            sys.exit(1)
        counts[outcome] += 1
        print(f"  {c.student_name:<{width}}  {outcome}: {note}  "
              f"({c.roll_name} — {c.scenario_title})")

    print(f"\nDone: {counts['graded']} graded, {counts['skipped']} skipped, "
          f"{counts['failed']} failed.")
    if counts["failed"]:
        print("Failed ones were left ungraded — re-running only retries those.")


if __name__ == "__main__":
    main()
