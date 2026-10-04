#!/usr/bin/env python
"""One-page grade/progress report for a single student, as a PDF.

For FERPA-approved requesters (admin, counselors): current grade, every
graded assignment, progress by type and overall on the 60 course items,
and whether the student is ahead of / on / behind the pacing-guide dates.

Data comes from the newest all-grades import CSV that export_all_grades.py
writes (the same numbers that go into D2L); --refresh runs a live export
first. Roster/campus/period come from the rosetta stone.

Usage:
    python student_report.py                    # search + pick interactively
    python student_report.py --student garcia   # pre-filter by name
    python student_report.py --refresh          # pull live grades first
    python student_report.py --as-of 2026-10-02 # judge pace as of a date

Output: OneDrive 2026 Fall/student-reports/<Last>_<First>_<date>.pdf
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "d2l-import"
sys.path.insert(0, str(TOOLS))

from d2l_prep import DEFAULT_ROSETTA  # noqa: E402
from export_all_grades import GRADE_SUFFIX, read_template_items  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

GRADES_DIR = Path(r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\grade-imports")
OUT_DIR = Path(r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\student-reports")

# The course plan (items, pacing-guide target dates, weights) is shared with
# the live student dashboard in the scenarios API — edit it there, not here.
PLAN_PATH = HERE.parent.parent / "services" / "api" / "app" / "data" / "course_plan_fall2026.json"
PLAN = json.loads(PLAN_PATH.read_text(encoding="utf-8"))

WEIGHTS = PLAN["weights"]  # syllabus
TYPE_LABEL = PLAN["type_labels"]
SECTION = {"SGPHS": "G4E · CRN 82811 · South Grand Prairie HS",
           "GPHS": "GGE · CRN 84049 · Grand Prairie HS"}
AHEAD_MIN = PLAN["pace"]["ahead_min_early"]      # items finished early to count as "ahead"
SLIGHTLY_MAX = PLAN["pace"]["slightly_behind_max"]  # past-due missing items still "slightly behind"

Y = 2026
# (D2L grade item, display title, type, chapter, unit, (month, day) target)
ITEMS = [
    (i["d2l_item"], i["title"], i["type"], i["chapter"] or 0, i["unit"],
     (int(i["target"][5:7]), int(i["target"][8:10])))
    for i in PLAN["items"]
]
FLEXIBLE = {i["d2l_item"] for i in PLAN["items"] if i["flexible"]}  # no set date
UNIT_NAMES = {int(k): v for k, v in PLAN["units"].items()}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def letter(pct: float) -> str:
    return "A" if pct >= 90 else "B" if pct >= 80 else "C" if pct >= 70 else "D" if pct >= 60 else "F"


def fmt_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def fmt_pct(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def check_items_against_template() -> None:
    template = read_template_items(TOOLS / "all_grade_import_template.csv")
    ours = [i[0] for i in ITEMS]
    missing, extra = set(template) - set(ours), set(ours) - set(template)
    if missing or extra:
        sys.exit("ITEMS is out of sync with the D2L template.\n"
                 f"  in template, not in ITEMS: {sorted(missing)}\n"
                 f"  in ITEMS, not in template: {sorted(extra)}\n"
                 "Update ITEMS in student_report.py (title, type, unit, target date).")


def newest_grades_csv() -> Path:
    files = sorted(GRADES_DIR.glob("all_grades_import_*.csv"))
    if not files:
        sys.exit(f"No all_grades_import_*.csv in {GRADES_DIR} — run with --refresh.")
    return files[-1]


def load_grades(path: Path) -> dict[str, dict[str, float]]:
    """OrgDefinedId -> {D2L item -> grade}."""
    out: dict[str, dict[str, float]] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            grades = {}
            for col, val in row.items():
                if col and col.endswith(GRADE_SUFFIX) and (val or "").strip():
                    grades[col[: -len(GRADE_SUFFIX)]] = float(val)
            out[row["OrgDefinedId"]] = grades
    return out


def load_roster() -> list[dict[str, str]]:
    with open(DEFAULT_ROSETTA, encoding="utf-8-sig", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("OrgDefinedId") or "").strip()]


def pick_student(roster: list[dict[str, str]], query: str | None) -> dict[str, str]:
    def label(r):
        per = r.get("Period") or "?"
        return f"{r['Last Name']}, {r['First Name']}  ({r.get('Campus') or '?'} · P{per})"

    while True:
        q = (query or input("Student name (part of first or last; blank = list all): ")).strip().lower()
        query = None
        hits = [r for r in roster
                if not q or q in f"{r['First Name']} {r['Last Name']} {r.get('Aliases', '')}".lower()]
        hits.sort(key=lambda r: (r["Last Name"].lower(), r["First Name"].lower()))
        if not hits:
            print("  no match — try again")
            continue
        if len(hits) == 1:
            print(f"  -> {label(hits[0])}")
            return hits[0]
        for n, r in enumerate(hits, 1):
            print(f"  {n:3}. {label(r)}")
        choice = input("Number (or Enter to search again): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(hits):
            return hits[int(choice) - 1]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def analyze(grades: dict[str, float], as_of: date) -> dict:
    rows = []
    for item, title, typ, ch, unit, (m, d) in ITEMS:
        due = date(Y, m, d)
        g = grades.get(item)
        if g is not None:
            state = "early" if due > as_of else "done"
        else:
            state = "missing" if due < as_of else "upcoming"
        rows.append({"item": item, "title": title, "type": typ, "ch": ch, "unit": unit,
                     "due": due, "grade": g, "state": state})

    by_type = {}
    for typ in WEIGHTS:
        rs = [r for r in rows if r["type"] == typ]
        graded = [r["grade"] for r in rs if r["grade"] is not None]
        counted = [r["grade"] or 0.0 for r in rs if r["grade"] is not None or r["state"] == "missing"]
        by_type[typ] = {
            "total": len(rs),
            "done": len(graded),
            "due": sum(1 for r in rs if r["due"] < as_of),
            "missing": sum(1 for r in rs if r["state"] == "missing"),
            "avg_submitted": sum(graded) / len(graded) if graded else None,
            "avg_counted": sum(counted) / len(counted) if counted else None,
        }

    def weighted(key):
        parts = [(WEIGHTS[t], v[key]) for t, v in by_type.items() if v[key] is not None]
        wsum = sum(w for w, _ in parts)
        return sum(w * a for w, a in parts) / wsum if wsum else None

    missing = [r for r in rows if r["state"] == "missing"]
    early = [r for r in rows if r["state"] == "early"]
    if missing:
        pace = ("slight", "Slightly behind") if len(missing) <= SLIGHTLY_MAX else ("behind", "Behind")
    elif len(early) >= AHEAD_MIN:
        pace = ("ahead", "Ahead of schedule")
    else:
        pace = ("ok", "On track")
    return {"rows": rows, "by_type": by_type, "missing": missing, "early": early,
            "grade": weighted("avg_counted"), "grade_submitted": weighted("avg_submitted"),
            "pace": pace, "due_count": sum(1 for r in rows if r["due"] < as_of),
            "done_count": sum(1 for r in rows if r["grade"] is not None)}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
CSS = """
*{-webkit-print-color-adjust:exact;print-color-adjust:exact;box-sizing:border-box}
@page{size:letter;margin:0}
html,body{margin:0;background:#fff}
body{font:10.5px/1.3 'Segoe UI',Arial,sans-serif;color:#1f2328}
.page{width:8.5in;height:11in;padding:.42in .5in .35in;overflow:hidden;position:relative}
.ferpa{background:#f6f1e7;border:1px solid #d9c9a8;color:#6b4e16;font-size:8.6px;padding:3px 8px;
 border-radius:4px;text-align:center;letter-spacing:.01em}
.head{display:flex;justify-content:space-between;align-items:flex-end;margin:10px 0 2px;
 border-bottom:2px solid #1f3a5f;padding-bottom:6px}
.head h1{font-size:21px;margin:0;color:#1f3a5f;letter-spacing:-.01em}
.head .course{font-size:10px;color:#57606a;margin-top:2px}
.head .meta{text-align:right;font-size:9.5px;color:#57606a;line-height:1.45}
.head .meta b{color:#1f2328}
.tiles{display:grid;grid-template-columns:1.15fr 1.25fr 1fr 1fr;gap:8px;margin:10px 0 8px}
.tile{border:1px solid #d8dee4;border-radius:6px;padding:6px 10px}
.tile .k{font-size:8.5px;text-transform:uppercase;letter-spacing:.06em;color:#57606a}
.tile .v{font-size:22px;font-weight:700;line-height:1.15}
.tile .s{font-size:9px;color:#57606a}
.pace-ok .v,.pace-ahead .v{color:#1a7f37}.pace-slight .v{color:#9a6700}.pace-behind .v{color:#b42318}
.pace-ok{border-left:4px solid #1a7f37}.pace-ahead{border-left:4px solid #1a7f37}
.pace-slight{border-left:4px solid #d4a72c}.pace-behind{border-left:4px solid #b42318}
h2{font-size:9.5px;text-transform:uppercase;letter-spacing:.07em;color:#1f3a5f;margin:8px 0 4px;
 border-bottom:1px solid #d8dee4;padding-bottom:2px}
table.types{width:100%;border-collapse:collapse;font-size:10px}
table.types th{font-size:8.5px;text-transform:uppercase;letter-spacing:.04em;color:#57606a;
 font-weight:600;text-align:left;padding:2px 6px}
table.types td{padding:3px 6px;border-top:1px solid #eef1f4;vertical-align:middle}
table.types td.n{text-align:right;white-space:nowrap}
table.types tr.total td{border-top:1.5px solid #afb8c1;font-weight:700}
.bar{position:relative;height:9px;background:#eef1f4;border-radius:5px;width:100%;min-width:150px}
.bar .fill{position:absolute;left:0;top:0;bottom:0;background:#2f6fb3;border-radius:5px}
.bar .mark{position:absolute;top:-3px;bottom:-3px;width:2px;background:#1f2328}
.legend{font-size:8.5px;color:#57606a;margin-top:3px}
.legend i{display:inline-block;width:2px;height:9px;background:#1f2328;vertical-align:-1px;margin:0 3px 0 0}
.missing-box{background:#fdf0ef;border:1px solid #f1c4c0;border-radius:5px;padding:4px 9px;
 margin:6px 0 2px;font-size:9.5px;color:#7a1f16}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:0 18px}
.unit{font-size:8.8px;font-weight:700;color:#1f3a5f;margin:5px 0 1px;text-transform:uppercase;
 letter-spacing:.04em}
.unit span{font-weight:400;color:#57606a;text-transform:none;letter-spacing:0}
table.items{width:100%;border-collapse:collapse;font-size:9.4px}
table.items td{padding:1.4px 3px;border-top:1px solid #f0f2f4;white-space:nowrap}
table.items td.t{width:100%;overflow:hidden;text-overflow:ellipsis;max-width:0}
table.items td.ty{color:#8c959f;font-size:8px;text-transform:uppercase;letter-spacing:.03em}
table.items td.d{color:#57606a;text-align:right}
table.items td.g{text-align:right;width:52px;font-weight:600}
tr.frq td.t{font-weight:600}
.st-missing td.g{color:#b42318}.st-missing td.t{color:#b42318}
.st-upcoming td{color:#8c959f}.st-upcoming td.g{font-weight:400}
.st-early td.g{color:#1a7f37}
.foot{position:absolute;left:.5in;right:.5in;bottom:.3in;font-size:8px;color:#6e7781;
 border-top:1px solid #d8dee4;padding-top:4px;line-height:1.4}
"""


def render(stu: dict[str, str], a: dict, as_of: date, source: Path) -> str:
    name = f"{stu['First Name']} {stu['Last Name']}"
    campus = (stu.get("Campus") or "").strip()
    period = (stu.get("Period") or "").strip()
    grade, gsub = a["grade"], a["grade_submitted"]
    pace_cls, pace_lbl = a["pace"]
    n_miss, n_early = len(a["missing"]), len(a["early"])
    if n_miss:
        pace_sub = f"{n_miss} past-due item{'s' * (n_miss != 1)} not submitted"
    elif n_early:
        pace_sub = f"All due work done · {n_early} finished early"
    else:
        pace_sub = "All work due to date is done"

    p = [f'<div class="page"><div class="ferpa"><b>CONFIDENTIAL — FERPA-protected education record</b> '
         '(20 U.S.C. § 1232g). For school officials with a legitimate educational interest. '
         'Do not redisclose.</div>']
    p.append(
        f'<div class="head"><div><h1>{esc(name)}</h1><div class="course">Student Progress Report · '
        f'PSCI 2305 American Government (Dual Credit, ETAMU) · Fall 2026'
        f'{"<br>Section " + esc(SECTION[campus]) if campus in SECTION else ""}'
        f'{" · Period " + esc(period) if period else ""}</div></div>'
        f'<div class="meta">ETAMU ID <b>{esc(stu["OrgDefinedId"])}</b><br>'
        f'{"HS Student ID <b>" + esc(stu["HS Student ID"]) + "</b><br>" if stu.get("HS Student ID") else ""}'
        f'Report as of <b>{as_of.strftime("%a, %b %d, %Y").replace(" 0", " ")}</b></div></div>')

    g_txt = f"{fmt_pct(grade)}%" if grade is not None else "—"
    g_let = f" {letter(grade)}" if grade is not None else ""
    g_sub = (f"On submitted work only: {fmt_pct(gsub)}%" if gsub is not None
             else "No graded work yet")
    p.append('<div class="tiles">'
             f'<div class="tile"><div class="k">Current grade</div><div class="v">{g_txt}'
             f'<span style="font-size:15px;color:#57606a">{g_let}</span></div><div class="s">{g_sub}</div></div>'
             f'<div class="tile pace-{pace_cls}"><div class="k">Pace vs. schedule</div>'
             f'<div class="v" style="font-size:18px">{pace_lbl}</div><div class="s">{pace_sub}</div></div>'
             f'<div class="tile"><div class="k">Completed</div><div class="v">{a["done_count"]}'
             f'<span style="font-size:13px;color:#57606a"> / 60</span></div>'
             f'<div class="s">{a["due_count"]} due to date</div></div>'
             f'<div class="tile"><div class="k">Past-due missing</div><div class="v" '
             f'style="color:{"#b42318" if n_miss else "#1a7f37"}">{n_miss}</div>'
             f'<div class="s">{round(100 * a["done_count"] / 60)}% of course finished</div></div></div>')

    # --- progress by type
    p.append('<h2>Progress by assignment type</h2><table class="types"><tr><th>Type (weight)</th>'
             '<th style="text-align:right">Done</th><th style="text-align:right">Due so far</th>'
             '<th style="text-align:right">Missing</th><th style="text-align:right">Avg. submitted</th>'
             '<th style="width:36%">Progress of total</th></tr>')

    def type_row(label, done, total, due, miss, avg, cls=""):
        avg_s = f"{fmt_pct(avg)}%" if avg is not None else "—"
        return (f'<tr class="{cls}"><td>{label}</td><td class="n">{done} / {total}</td>'
                f'<td class="n">{due}</td><td class="n" style="color:{"#b42318" if miss else "inherit"}">'
                f'{miss}</td><td class="n">{avg_s}</td><td><div class="bar">'
                f'<div class="fill" style="width:{100 * done / total:.1f}%"></div>'
                f'<div class="mark" style="left:calc({100 * due / total:.1f}% - 1px)"></div></div></td></tr>')

    for typ, v in a["by_type"].items():
        p.append(type_row(f"{TYPE_LABEL[typ]} ({int(WEIGHTS[typ] * 100)}%)", v["done"], v["total"],
                          v["due"], v["missing"], v["avg_submitted"]))
    p.append(type_row("All assignments", a["done_count"], 60, a["due_count"], n_miss, None, "total"))
    p.append('</table><div class="legend"><i></i>marker = where the pacing guide expects the '
             'student to be today; blue fill = completed. In the list below, <span style="color:#1a7f37">'
             '<b>green</b></span> grades were finished before their target date; '
             '<span style="color:#b42318"><b>red</b></span> items are past due.</div>')

    if a["missing"]:
        names = [f"{r['title']} ({fmt_date(r['due'])})" for r in a["missing"]]
        shown = names if len(names) <= 10 else names[:9] + [f"and {len(names) - 9} more (red below)"]
        p.append(f'<div class="missing-box"><b>Past-due, not submitted:</b> {esc("; ".join(shown))}. '
                 'Late work is accepted through Dec 11 at −1% per day.</div>')

    # --- every assignment, by unit, in two columns
    p.append('<h2>All 60 assignments · target dates from the course pacing guide</h2><div class="cols">')
    for col_units in ((1, 2), (3, 4, 5)):
        p.append("<div>")
        for u in col_units:
            p.append(f'<div class="unit">Unit {u} <span>· {UNIT_NAMES[u]}</span></div><table class="items">')
            for r in (r for r in a["rows"] if r["unit"] == u):
                if r["grade"] is not None:
                    g = fmt_pct(r["grade"])
                elif r["state"] == "missing":
                    g = "Missing"
                else:
                    g = "—"
                ty = {"video": "Video", "scenario": "Scen.", "frq": "FRQ"}[r["type"]]
                due = "by " + fmt_date(r["due"]) if r["item"] in FLEXIBLE else fmt_date(r["due"])
                p.append(f'<tr class="st-{r["state"]}{" frq" if r["type"] == "frq" else ""}">'
                         f'<td class="ty">{ty}</td><td class="t">{esc(r["title"])}</td>'
                         f'<td class="d">{due}</td><td class="g">{g}</td></tr>')
            p.append("</table>")
        p.append("</div>")
    p.append("</div>")

    p.append(
        '<div class="foot"><b>How to read this.</b> Current grade uses the syllabus weights (videos 20% · '
        'scenarios 35% · FRQ exams 45%) over all graded work plus every past-due item, which counts as 0 until '
        'submitted; “on submitted work only” ignores missing items. Pace: <i>On track</i> = nothing past due; '
        f'<i>Ahead</i> = nothing past due and {AHEAD_MIN}+ items finished before their dates; <i>Slightly '
        f'behind</i> = 1–{SLIGHTLY_MAX} past-due items; <i>Behind</i> = more. Dates are pacing-guide targets; '
        'no work is accepted after Fri, Dec 11 (ETAMU term end). Letter scale A 90 · B 80 · C 70 · D 60. '
        f'Grades as of the {esc(source.stem.replace("all_grades_import_", ""))} gradebook export. '
        'Instructor: Arthur Turner · Arthur.Turner@etamu.edu</div></div>')

    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(name)} — progress report"
            f"</title><style>{CSS}</style></head><body>{''.join(p)}</body></html>")


# ---------------------------------------------------------------------------
# PDF (headless Edge, as in checklist_unit2.py)
# ---------------------------------------------------------------------------
def find_browser() -> str | None:
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(c):
            return c
    return None


def html_to_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    import shutil
    profile = Path(tempfile.mkdtemp(prefix="edge-pdf-"))
    try:
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
             "--print-to-pdf-no-header", html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=180)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    for _ in range(30):  # OneDrive can delay the file's appearance
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Edge exited cleanly but wrote no PDF: {pdf_path}")


def pdf_page_count(path: Path) -> int:
    import re
    data = path.read_bytes()
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", data)]
    return max(counts) if counts else len(re.findall(rb"/Type\s*/Page[^s]", data))


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--student", help="name filter to start the search with")
    ap.add_argument("--refresh", action="store_true",
                    help="run export_all_grades.py first to pull live grades")
    ap.add_argument("--grades", type=Path, help="grades CSV (default: newest export)")
    ap.add_argument("--as-of", type=date.fromisoformat, default=date.today(),
                    help="date to judge pace against (default: today)")
    ap.add_argument("--html", action="store_true", help="also keep the HTML file")
    args = ap.parse_args()

    check_items_against_template()
    if args.refresh:
        print("Pulling live grades (export_all_grades.py)…")
        subprocess.run([sys.executable, str(TOOLS / "export_all_grades.py")],
                       cwd=TOOLS, check=True)
    source = args.grades or newest_grades_csv()
    stamp = source.stem.replace("all_grades_import_", "")
    print(f"Grades: {source.name}")
    if not args.refresh and stamp != args.as_of.isoformat():
        print(f"  NOTE: export is from {stamp}; use --refresh for live grades.")

    grades = load_grades(source)
    roster = load_roster()
    browser = find_browser()
    if not browser:
        sys.exit("Edge/Chrome not found — cannot render PDF.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    query = args.student
    while True:
        stu = pick_student(roster, query)
        query = None
        a = analyze(grades.get(stu["OrgDefinedId"], {}), args.as_of)
        base = f"{stu['Last Name']}_{stu['First Name']}_{args.as_of.isoformat()}".replace(" ", "-")
        html_path = OUT_DIR / f"{base}.html"
        pdf_path = OUT_DIR / f"{base}.pdf"
        html_path.write_text(render(stu, a, args.as_of, source), encoding="utf-8")
        html_to_pdf(browser, html_path, pdf_path)
        if not args.html:
            html_path.unlink(missing_ok=True)
        pages = pdf_page_count(pdf_path)
        g = f"{fmt_pct(a['grade'])}% {letter(a['grade'])}" if a["grade"] is not None else "no grades"
        print(f"  {g} · {a['pace'][1]} · {a['done_count']}/60 done, {len(a['missing'])} past-due missing")
        print(f"  wrote {pdf_path}" + ("" if pages == 1 else f"  *** {pages} pages — expected 1 ***"))
        if input("Another student? [y/N] ").strip().lower() != "y":
            break


if __name__ == "__main__":
    main()
