#!/usr/bin/env python
"""Fetch every grade from all three apps and build one D2L all-grades import CSV.

Talks directly to the production APIs (scenarios, essays, video quizzes),
merges grades across classes, matches students against the rosetta stone,
and writes a wide import file whose columns mirror the D2L "all grades"
template:

    OrgDefinedId,Last Name,First Name,<item 1> Points Grade,...,End-of-Line Indicator

Blank cells are left blank — D2L skips them on import, so a partial run can
never wipe an existing grade.

Usage:
    python export_all_grades.py                # fetch everything, write the CSV
    python export_all_grades.py --check        # fetch + report, write nothing
    python export_all_grades.py --discover     # write assignments_map.csv from live titles
    python export_all_grades.py --source video # limit to one or more apps

Credentials live in .env next to this script (see .env.example). Grade rules
and name matching are imported from d2l_prep.py — edit them there.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from difflib import get_close_matches
from http.cookiejar import CookieJar
from pathlib import Path

from d2l_prep import DEFAULT_ROSETTA, Roster, fmt_grade, norm, split_name, video_grade

HERE = Path(__file__).resolve().parent

# Redirected output (scheduled runs logging to a file) must not crash on
# accented student names under the cp1252 default.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

SOURCES = ("scenario", "essay", "video")

CONFIG_DEFAULTS = {
    # Public by design (shipped in both frontend bundles; see the
    # supabase-keepalive workflow for the same values).
    "SUPABASE_URL": "https://ldtrukooegjbyrlopcfi.supabase.co",
    "SUPABASE_ANON_KEY": "sb_publishable_my65htwaG4yvpVkImjog9g_0lPErJQc",
    "SCENARIO_API_BASE": "https://decision-simulation-engine-production.up.railway.app",
    "ESSAY_API_BASE": "https://api-production-e92d.up.railway.app",
    "VIDEO_API_BASE": "https://videos.cruxlabs.academy",
    # Secrets — fill these in .env (never committed):
    "SUPABASE_TEACHER_EMAIL": "",
    "SUPABASE_TEACHER_PASSWORD": "",
    "VIDEO_TEACHER_EMAIL": "",
    "VIDEO_TEACHER_PASSWORD": "",
    # Fallback source for the video credentials when the two above are blank.
    "VIDEO_QUIZ_ENV": r"C:\Users\arttu\video-quiz\.env",
    # Semicolon-separated student names to skip silently (old/test students
    # still on an app class roll but not in the rosetta stone).
    "IGNORE_STUDENTS": "",
    "OUT_DIR": r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\grade-imports",
}

GRADE_SUFFIX = " Points Grade"
FIXED_LEAD = ["OrgDefinedId", "Last Name", "First Name"]
FIXED_TAIL = "End-of-Line Indicator"


# ---------------------------------------------------------------------------
# Config
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
    if not (cfg["VIDEO_TEACHER_EMAIL"] and cfg["VIDEO_TEACHER_PASSWORD"]):
        vq = parse_env_file(Path(cfg["VIDEO_QUIZ_ENV"]))
        cfg["VIDEO_TEACHER_EMAIL"] = cfg["VIDEO_TEACHER_EMAIL"] or vq.get("TEACHER_EMAIL", "")
        cfg["VIDEO_TEACHER_PASSWORD"] = cfg["VIDEO_TEACHER_PASSWORD"] or vq.get("TEACHER_PASSWORD", "")
    return cfg


# ---------------------------------------------------------------------------
# HTTP (stdlib only)
# ---------------------------------------------------------------------------
def request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: dict | None = None,
    opener: urllib.request.OpenerDirector | None = None,
    retries: int = 2,
) -> bytes:
    data = json.dumps(json_body).encode() if json_body is not None else None
    hdrs = dict(headers or {})
    if data is not None:
        hdrs.setdefault("Content-Type", "application/json")
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs)
        try:
            open_fn = opener.open if opener else urllib.request.urlopen
            with open_fn(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode(errors="replace")
            if e.code >= 500 and attempt < retries:
                last_err = e
            else:
                raise RuntimeError(f"HTTP {e.code} from {url}: {body}") from None
        except urllib.error.URLError as e:
            last_err = e
        if attempt < retries:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Could not reach {url}: {last_err}")


def get_json(url: str, **kw) -> object:
    return json.loads(request(url, **kw))


def get_csv_rows(url: str, **kw) -> list[dict[str, str]]:
    text = request(url, **kw).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


# ---------------------------------------------------------------------------
# Assignment titles
# ---------------------------------------------------------------------------
def norm_title(s: str) -> str:
    """Casefold and reduce to alphanumeric words — forgiving about the odd
    stray backtick or semicolon that crept into a D2L grade item name."""
    s = s.casefold().replace("&", " and ")
    s = re.sub(r"[^0-9a-z]+", " ", s)
    return " ".join(s.split())


class Merged:
    """Grades for one app assignment title, merged across classes."""

    def __init__(self, source: str, title: str):
        self.source = source
        self.title = title
        self.grades: dict[str, object] = {}  # raw student name -> grade
        self.conflicts: list[str] = []

    def add(self, name: str, grade: object) -> None:
        name = " ".join(name.split())
        if not name or grade is None or grade == "":
            return
        if name in self.grades and self.grades[name] != grade:
            keep = max((self.grades[name], grade), key=_as_float)
            self.conflicts.append(
                f"{name}: {self.grades[name]} vs {grade} -> kept {fmt_any(keep)}")
            self.grades[name] = keep
        else:
            self.grades[name] = grade


def _as_float(v: object) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("-inf")


def fmt_any(grade: object) -> str:
    return fmt_grade(grade) if isinstance(grade, float) else str(grade)


# ---------------------------------------------------------------------------
# Fetchers — each returns {norm_title: Merged}
# ---------------------------------------------------------------------------
def supabase_token(cfg: dict[str, str]) -> str:
    email = cfg["SUPABASE_TEACHER_EMAIL"]
    password = cfg["SUPABASE_TEACHER_PASSWORD"]
    if not (email and password):
        raise RuntimeError(
            "SUPABASE_TEACHER_EMAIL / SUPABASE_TEACHER_PASSWORD not set — "
            f"add them to {HERE / '.env'} (your scenarios/essays teacher login)")
    out = get_json(
        f"{cfg['SUPABASE_URL']}/auth/v1/token?grant_type=password",
        headers={"apikey": cfg["SUPABASE_ANON_KEY"]},
        json_body={"email": email, "password": password},
    )
    return out["access_token"]  # type: ignore[index]


def fetch_scenario(cfg: dict[str, str], token: str) -> dict[str, Merged]:
    base = cfg["SCENARIO_API_BASE"]
    auth = {"Authorization": f"Bearer {token}"}
    merged: dict[str, Merged] = {}
    for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
        for sc in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/scenarios",
                           headers=auth):
            rows = get_csv_rows(
                f"{base}/api/v1/teacher/rolls/{roll['id']}"
                f"/scenarios/{sc['scenario_id']}/gradebook.csv", headers=auth)
            m = merged.setdefault(norm_title(sc["title"]),
                                  Merged("scenario", sc["title"]))
            for r in rows:
                m.add(r.get("student_name", ""), (r.get("grade_total") or "").strip() or None)
    return merged


def fetch_essay(cfg: dict[str, str], token: str) -> dict[str, Merged]:
    base = cfg["ESSAY_API_BASE"]
    auth = {"Authorization": f"Bearer {token}"}
    merged: dict[str, Merged] = {}
    for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
        for a in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/assignments",
                          headers=auth):
            rows = get_csv_rows(
                f"{base}/api/v1/teacher/rolls/{roll['id']}"
                f"/assignments/{a['assignment_id']}/gradebook.csv", headers=auth)
            m = merged.setdefault(norm_title(a["title"]),
                                  Merged("essay", a["title"]))
            for r in rows:
                m.add(r.get("student_name", ""),
                      (r.get("effective_total") or "").strip() or None)
    return merged


def video_opener(cfg: dict[str, str]) -> urllib.request.OpenerDirector:
    email = cfg["VIDEO_TEACHER_EMAIL"]
    password = cfg["VIDEO_TEACHER_PASSWORD"]
    if not (email and password):
        raise RuntimeError(
            "Video credentials not found — set VIDEO_TEACHER_EMAIL / "
            f"VIDEO_TEACHER_PASSWORD in {HERE / '.env'} (or point "
            "VIDEO_QUIZ_ENV at the video-quiz repo's .env)")
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar()))
    request(f"{cfg['VIDEO_API_BASE']}/api/admin/login",
            json_body={"email": email, "password": password}, opener=opener)
    return opener


def fetch_video(cfg: dict[str, str]) -> dict[str, Merged]:
    base = cfg["VIDEO_API_BASE"]
    opener = video_opener(cfg)
    merged: dict[str, Merged] = {}
    for a in get_json(f"{base}/api/admin/assignments", opener=opener):
        if not a.get("className"):  # unassigned to a class -> the report 400s
            continue
        rows = get_csv_rows(
            f"{base}/api/admin/reports/assignments/{a['id']}?format=csv",
            opener=opener)
        m = merged.setdefault(norm_title(a["videoTitle"]),
                              Merged("video", a["videoTitle"]))
        for r in rows:
            grade = video_grade(r.get("status") or "",
                                int(r.get("first_try_correct") or 0),
                                int(r.get("total_questions") or 0))
            m.add(r.get("student_name", ""), grade)
    return merged


def fetch_titles_only(cfg: dict[str, str], sources: list[str]) -> dict[str, list[str]]:
    """Just the live assignment titles per source (for --discover)."""
    titles: dict[str, list[str]] = {}
    token = None
    if "scenario" in sources or "essay" in sources:
        token = supabase_token(cfg)
        auth = {"Authorization": f"Bearer {token}"}
    if "scenario" in sources:
        base, seen = cfg["SCENARIO_API_BASE"], {}
        for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
            for sc in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/scenarios",
                               headers=auth):
                seen[norm_title(sc["title"])] = sc["title"]
        titles["scenario"] = sorted(seen.values())
    if "essay" in sources:
        base, seen = cfg["ESSAY_API_BASE"], {}
        for roll in get_json(f"{base}/api/v1/teacher/rolls", headers=auth):
            for a in get_json(f"{base}/api/v1/teacher/rolls/{roll['id']}/assignments",
                              headers=auth):
                seen[norm_title(a["title"])] = a["title"]
        titles["essay"] = sorted(seen.values())
    if "video" in sources:
        base, seen = cfg["VIDEO_API_BASE"], {}
        opener = video_opener(cfg)
        for a in get_json(f"{base}/api/admin/assignments", opener=opener):
            if a.get("className"):
                seen[norm_title(a["videoTitle"])] = a["videoTitle"]
        titles["video"] = sorted(seen.values())
    return titles


# ---------------------------------------------------------------------------
# Template + mapping
# ---------------------------------------------------------------------------
def read_template_items(path: Path) -> list[str]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    items = []
    for col in header:
        if col in FIXED_LEAD or col == FIXED_TAIL or not col.strip():
            continue
        if not col.endswith(GRADE_SUFFIX):
            sys.exit(f"Template column {col!r} does not end with '{GRADE_SUFFIX}' — "
                     "is this really the D2L all-grades template?")
        items.append(col[: -len(GRADE_SUFFIX)])
    if not items:
        sys.exit(f"No grade columns found in template {path}")
    return items


def read_map(path: Path) -> dict[str, list[tuple[str, str]]]:
    """d2l_item -> [(source, app_title)]; empty app_title = leave column blank."""
    mapping: dict[str, list[tuple[str, str]]] = {}
    if not path.exists():
        return mapping
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = (row.get("d2l_item") or "").strip()
            if item:
                mapping.setdefault(item, []).append(
                    ((row.get("source") or "").strip(),
                     (row.get("app_title") or "").strip()))
    return mapping


def resolve_columns(
    items: list[str],
    mapping: dict[str, list[tuple[str, str]]],
    fetched: dict[str, dict[str, Merged]],
) -> tuple[dict[str, list[Merged]], list[str], list[str]]:
    """Attach app data to each template item.

    Explicit map rows win; otherwise a normalized-title match against every
    fetched source. Returns (item -> contributors, unmatched items,
    ambiguity/problem notes).
    """
    columns: dict[str, list[Merged]] = {}
    unmatched: list[str] = []
    notes: list[str] = []
    for item in items:
        contributors: list[Merged] = []
        if item in mapping:
            for source, app_title in mapping[item]:
                if not app_title:
                    continue  # explicit "leave blank"
                pool = fetched.get(source)
                if pool is None:
                    continue  # source not fetched this run
                m = pool.get(norm_title(app_title))
                if m:
                    contributors.append(m)
                else:
                    notes.append(f"map row for {item!r}: no {source} assignment "
                                 f"titled {app_title!r} was found")
        else:
            hits = [pool[key] for pool in fetched.values()
                    if (key := norm_title(item)) in pool]
            if len(hits) > 1:
                notes.append(f"{item!r} matches assignments in multiple sources "
                             f"({', '.join(h.source for h in hits)}) — add explicit "
                             "rows to assignments_map.csv")
            else:
                contributors = hits
        if contributors:
            columns[item] = contributors
        else:
            unmatched.append(item)
    return columns, unmatched, notes


def suggest(item: str, fetched: dict[str, dict[str, Merged]]) -> str:
    all_titles = {key: m for pool in fetched.values() for key, m in pool.items()}
    close = get_close_matches(norm_title(item), all_titles.keys(), n=1, cutoff=0.6)
    if close:
        m = all_titles[close[0]]
        return f" (closest live title: {m.source} {m.title!r})"
    return ""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def build_rows(
    items: list[str],
    columns: dict[str, list[Merged]],
    roster: Roster,
    ignored: frozenset[str] = frozenset(),
) -> tuple[list[list[str]], dict[str, set[str]], int, dict[str, int]]:
    """Returns (csv rows, unmatched name -> assignments, graded-cell count,
    ignored name -> skipped-grade count)."""
    match_cache: dict[str, dict | None] = {}
    unmatched: dict[str, set[str]] = {}
    skipped: dict[str, int] = {}
    per_student: dict[str, dict[str, object]] = {}  # org id -> item -> grade

    for item in items:
        for m in columns.get(item, []):
            for raw_name, grade in m.grades.items():
                if norm(split_name(raw_name)) in ignored:
                    skipped[raw_name] = skipped.get(raw_name, 0) + 1
                    continue
                if raw_name not in match_cache:
                    match_cache[raw_name] = roster.match(raw_name, interactive=False)[0]
                row = match_cache[raw_name]
                if row is None:
                    unmatched.setdefault(raw_name, set()).add(f"{m.source}: {m.title}")
                    continue
                cell = per_student.setdefault(row["OrgDefinedId"], {})
                if item in cell and cell[item] != grade:
                    grade = max((cell[item], grade), key=_as_float)
                cell[item] = grade

    by_id = {r["OrgDefinedId"]: r for r in roster.students}
    rows: list[list[str]] = []
    cells = 0
    for org_id in sorted(per_student,
                         key=lambda i: (by_id[i]["Last Name"], by_id[i]["First Name"])):
        student = by_id[org_id]
        grades = per_student[org_id]
        cells += len(grades)
        rows.append(
            [org_id, student["Last Name"], student["First Name"]]
            + [fmt_any(grades[i]) if i in grades else "" for i in items]
            + ["#"])
    return rows, unmatched, cells, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="fetch and report; write nothing")
    ap.add_argument("--discover", action="store_true",
                    help="write assignments_map.csv from live app titles")
    ap.add_argument("--source", default="scenario,essay,video",
                    help="comma-separated subset of: scenario,essay,video")
    ap.add_argument("--allow-partial", action="store_true",
                    help="still write the CSV if a source fails to fetch")
    ap.add_argument("--template", type=Path,
                    default=HERE / "all_grade_import_template.csv")
    ap.add_argument("--map", type=Path, default=HERE / "assignments_map.csv")
    ap.add_argument("--rosetta", type=Path, default=DEFAULT_ROSETTA)
    ap.add_argument("--env", type=Path, default=HERE / ".env")
    ap.add_argument("--out", type=Path, help="output file (default: "
                    "OUT_DIR/all_grades_import_<date>.csv)")
    args = ap.parse_args()

    sources = [s.strip() for s in args.source.split(",") if s.strip()]
    for s in sources:
        if s not in SOURCES:
            sys.exit(f"Unknown source {s!r} (expected: {', '.join(SOURCES)})")

    cfg = load_config(args.env)
    items = read_template_items(args.template)
    print(f"Template: {len(items)} grade items ({args.template.name})")

    if args.discover:
        titles = fetch_titles_only(cfg, sources)
        existing = read_map(args.map)
        by_norm = {norm_title(t): (src, t)
                   for src, ts in titles.items() for t in ts}
        with open(args.map, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["d2l_item", "source", "app_title"])
            for item in items:
                if item in existing:  # keep manual rows
                    for source, app_title in existing[item]:
                        w.writerow([item, source, app_title])
                elif norm_title(item) in by_norm:
                    w.writerow([item, *by_norm[norm_title(item)]])
                else:
                    w.writerow([item, "", ""])
        auto = sum(1 for i in items if i not in existing and norm_title(i) in by_norm)
        blank = sum(1 for i in items if i not in existing and norm_title(i) not in by_norm)
        print(f"Wrote {args.map}: {auto} auto-matched, "
              f"{len(items) - auto - blank} kept from existing map, {blank} unmatched "
              "(blank source/app_title rows — fill in or leave to skip)")
        claimed = {norm_title(i) for i in items} | {
            norm_title(t) for rows in existing.values() for _, t in rows if t}
        for src, ts in titles.items():
            extras = [t for t in ts if norm_title(t) not in claimed]
            if extras:
                print(f"  {src} assignments with no template column: "
                      + "; ".join(extras))
        return

    fetched: dict[str, dict[str, Merged]] = {}
    errors: dict[str, str] = {}
    token = None
    for source in sources:
        try:
            if source in ("scenario", "essay"):
                token = token or supabase_token(cfg)
                fetched[source] = (fetch_scenario if source == "scenario"
                                   else fetch_essay)(cfg, token)
            else:
                fetched[source] = fetch_video(cfg)
            n_assign = len(fetched[source])
            n_grades = sum(len(m.grades) for m in fetched[source].values())
            print(f"{source}: {n_assign} assignments, {n_grades} grades")
        except Exception as e:  # keep going; decide below whether to write
            errors[source] = str(e)
            print(f"{source}: FAILED — {e}", file=sys.stderr)

    mapping = read_map(args.map)
    columns, unmatched_items, notes = resolve_columns(items, mapping, fetched)

    roster = Roster(args.rosetta)
    ignored = frozenset(norm(split_name(n)) for n in
                        cfg["IGNORE_STUDENTS"].split(";") if n.strip())
    rows, unmatched_names, cells, skipped = build_rows(items, columns, roster,
                                                       ignored)

    print(f"\n{len(columns)} of {len(items)} template columns have data; "
          f"{len(rows)} students, {cells} grade cells")
    if unmatched_items:
        print(f"\nColumns with no data this run ({len(unmatched_items)}):")
        for item in unmatched_items:
            print(f"  {item}{suggest(item, fetched)}")
    for note in notes:
        print(f"  NOTE: {note}")
    conflict_notes = [f"{m.source} {m.title!r} — {c}"
                      for pool in fetched.values() for m in pool.values()
                      for c in m.conflicts]
    if conflict_notes:
        print("\nSame student graded differently in two classes (kept the best):")
        for c in conflict_notes:
            print(f"  {c}")
    if skipped:
        print(f"\nIgnored students skipped (IGNORE_STUDENTS): "
              + ", ".join(f"{n} ({c} grades)" for n, c in sorted(skipped.items())))
    if unmatched_names:
        print(f"\n*** {len(unmatched_names)} student names NOT in the rosetta stone "
              "(their grades are NOT in the file): ***")
        for name in sorted(unmatched_names):
            print(f"  {name!r} — {', '.join(sorted(unmatched_names[name]))}")
        print("  Fix by adding aliases to the rosetta stone, then re-run.")

    if args.check:
        print("\n--check: nothing written.")
        return
    if errors and not args.allow_partial and set(sources) - set(errors):
        sys.exit(f"\nNot writing the CSV — {', '.join(errors)} failed to fetch "
                 "(re-run with --allow-partial to write anyway; blank cells "
                 "never overwrite grades in D2L).")
    if errors and set(errors) == set(sources):
        sys.exit("\nEvery source failed — nothing to write.")

    out = args.out
    if out is None:
        out_dir = Path(cfg["OUT_DIR"])
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / f"all_grades_import_{date.today().isoformat()}.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(FIXED_LEAD + [f"{i}{GRADE_SUFFIX}" for i in items] + [FIXED_TAIL])
        w.writerows(rows)
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
