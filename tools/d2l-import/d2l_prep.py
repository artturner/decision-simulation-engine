#!/usr/bin/env python
"""Convert app grade exports (videos, essays, scenarios) into D2L import CSVs.

Reads one export file, auto-detects which app produced it, matches student
names against the rosetta stone roster, and writes a D2L-ready import file:

    OrgDefinedId,Last Name,First Name,<Assignment Name> Points Grade,End-of-Line Indicator
    50387010,Akhigbe,Eliana,96,#

Matching order per name: exact (normalized) -> alias column -> fuzzy with
interactive confirmation.  Anything unmatched is reported, never guessed.
Students without a grade are left out of the output (D2L treats missing
rows as "no change").

Usage:
    python d2l_prep.py <export.csv> [--assignment NAME] [--rosetta PATH]
                       [--out PATH] [--total N] [--no-input] [--force]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from difflib import get_close_matches
from pathlib import Path

DEFAULT_ROSETTA = Path(
    r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\rosetta_stone.csv"
)

FUZZY_CUTOFF = 0.8


# ---------------------------------------------------------------------------
# Video grading — EDIT HERE when the video grading rule changes.
# ---------------------------------------------------------------------------
def video_grade(completed: str, first_try: int, total_questions: int) -> float | None:
    """75 base for completing, plus up to 25 for first-try accuracy.

    Returns None (no grade) unless completed == "yes".
    A video with no questions grades as a flat 75 for completion.
    """
    if completed.strip().lower() != "yes":
        return None
    if total_questions <= 0:
        return 75.0
    return 75 + 25 * first_try / total_questions


# ---------------------------------------------------------------------------
# Name normalization and matching
# ---------------------------------------------------------------------------
def norm(s: str) -> str:
    """Accent-fold, casefold, drop punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = re.sub(r"[-.']", " ", s)
    return " ".join(s.split())


def split_name(raw: str) -> str:
    """Return 'First Last' from either 'Last, First' or 'First Last' input.

    Also repairs exports where the first-name field mistakenly repeats the
    last name (e.g. 'Anguiano Bonsignore, Jalen Anguiano-Bonsignore').
    """
    raw = raw.strip()
    if "," in raw:
        last, first = (part.strip() for part in raw.split(",", 1))
        nf, nl = norm(first), norm(last)
        if nf != nl and nf.endswith(" " + nl):
            first = first[: len(first) - len(last)].strip(" ,-")
        return f"{first} {last}"
    return raw


class Roster:
    def __init__(self, path: Path):
        self.students: list[dict[str, str]] = []
        self.by_key: dict[str, dict[str, str] | None] = {}  # None = ambiguous
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if not (row.get("OrgDefinedId") or "").strip():
                    continue
                self.students.append(row)
                keys = [norm(f"{row['First Name']} {row['Last Name']}")]
                for alias in (row.get("Aliases") or "").split(";"):
                    if alias.strip():
                        keys.append(norm(f"{alias} {row['Last Name']}"))
                for key in keys:
                    if key in self.by_key and self.by_key[key] is not row:
                        print(f"  WARNING: ambiguous roster name '{key}' — "
                              "matches will be skipped for it", file=sys.stderr)
                        self.by_key[key] = None
                    else:
                        self.by_key[key] = row

    def match(self, raw_name: str, interactive: bool) -> tuple[dict | None, str]:
        """Return (roster row or None, note)."""
        key = norm(split_name(raw_name))
        if not key:
            return None, "blank name"
        hit = self.by_key.get(key)
        if hit is not None:
            return hit, "exact/alias"
        if key in self.by_key:
            return None, "ambiguous roster name"
        candidates = get_close_matches(key, self.by_key.keys(), n=1,
                                       cutoff=FUZZY_CUTOFF)
        if candidates:
            cand = self.by_key[candidates[0]]
            if cand is None:
                return None, "ambiguous roster name"
            full = f"{cand['First Name']} {cand['Last Name']}"
            if interactive:
                ans = input(f"  Fuzzy match: '{raw_name}' -> '{full}'? [y/N] ")
                if ans.strip().lower().startswith("y"):
                    print(f"    (consider adding an alias for {full} "
                          "in the rosetta stone)")
                    return cand, "fuzzy (confirmed)"
                return None, f"fuzzy match to '{full}' rejected"
            return None, f"possible match '{full}' (run without --no-input to confirm)"
        return None, "no match"


# ---------------------------------------------------------------------------
# Export readers — each yields (raw_name, grade) pairs.
#   grade is a str (pass-through), float (computed), or None (no grade).
# ---------------------------------------------------------------------------
def read_export(path: Path) -> list[dict[str, str]]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            with open(path, encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    sys.exit(f"Could not decode {path} as UTF-8 or Windows-1252.")


def detect_kind(fieldnames: list[str]) -> str:
    have = set(fieldnames)
    if {"student", "completed", "first_try_correct"} <= have:
        return "video"
    if {"student_name", "grade_total"} <= have:
        return "scenario"
    if {"student_name", "effective_total"} <= have:
        return "essay"
    sys.exit(
        "Unrecognized export format. Expected one of:\n"
        "  video    -> columns: student, completed, first_try_correct, ...\n"
        "  scenario -> columns: student_name, grade_total, ...  (teacher gradebook export)\n"
        "  essay    -> columns: student_name, effective_total, ...\n"
        f"Got columns: {', '.join(fieldnames)}"
    )


def extract_grades(kind: str, rows: list[dict], args) -> list[tuple[str, object]]:
    if kind == "video":
        total = args.total
        if total is None:
            derived = max((int(r.get("questions_answered") or 0) for r in rows),
                          default=0)
            if args.no_input:
                total = derived
                print(f"Total questions in video: {total} (derived)")
            else:
                ans = input(f"Total questions in this video [{derived}]: ").strip()
                total = int(ans) if ans else derived
        return [
            (r["student"],
             video_grade(r.get("completed") or "",
                         int(r.get("first_try_correct") or 0), total))
            for r in rows
        ]
    grade_col = {"scenario": "grade_total", "essay": "effective_total"}[kind]
    return [(r["student_name"], (r.get(grade_col) or "").strip() or None)
            for r in rows]


def fmt_grade(grade: object) -> str:
    if isinstance(grade, float):
        return f"{grade:.2f}".rstrip("0").rstrip(".")
    return str(grade)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", type=Path, help="grade export CSV from an app")
    ap.add_argument("--assignment", help="D2L grade item name (prompted if omitted)")
    ap.add_argument("--rosetta", type=Path, default=DEFAULT_ROSETTA,
                    help="rosetta stone roster CSV")
    ap.add_argument("--out", type=Path, help="output path (default: "
                    "<Assignment>_import.csv next to the export)")
    ap.add_argument("--total", type=int,
                    help="video only: total questions (default: derived)")
    ap.add_argument("--no-input", action="store_true",
                    help="never prompt; fuzzy matches are reported, not applied")
    ap.add_argument("--force", action="store_true",
                    help="overwrite the output file if it exists")
    args = ap.parse_args()

    if not args.export.exists():
        sys.exit(f"Export file not found: {args.export}")
    if not args.rosetta.exists():
        sys.exit(f"Rosetta stone not found: {args.rosetta}")

    rows = read_export(args.export)
    if not rows:
        sys.exit("Export file has no data rows.")
    kind = detect_kind(list(rows[0].keys()))
    print(f"Detected export type: {kind} ({len(rows)} rows)")

    assignment = args.assignment
    while not assignment:
        if args.no_input:
            sys.exit("--assignment is required with --no-input")
        assignment = input("Assignment name (exact D2L grade item name): ").strip()

    roster = Roster(args.rosetta)
    print(f"Roster: {len(roster.students)} students loaded")

    matched: list[tuple[dict, str]] = []      # (roster row, grade string)
    matched_no_grade: list[str] = []
    unmatched_graded: list[tuple[str, str, str]] = []   # name, grade, note
    unmatched_no_grade: list[tuple[str, str]] = []
    claimed: dict[str, str] = {}              # OrgDefinedId -> raw name

    for raw_name, grade in extract_grades(kind, rows, args):
        row, note = roster.match(raw_name, interactive=not args.no_input)
        if row is None:
            if grade is None:
                unmatched_no_grade.append((raw_name, note))
            else:
                unmatched_graded.append((raw_name, fmt_grade(grade), note))
            continue
        if grade is None:
            matched_no_grade.append(raw_name)
            continue
        org_id = row["OrgDefinedId"]
        if org_id in claimed:
            sys.exit(f"ERROR: both '{claimed[org_id]}' and '{raw_name}' matched "
                     f"{row['First Name']} {row['Last Name']} ({org_id}). "
                     "Fix the export or roster before importing.")
        claimed[org_id] = raw_name
        matched.append((row, fmt_grade(grade)))

    matched.sort(key=lambda m: (m[0]["Last Name"], m[0]["First Name"]))

    safe = re.sub(r"[^\w\- ]", "_", assignment).strip()
    out_path = args.out or args.export.parent / f"{safe}_import.csv"
    if out_path.exists() and not args.force:
        sys.exit(f"{out_path} already exists — use --force to overwrite.")

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["OrgDefinedId", "Last Name", "First Name",
                         f"{assignment} Points Grade", "End-of-Line Indicator"])
        for row, grade in matched:
            writer.writerow([row["OrgDefinedId"], row["Last Name"],
                             row["First Name"], grade, "#"])

    print(f"\nWrote {out_path}")
    print(f"  {len(matched)} students with grades")
    print(f"  {len(matched_no_grade)} matched students without a grade (omitted)")
    if unmatched_graded:
        print(f"\n  *** {len(unmatched_graded)} UNMATCHED names WITH grades "
              "(NOT in the import file): ***")
        for name, grade, note in unmatched_graded:
            print(f"      {name!r} (grade {grade}) — {note}")
        print("      Fix by adding an alias in the rosetta stone, then re-run.")
    if unmatched_no_grade:
        print(f"  {len(unmatched_no_grade)} unmatched names without grades "
              "(ignored):")
        for name, note in unmatched_no_grade:
            print(f"      {name!r} — {note}")


if __name__ == "__main__":
    main()
