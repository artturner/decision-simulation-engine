#!/usr/bin/env python
"""Build Unit 1 performance summaries from the fetched raw data.

Outputs (OneDrive 2026 Fall/unit1-reports/):
  unit1_master_<date>.csv                    one row per student, every dimension
  unit1_student_summaries_SGPHS_<date>.html  printable, one page per student
  unit1_student_summaries_GPHS_<date>.html
  unit1_teacher_report_<date>.html           class-level monitoring update
"""
import csv
import html
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

TOOLS = Path(r"C:\Users\arttu\decision-simulation-engine\tools\d2l-import")
sys.path.insert(0, str(TOOLS))
from d2l_prep import DEFAULT_ROSETTA, Roster, norm, split_name, video_grade  # noqa: E402
from export_all_grades import load_config  # noqa: E402

HERE = Path(__file__).resolve().parent
RAW = HERE / "unit1_raw"
OUT_DIR = Path(r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\unit1-reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()

VIDEOS = [  # (canonical title, chapter)
    ("What is Government", 1),
    ("Who Governs? Three Theories of Power", 1),
    ("The Modern Citizen: Civic Engagement", 1),
    ("Why America Declared Independence", 2),
    ("America's Rough Draft", 2),
    ("The Great Debate", 2),
    ("The American Tug-of-War", 3),
    ("The Great Power Struggle", 3),
    ("Federalism: A Tug of War", 3),
]
SCENARIOS = [
    ("ch1_liberty_park", "Liberty Park Under Threat", 1),
    ("ch2_philadelphia", "The Philadelphia Compromise", 2),
    ("ch3_cherokee", "A Nation Divided: The Cherokee Choice", 3),
]
OUTCOME_LABEL = {
    "success": "Success", "compromise": "Compromise", "failure": "Setback",
    "legal_path": "Legal path", "negotiation_path": "Negotiation path",
    "resistance_path": "Resistance path",
}
DIMS = [("explanation_task_response", "Explanation / task response"),
        ("specific_evidence", "Specific evidence"),
        ("reasoning", "Reasoning")]
W_VIDEO, W_SCEN, W_FRQ = 0.20, 0.35, 0.45


def f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def esc(s):
    return html.escape(str(s if s is not None else ""))


# ---------------------------------------------------------------------------
# Load + merge
# ---------------------------------------------------------------------------
cfg = load_config(TOOLS / ".env")
IGNORED = {norm(split_name(n)) for n in cfg["IGNORE_STUDENTS"].split(";") if n.strip()}
roster = Roster(DEFAULT_ROSETTA)
students: dict[str, dict] = {}   # org id -> record
unmatched: dict[str, set] = defaultdict(set)


def resolve(raw_name: str, source: str, campus_hint: str = "?"):
    key = norm(split_name(raw_name))
    if key in IGNORED:
        return None
    row, _note = roster.match(raw_name, interactive=False)
    if row is None:
        # Student is live in the apps but missing from the rosetta stone
        # (e.g. added to a class after the roster was built). Keep them in
        # the reports under a name key so they still get a summary sheet.
        unmatched[split_name(raw_name)].add(source)
        oid = f"name:{key}"
        if oid not in students:
            parts = split_name(raw_name).rsplit(" ", 1)
            first, last = (parts if len(parts) == 2 else (raw_name, ""))
            students[oid] = {
                "oid": "", "last": last, "first": first,
                "campus": campus_hint, "period": "?", "not_in_rosetta": True,
                "videos": {}, "scenarios": {}, "essay": None,
            }
        rec = students[oid]
        if rec["campus"] == "?" and campus_hint != "?":
            rec["campus"] = campus_hint
        return rec
    oid = row["OrgDefinedId"]
    if oid not in students:
        students[oid] = {
            "oid": oid, "last": row["Last Name"], "first": row["First Name"],
            "campus": (row.get("Campus") or "").strip() or "?",
            "period": (row.get("Period") or "").strip() or "?",
            "videos": {}, "scenarios": {}, "essay": None,
        }
    return students[oid]


def campus_from(label: str) -> str:
    up = (label or "").upper()
    if "SGPHS" in up:
        return "SGPHS"
    if "GPHS" in up:
        return "GPHS"
    return "?"


scen_raw = json.loads((RAW / "scenarios.json").read_text(encoding="utf-8"))
for block in scen_raw:
    for r in block["rows"]:
        rec = resolve(r["student_name"], f"scenario {block['title']}", campus_from(block["roll"]))
        if rec is None:
            continue
        cur = rec["scenarios"].get(block["scenario"])
        grade = f(r.get("grade_total"))
        # keep the better record if the student appears in two rolls
        if cur and (f(cur.get("grade")) or -1) >= (grade or -1) and cur["status"] == "completed":
            continue
        rec["scenarios"][block["scenario"]] = {
            "status": r["status"], "outcome": r.get("best_attempt_outcome") or "",
            "grade": grade, "submitted_count": int(f(r.get("submitted_count"), 0)),
            "accepted": r.get("grade_accepted") == "yes",
            "needs_review": r.get("needs_human_review") == "yes",
            "has_reflection": bool(r.get("reflection_submitted_at")),
        }

essay_raw = json.loads((RAW / "essays.json").read_text(encoding="utf-8"))
for block in essay_raw:
    for r in block["rows"]:
        rec = resolve(r["student_name"], "essay FRQ1", campus_from(block["roll"]))
        if rec is None:
            continue
        total = f(r.get("effective_total"))
        cur = rec["essay"]
        if cur and (cur["total"] or -1) >= (total or -1):
            continue
        rec["essay"] = {
            "status": r["status"], "total": total,
            "on_time": r.get("submitted_on_time"),
            "word_count": int(f(r.get("word_count"), 0)),
            "attempts": int(f(r.get("attempts_used"), 0)),
            "low_effort": r.get("low_effort_flags") or "",
            "needs_review": r.get("needs_human_review") == "yes",
            "dims": {k: {"level": r.get(f"{k}_level") or "",
                         "points": f(r.get(f"{k}_points"))} for k, _ in DIMS},
        }

vid_raw = json.loads((RAW / "videos.json").read_text(encoding="utf-8"))
CANON_BY_RAW = {"What is Government?": "What is Government",
                "Federalism: A Tug-of-War": "Federalism: A Tug of War",
                "Why America Declared Independence: The Broken Contract":
                    "Why America Declared Independence"}
for block in vid_raw:
    canon = CANON_BY_RAW.get(block["video"], block["video"])
    canon = CANON_BY_RAW.get(block["app_title"], canon)
    for r in block["rows"]:
        rec = resolve(r["student_name"], f"video {canon}", campus_from(block["class"]))
        if rec is None:
            continue
        qa, tq = int(f(r.get("questions_answered"), 0)), int(f(r.get("total_questions"), 0))
        ftc, att = int(f(r.get("first_try_correct"), 0)), int(f(r.get("total_attempts"), 0))
        g = video_grade(r.get("status") or "", ftc, tq)
        cur = rec["videos"].get(canon)
        if cur and (cur["grade"] or -1) >= (g if g is not None else -1):
            continue
        rec["videos"][canon] = {"status": r.get("status") or "not_started",
                                "qa": qa, "tq": tq, "ftc": ftc, "att": att,
                                "grade": g}

# ---------------------------------------------------------------------------
# Derived per-student metrics
# ---------------------------------------------------------------------------
VIDEO_TITLES = [t for t, _c in VIDEOS]
for rec in students.values():
    vids = rec["videos"]
    completed = [t for t in VIDEO_TITLES if vids.get(t, {}).get("status") == "completed"]
    grades = [vids.get(t, {}).get("grade") for t in VIDEO_TITLES]
    rec["video_completed"] = len(completed)
    rec["video_avg"] = round(sum(g or 0 for g in grades) / len(VIDEO_TITLES), 1)
    qa = sum(v["qa"] for v in vids.values())
    ftc = sum(v["ftc"] for v in vids.values())
    att = sum(v["att"] for v in vids.values())
    rec["q_answered"] = qa
    rec["first_try_pct"] = round(100 * ftc / qa, 1) if qa else None
    rec["avg_attempts"] = round(att / qa, 2) if qa else None

    scen = rec["scenarios"]
    done = [k for k, _t, _c in SCENARIOS
            if scen.get(k, {}).get("status") == "completed"]
    rec["scen_completed"] = len(done)
    rec["scen_avg"] = round(sum(scen.get(k, {}).get("grade") or 0
                                for k, _t, _c in SCENARIOS) / len(SCENARIOS), 1)

    es = rec["essay"]
    rec["frq_total"] = es["total"] if es and es["total"] is not None else None
    rec["composite"] = round(W_VIDEO * rec["video_avg"] + W_SCEN * rec["scen_avg"]
                             + W_FRQ * (rec["frq_total"] or 0), 1)

    missing = []
    for t in VIDEO_TITLES:
        if vids.get(t, {}).get("status") != "completed":
            missing.append(("video", t))
    for k, title, _c in SCENARIOS:
        st = scen.get(k, {})
        if st.get("status") != "completed":
            missing.append(("scenario", title))
        elif st.get("grade") is None:
            missing.append(("reflection", title))
    if rec["frq_total"] is None:
        missing.append(("frq", "Unit 1 FRQ (Federalism)"))
    rec["missing"] = missing

    rec["flags"] = []
    if rec.get("not_in_rosetta"):
        rec["flags"].append("not_in_rosetta")
    if rec["composite"] < 70 or len(missing) >= 3:
        rec["flags"].append("needs_encouragement")
    if (rec["video_completed"] >= 5 and rec["first_try_pct"] is not None
            and rec["first_try_pct"] < 60):
        rec["flags"].append("comprehension_watch")
    if rec["composite"] >= 93 and not missing:
        rec["flags"].append("high_performer")

roll = sorted(students.values(), key=lambda r: (r["campus"], r["last"], r["first"]))
by_campus = defaultdict(list)
for rec in roll:
    by_campus[rec["campus"]].append(rec)

# ---------------------------------------------------------------------------
# Master CSV
# ---------------------------------------------------------------------------
master = OUT_DIR / f"unit1_master_{TODAY}.csv"
with open(master, "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh)
    head = ["OrgDefinedId", "Last Name", "First Name", "Campus", "Period",
            "Unit1 Composite", "Video Avg", "Videos Completed (of 9)",
            "First-Try %", "Avg Attempts/Q", "Scenario Avg",
            "Scenarios Completed (of 3)"]
    for _k, title, _c in SCENARIOS:
        head += [f"{title} — outcome", f"{title} — reflection grade",
                 f"{title} — attempts"]
    head += ["FRQ1 Total", "FRQ1 On Time", "FRQ1 Word Count", "FRQ1 Attempts"]
    head += [f"FRQ1 {lbl} (pts/30)" for _k, lbl in DIMS]
    head += [f"{t} grade" for t in VIDEO_TITLES]
    head += ["Missing Items", "Flags"]
    w.writerow(head)
    for rec in roll:
        es = rec["essay"]
        row = [rec["oid"], rec["last"], rec["first"], rec["campus"],
               rec.get("period", "?"),
               rec["composite"], rec["video_avg"], rec["video_completed"],
               rec["first_try_pct"] if rec["first_try_pct"] is not None else "",
               rec["avg_attempts"] if rec["avg_attempts"] is not None else "",
               rec["scen_avg"], rec["scen_completed"]]
        for k, _t, _c in SCENARIOS:
            s = rec["scenarios"].get(k, {})
            row += [OUTCOME_LABEL.get(s.get("outcome"), s.get("outcome") or ""),
                    s.get("grade") if s.get("grade") is not None else "",
                    s.get("submitted_count") or ""]
        row += [rec["frq_total"] if rec["frq_total"] is not None else "",
                (es or {}).get("on_time") or "", (es or {}).get("word_count") or "",
                (es or {}).get("attempts") or ""]
        for k, _lbl in DIMS:
            p = ((es or {}).get("dims") or {}).get(k, {}).get("points")
            row.append(p if p is not None else "")
        for t in VIDEO_TITLES:
            g = rec["videos"].get(t, {}).get("grade")
            row.append(round(g, 1) if g is not None else "")
        row += ["; ".join(f"{kind}: {name}" for kind, name in rec["missing"]),
                ", ".join(rec["flags"])]
        w.writerow(row)
print(f"wrote {master.name} ({len(roll)} students)")

# ---------------------------------------------------------------------------
# Student summary sheets
# ---------------------------------------------------------------------------
# Compact enough that every sheet fits ONE US-Letter page when printed.
CSS = """
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:12px/1.35 'Segoe UI',Arial,sans-serif;color:#222;margin:0;padding:20px;background:#fff}
.sheet{max-width:740px;margin:0 auto 30px;page-break-after:always;border:1px solid #ddd;
 border-radius:8px;padding:14px 22px 10px}
h1{font-size:17px;margin:0 0 2px} .sub{color:#666;font-size:10.5px;margin-bottom:8px}
.tiles{display:flex;gap:8px;margin:8px 0 10px;flex-wrap:wrap}
.tile{flex:1;min-width:100px;border:1px solid #e0e0e0;border-radius:6px;padding:5px 8px;text-align:center}
.tile b{display:block;font-size:18px} .tile span{font-size:9px;color:#666;text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse;margin:4px 0 8px;font-size:11px}
th{text-align:left;font-size:9.5px;text-transform:uppercase;letter-spacing:.04em;color:#666;
 border-bottom:2px solid #ccc;padding:2px 6px}
td{border-bottom:1px solid #eee;padding:2.5px 6px}
h2{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#444;margin:9px 0 2px}
.ok{color:#1a7a2e;font-weight:600}.warn{color:#b3550e;font-weight:600}.miss{color:#b02a2a;font-weight:600}
.focus{background:#f6f8fb;border-left:3px solid #3c6291;padding:6px 12px;border-radius:0 6px 6px 0}
.focus li{margin:2px 0}
.chip{display:inline-block;border:1px solid #ccc;border-radius:12px;padding:0 8px;font-size:10.5px;margin-right:5px}
.blankpage{page-break-after:always}
/* Zero @page margin suppresses the browser's printed header/footer (they draw
   in the margin band); the sheet's own padding provides the physical margin. */
@page{size:letter;margin:0}
@media print{body{padding:0}
 .sheet{border:none;border-radius:0;padding:26px 36px 0;margin:0;max-width:none;page-break-inside:avoid}}
"""


def status_cell(status):
    return {"completed": '<span class="ok">Completed</span>',
            "in_progress": '<span class="warn">In progress</span>'}.get(
        status, '<span class="miss">Not started</span>')


def focus_bullets(rec):
    out = []
    vids_missing = [n for k, n in rec["missing"] if k == "video"]
    scen_missing = [n for k, n in rec["missing"] if k == "scenario"]
    refl_missing = [n for k, n in rec["missing"] if k == "reflection"]
    if vids_missing:
        shown = ", ".join(vids_missing[:3])
        more = f" — and {len(vids_missing) - 3} more" if len(vids_missing) > 3 else ""
        out.append(f"Finish the remaining video{'s' if len(vids_missing) > 1 else ''}: "
                   f"{shown}{more}.")
    if scen_missing:
        out.append("Complete the scenario" + ("s: " if len(scen_missing) > 1 else ": ")
                   + ", ".join(scen_missing) + ".")
    if refl_missing:
        out.append("You played but haven't submitted the reflection for: "
                   + ", ".join(refl_missing) + " — the reflection is where the grade comes from.")
    if rec["frq_total"] is None:
        out.append("Submit the Unit 1 FRQ (Federalism). Late penalty is only 1%/day — it is always worth turning in.")
    es = rec["essay"]
    if es and es["total"] is not None:
        weakest = min(es["dims"].items(), key=lambda kv: kv[1]["points"] or 0)
        if (weakest[1]["points"] or 0) <= 18:
            lbl = dict(DIMS)[weakest[0]]
            tip = {"specific_evidence": "name specific clauses, cases, and examples (e.g., commerce clause, McCulloch, categorical grants)",
                   "reasoning": "connect each piece of evidence back to the question with a because/therefore sentence",
                   "explanation_task_response": "answer every part of the prompt directly before adding detail"}[weakest[0]]
            out.append(f"On FRQs, your growth area is <b>{lbl.lower()}</b>: {tip}.")
    if rec["first_try_pct"] is not None and rec["first_try_pct"] < 60 and rec["video_completed"] >= 5:
        out.append("Video checkpoints: your first-try accuracy is below 60% — slow down before answering, "
                   "and rewind 30 seconds when a question surprises you.")
    for k, title, _c in SCENARIOS:
        s = rec["scenarios"].get(k, {})
        if s.get("status") == "completed" and (s.get("grade") or 0) and s["grade"] < 70:
            out.append(f"Consider replaying <i>{title}</i> and resubmitting a deeper reflection — "
                       "only your best attempt counts.")
            break
    if not out:
        out.append("Everything in Unit 1 is complete and strong across all three platforms — excellent consistency. "
                   "Keep the same rhythm in Unit 2.")
    return out[:4]  # one printed page per student — never let the list overflow


def student_sheet(rec):
    es = rec["essay"]
    frq = f"{rec['frq_total']:g}" if rec["frq_total"] is not None else "—"
    ft = f"{rec['first_try_pct']:g}%" if rec["first_try_pct"] is not None else "—"
    h = [f'<div class="sheet"><h1>{esc(rec["first"])} {esc(rec["last"])}</h1>'
         f'<div class="sub">PSCI 2305 — Unit 1 performance summary (Chapters 1–3: '
         f'Government, the Constitution, Federalism) · {esc(rec["campus"])}'
         f'{" · Period " + esc(rec["period"]) if rec.get("period", "?") != "?" else ""}'
         f' · generated {TODAY}</div>']
    h.append('<div class="tiles">'
             f'<div class="tile"><b>{rec["composite"]:g}</b><span>Unit 1 composite*</span></div>'
             f'<div class="tile"><b>{rec["video_avg"]:g}</b><span>Videos (avg of 9)</span></div>'
             f'<div class="tile"><b>{rec["scen_avg"]:g}</b><span>Scenarios (avg of 3)</span></div>'
             f'<div class="tile"><b>{frq}</b><span>Unit 1 FRQ</span></div>'
             f'<div class="tile"><b>{ft}</b><span>First-try accuracy</span></div></div>')

    h.append('<h2>Video quizzes — 9 assigned</h2><table><tr><th>Ch</th><th>Video</th>'
             '<th>Status</th><th>First-try</th><th>Grade</th></tr>')
    for title, ch in VIDEOS:
        v = rec["videos"].get(title, {})
        first = f"{v['ftc']}/{v['qa']}" if v.get("qa") else "—"
        g = f"{round(v['grade'], 1):g}" if v.get("grade") is not None else "—"
        h.append(f'<tr><td>{ch}</td><td>{esc(title)}</td><td>{status_cell(v.get("status"))}</td>'
                 f'<td>{first}</td><td>{g}</td></tr>')
    h.append("</table>")

    h.append('<h2>Decision scenarios — 3 assigned</h2><table><tr><th>Ch</th><th>Scenario</th>'
             '<th>Status</th><th>Path reached</th><th>Reflection grade</th></tr>')
    for k, title, ch in SCENARIOS:
        s = rec["scenarios"].get(k, {})
        out_lbl = OUTCOME_LABEL.get(s.get("outcome"), s.get("outcome") or "—")
        g = f"{s['grade']:g}" if s.get("grade") is not None else (
            '<span class="warn">reflection pending</span>' if s.get("status") == "completed" else "—")
        h.append(f'<tr><td>{ch}</td><td>{esc(title)}</td><td>{status_cell(s.get("status"))}</td>'
                 f'<td>{esc(out_lbl)}</td><td>{g}</td></tr>')
    h.append('</table><div class="sub" style="margin-top:-8px">Scenario grades come from your '
             'written reflection, not from which ending you reached — every path is gradable.</div>')

    h.append('<h2>Unit 1 FRQ — Federalism evolution</h2>')
    if es and es["total"] is not None:
        chips = "".join(
            f'<span class="chip">{dict(DIMS)[k]}: <b>{d["level"] or "—"}</b>'
            f' ({d["points"]:g}/30)</span>' for k, d in es["dims"].items())
        late = "" if es["on_time"] == "yes" else ' · <span class="warn">submitted late</span>'
        h.append(f'<p style="margin:4px 0 6px"><b>{es["total"]:g}/100</b>{late} · '
                 f'{es["word_count"]} words · {es["attempts"]} attempt{"s" if es["attempts"] != 1 else ""}</p>'
                 f'<p style="margin:4px 0">{chips}</p>')
    else:
        h.append('<p class="miss" style="margin:4px 0">Not submitted.</p>')

    h.append('<h2>Where to focus next</h2><div class="focus"><ul style="margin:6px 0;padding-left:20px">')
    for b in focus_bullets(rec):
        h.append(f"<li>{b}</li>")
    h.append('</ul></div>')
    h.append('<div class="sub" style="margin-top:10px">*Composite uses the course weights: '
             'videos 20% · scenarios 35% · FRQ exams 45%. Missing work counts as zero, so '
             'finishing anything on the list raises it immediately.</div></div>')
    return "".join(h)


def period_key(rec):
    p = rec.get("period", "?")
    return (0, int(p)) if p.isdigit() else (1, 0)


def find_browser():
    import os
    for c in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if os.path.exists(c):
            return c
    return None


def html_to_pdf(browser, html_path: Path, pdf_path: Path):
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:  # own profile: never fights a running Edge
        subprocess.run(
            [browser, "--headless=new", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={tmp}", f"--print-to-pdf={pdf_path}",
             "--print-to-pdf-no-header", html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=600)


def pdf_page_count(path: Path) -> int:
    data = path.read_bytes()
    import re as _re
    counts = [int(m) for m in _re.findall(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", data)]
    if counts:
        return max(counts)
    return len(_re.findall(rb"/Type\s*/Page[^s]", data))


BROWSER = find_browser()
for campus, recs in sorted(by_campus.items()):
    recs = sorted(recs, key=lambda r: (period_key(r), r["last"].lower(), r["first"].lower()))
    path = OUT_DIR / f"unit1_student_summaries_{campus}_{TODAY}.html"
    parts, last_period = [], object()
    for r in recs:
        if r.get("period", "?") != last_period:
            last_period = r.get("period", "?")
            n = sum(1 for x in recs if x.get("period", "?") == last_period)
            label = f"Period {last_period}" if last_period != "?" else "No period assigned"
            parts.append(
                f'<div class="sheet" style="display:flex;align-items:center;justify-content:center;'
                f'min-height:220px"><div style="text-align:center"><h1 style="font-size:30px">'
                f'{esc(campus)} — {label}</h1><div class="sub" style="font-size:14px">'
                f'{n} student summaries · Unit 1 · {TODAY}</div></div></div>')
        parts.append(student_sheet(r))
    head_html = (f"<!doctype html><html><head><meta charset='utf-8'><title>Unit 1 summaries — "
                 f"{campus}</title><style>{CSS}</style></head><body>")
    path.write_text(head_html + "".join(parts) + "</body></html>", encoding="utf-8")
    periods = [p for p, _ in
               sorted({(r.get('period', '?'), period_key(r)) for r in recs}, key=lambda t: t[1])]
    n_pages = len(parts)  # dividers + one page per student
    print(f"wrote {path.name} ({len(recs)} sheets, periods: {', '.join(periods)})")

    # Duplex-safe copy: a blank page behind every page, so a copier stuck on
    # 2-sided printing still puts each student's data alone on its own sheet.
    blank = '<div class="blankpage">&nbsp;</div>'
    dup_html = OUT_DIR / f"_duplex_{campus}.html"
    dup_html.write_text(head_html + blank.join(parts) + blank + "</body></html>",
                        encoding="utf-8")

    if BROWSER:
        for src, suffix, expect in ((path, "", n_pages),
                                    (dup_html, "_duplexsafe", n_pages * 2)):
            pdf = OUT_DIR / f"unit1_student_summaries_{campus}_{TODAY}{suffix}.pdf"
            html_to_pdf(BROWSER, src, pdf)
            got = pdf_page_count(pdf)
            status = "OK" if got == expect else f"MISMATCH (expected {expect})"
            print(f"  {pdf.name}: {got} pages {status}")
    else:
        print("  (no Edge/Chrome found — PDFs skipped)")
    dup_html.unlink(missing_ok=True)

# ---------------------------------------------------------------------------
# Teacher report
# ---------------------------------------------------------------------------
def mean(vals):
    vals = [v for v in vals if v is not None]
    return round(statistics.mean(vals), 1) if vals else None


def pct(n, d):
    return round(100 * n / d, 1) if d else 0


vq = json.loads((RAW / "video_questions.json").read_text(encoding="utf-8"))
most_missed = json.loads((RAW / "most_missed.json").read_text(encoding="utf-8"))
unit1_titles_norm = {t.lower().replace("?", "").replace("-", " ").replace(":", "")
                     for t in VIDEO_TITLES} | {"what is government", "federalism a tug of war",
                                               "why america declared independence the broken contract"}

R = []
R.append(f"""<!doctype html><html><head><meta charset="utf-8">
<title>Unit 1 monitoring report</title><style>
body{{font:14px/1.5 'Segoe UI',Arial,sans-serif;color:#222;max-width:960px;margin:0 auto;padding:28px 20px}}
h1{{font-size:22px;margin-bottom:2px}} h2{{font-size:16px;margin:26px 0 6px;border-bottom:2px solid #ddd;padding-bottom:3px}}
h3{{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#555;margin:16px 0 4px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}
th{{text-align:left;background:#f4f4f4;padding:5px 8px;font-size:12px}}
td{{border-bottom:1px solid #eee;padding:5px 8px;vertical-align:top}}
.bar{{background:#3c6291;height:10px;border-radius:2px;display:inline-block;vertical-align:middle}}
.sub{{color:#666;font-size:12px}} .warn{{color:#b3550e;font-weight:600}} .bad{{color:#b02a2a;font-weight:600}}
.ok{{color:#1a7a2e;font-weight:600}} .note{{background:#fdf6ec;border-left:3px solid #b3550e;padding:8px 14px;margin:8px 0}}
</style></head><body>
<h1>Unit 1 performance monitoring — PSCI 2305</h1>
<div class="sub">Chapters 1–3 · 9 video quizzes · 3 decision scenarios · Unit 1 FRQ (Federalism, due Sep 11) ·
data pulled live {TODAY} · {len(roll)} rostered students ({len(by_campus.get('SGPHS', []))} SGPHS, {len(by_campus.get('GPHS', []))} GPHS)</div>""")

# --- section overview
R.append("<h2>1 · Section overview</h2><table><tr><th>Section</th><th>n</th>"
         "<th>Unit composite (mean)</th><th>Video avg</th><th>First-try %</th>"
         "<th>Scenario avg</th><th>FRQ mean (submitted)</th><th>FRQ submitted</th>"
         "<th>All work complete</th></tr>")
for campus, recs in sorted(by_campus.items()):
    frqs = [r["frq_total"] for r in recs if r["frq_total"] is not None]
    complete = sum(1 for r in recs if not r["missing"])
    R.append(f"<tr><td><b>{campus}</b></td><td>{len(recs)}</td>"
             f"<td>{mean([r['composite'] for r in recs])}</td>"
             f"<td>{mean([r['video_avg'] for r in recs])}</td>"
             f"<td>{mean([r['first_try_pct'] for r in recs])}</td>"
             f"<td>{mean([r['scen_avg'] for r in recs])}</td>"
             f"<td>{mean(frqs)}</td>"
             f"<td>{len(frqs)}/{len(recs)} ({pct(len(frqs), len(recs))}%)</td>"
             f"<td>{complete}/{len(recs)} ({pct(complete, len(recs))}%)</td></tr>")
R.append("</table>")

# --- completion funnel per assignment
R.append("<h2>2 · Completion by assignment</h2><table><tr><th>Assignment</th>"
         "<th>Type</th><th>Completed</th><th>In progress</th><th>Not started</th>"
         "<th>Mean grade (completed)</th></tr>")
for title, ch in VIDEOS:
    sts = Counter(r["videos"].get(title, {}).get("status", "not_started") for r in roll)
    gs = [r["videos"][title]["grade"] for r in roll
          if r["videos"].get(title, {}).get("grade") is not None]
    n = len(roll)
    R.append(f"<tr><td>Ch{ch} · {esc(title)}</td><td>video</td>"
             f"<td>{sts['completed']} ({pct(sts['completed'], n)}%)</td>"
             f"<td>{sts['in_progress']}</td><td>{sts['not_started'] + sts[None]}</td>"
             f"<td>{mean(gs)}</td></tr>")
for k, title, ch in SCENARIOS:
    sts = Counter(r["scenarios"].get(k, {}).get("status", "not_started") for r in roll)
    gs = [r["scenarios"][k]["grade"] for r in roll
          if r["scenarios"].get(k, {}).get("grade") is not None]
    pending = sum(1 for r in roll if r["scenarios"].get(k, {}).get("status") == "completed"
                  and r["scenarios"][k].get("grade") is None)
    extra = f" <span class='warn'>({pending} played, reflection pending)</span>" if pending else ""
    R.append(f"<tr><td>Ch{ch} · {esc(title)}</td><td>scenario</td>"
             f"<td>{sts['completed']} ({pct(sts['completed'], len(roll))}%){extra}</td>"
             f"<td>{sts['in_progress']}</td><td>{sts['not_started']}</td>"
             f"<td>{mean(gs)}</td></tr>")
frq_sub = [r for r in roll if r["frq_total"] is not None]
late = sum(1 for r in frq_sub if (r["essay"] or {}).get("on_time") != "yes")
R.append(f"<tr><td>Unit 1 FRQ — Federalism</td><td>essay</td>"
         f"<td>{len(frq_sub)} ({pct(len(frq_sub), len(roll))}%), {late} late</td><td>—</td>"
         f"<td>{len(roll) - len(frq_sub)}</td>"
         f"<td>{mean([r['frq_total'] for r in frq_sub])}</td></tr></table>")

# --- FRQ dimension analysis
R.append("<h2>3 · FRQ skill breakdown (reteach signal)</h2>")
R.append("<table><tr><th>Dimension</th><th>Mean pts /30</th><th>Level distribution (submitted essays)</th></tr>")
dim_means = {}
for k, lbl in DIMS:
    pts = [(r["essay"]["dims"][k]["points"]) for r in frq_sub
           if r["essay"]["dims"].get(k, {}).get("points") is not None]
    levels = Counter((r["essay"]["dims"][k]["level"] or "?") for r in frq_sub)
    dim_means[k] = mean(pts)
    dist = " · ".join(f"{lv}: {n}" for lv, n in levels.most_common())
    bar = int((dim_means[k] or 0) / 30 * 200)
    R.append(f"<tr><td>{lbl}</td><td><span class='bar' style='width:{bar}px'></span> "
             f"{dim_means[k]}</td><td class='sub'>{dist}</td></tr>")
R.append("</table>")
weakest_key = min(dim_means, key=lambda k: dim_means[k] or 99)
R.append(f"<div class='note'>Weakest FRQ dimension overall: <b>{dict(DIMS)[weakest_key]}</b> "
         f"(mean {dim_means[weakest_key]}/30). </div>")
low_effort = [(r, r["essay"]["low_effort"]) for r in frq_sub if r["essay"]["low_effort"]]
if low_effort:
    R.append("<h3>Low-effort flags</h3><ul>")
    for r, flag in low_effort:
        R.append(f"<li>{esc(r['first'])} {esc(r['last'])} ({r['campus']}): {esc(flag)}</li>")
    R.append("</ul>")
multi_attempt = sum(1 for r in frq_sub if r["essay"]["attempts"] > 1)
R.append(f"<p class='sub'>Revision use: {multi_attempt}/{len(frq_sub)} submitted essays used "
         f"more than one attempt ({pct(multi_attempt, len(frq_sub))}%).</p>")

# --- scenario analysis
R.append("<h2>4 · Scenario outcomes &amp; reflections</h2>")
R.append("<table><tr><th>Scenario</th><th>Path distribution (completed)</th>"
         "<th>Reflection grade mean</th><th>&lt;70</th><th>Needs review</th><th>Resubmitted (2+ plays)</th></tr>")
for k, title, ch in SCENARIOS:
    rows = [r["scenarios"][k] for r in roll if k in r["scenarios"]]
    comp = [s for s in rows if s["status"] == "completed"]
    dist = Counter(OUTCOME_LABEL.get(s["outcome"], s["outcome"]) for s in comp)
    gs = [s["grade"] for s in comp if s["grade"] is not None]
    low = sum(1 for g in gs if g < 70)
    review = sum(1 for s in rows if s["needs_review"])
    multi = sum(1 for s in comp if s["submitted_count"] > 1)
    dist_s = " · ".join(f"{o}: {n} ({pct(n, len(comp))}%)" for o, n in dist.most_common())
    R.append(f"<tr><td>Ch{ch} · {esc(title)}</td><td class='sub'>{dist_s}</td>"
             f"<td>{mean(gs)}</td><td>{low}</td><td>{review}</td><td>{multi}</td></tr>")
R.append("</table>")

# --- video item analysis
R.append("<h2>5 · Video question item analysis (content quality signal)</h2>"
         "<p class='sub'>Questions where fewer than 70% of students answered right on the "
         "first try (min 10 responses). A dominant wrong option suggests the video segment "
         "or the question itself needs attention.</p>"
         "<table><tr><th>Video</th><th>t</th><th>Question</th><th>n</th>"
         "<th>First-try %</th><th>Avg attempts</th><th>Wrong answers drawn to</th></tr>")
flagged_q = 0
for block in vq:
    for q in block["questions"]:
        n = int(f(q.get("responses"), 0))
        fa = f(q.get("first_attempt_pct"))
        if n < 10 or fa is None or fa >= 70:
            continue
        flagged_q += 1
        wrong = q.get("wrong_first_answers") or {}
        tot_wrong = sum(wrong.values()) or 1
        wrong_s = ", ".join(f"{o}: {c} ({pct(c, tot_wrong)}%)"
                            for o, c in sorted(wrong.items(), key=lambda kv: -kv[1]))
        ts = int(f(q.get("timestamp_s"), 0))
        cls = "bad" if fa < 50 else "warn"
        R.append(f"<tr><td>{esc(block['video'])}</td><td>{ts // 60}:{ts % 60:02d}</td>"
                 f"<td class='sub'>{esc(q['prompt'])}</td><td>{n}</td>"
                 f"<td class='{cls}'>{fa:g}%</td><td>{f(q.get('avg_attempts')):g}</td>"
                 f"<td class='sub'>{wrong_s}</td></tr>")
if not flagged_q:
    R.append("<tr><td colspan='7' class='ok'>No Unit 1 question fell below 70% first-try.</td></tr>")
R.append("</table>")

# --- watchlists
R.append("<h2>6 · Student watchlists</h2>")


def name_line(r, extra=""):
    return (f"<li>{esc(r['first'])} {esc(r['last'])} ({r['campus']}) — "
            f"composite {r['composite']:g}{extra}</li>")


enc = [r for r in roll if "needs_encouragement" in r["flags"]]
tier1 = [r for r in enc if len(r["missing"]) >= 8]
tier2 = [r for r in enc if 3 <= len(r["missing"]) <= 7]
tier3 = [r for r in enc if len(r["missing"]) <= 2]


def tier_list(title, recs):
    R.append(f"<h3>{title} ({len(recs)})</h3><ul>")
    for r in sorted(recs, key=lambda r: r["composite"]):
        frq_s = "no FRQ" if r["frq_total"] is None else f"FRQ {r['frq_total']:g}"
        R.append(name_line(r, f", {len(r['missing'])}/13 items missing, {frq_s}"))
    R.append("</ul>")


tier_list("Tier 1 — priority outreach: barely engaged (≥8 of 13 items missing)", tier1)
tier_list("Tier 2 — behind: 3–7 items missing", tier2)
tier_list("Tier 3 — doing the work but struggling: ≤2 missing, composite &lt; 70", tier3)
comp_watch = [r for r in roll if "comprehension_watch" in r["flags"]
              and "needs_encouragement" not in r["flags"]]
R.append(f"<h3>Comprehension watch — completing videos but first-try &lt; 60% ({len(comp_watch)})</h3><ul>")
for r in sorted(comp_watch, key=lambda r: r["first_try_pct"] or 0):
    R.append(name_line(r, f", first-try {r['first_try_pct']:g}%"))
R.append("</ul>")
refl_pend = [(r, title) for r in roll for k, title, _c in SCENARIOS
             if r["scenarios"].get(k, {}).get("status") == "completed"
             and r["scenarios"][k].get("grade") is None]
if refl_pend:
    R.append(f"<h3>Played a scenario but no graded reflection ({len(refl_pend)}) — quick wins</h3><ul>")
    for r, title in refl_pend:
        R.append(f"<li>{esc(r['first'])} {esc(r['last'])} ({r['campus']}) — {esc(title)}</li>")
    R.append("</ul>")
stars = [r for r in roll if "high_performer" in r["flags"]]
R.append(f"<h3>High performers — composite ≥ 93, nothing missing ({len(stars)})</h3>"
         f"<p class='sub'>{', '.join(esc(r['first']) + ' ' + esc(r['last']) for r in stars)}</p>")

# --- data quality
R.append("<h2>7 · Data notes</h2><ul>")
if unmatched:
    for nm, srcs in sorted(unmatched.items()):
        R.append(f"<li class='warn'>{esc(nm)} is active in the apps ({len(srcs)} assignments) "
                 "but NOT in the rosetta stone — included in these reports by name, but their "
                 "grades are silently dropped from every D2L import until you add them "
                 "(with their ETAMU OrgDefinedId) to rosetta_stone.csv.</li>")
else:
    R.append("<li class='ok'>Every app name matched the rosetta stone.</li>")
R.append(f"<li class='sub'>Ignored (pilot/summer) students skipped: "
         f"{esc(cfg['IGNORE_STUDENTS'] or 'none configured')}.</li>")
R.append("<li class='sub'>Composite = 20% videos + 35% scenarios + 45% FRQ (course weights); "
         "missing work counted as 0.</li></ul>")
R.append("</body></html>")

report = OUT_DIR / f"unit1_teacher_report_{TODAY}.html"
report.write_text("".join(R), encoding="utf-8")
print(f"wrote {report.name}")

# console digest for the session
print("\n--- digest ---")
for campus, recs in sorted(by_campus.items()):
    frqs = [r["frq_total"] for r in recs if r["frq_total"] is not None]
    print(f"{campus}: n={len(recs)} composite={mean([r['composite'] for r in recs])} "
          f"video={mean([r['video_avg'] for r in recs])} scen={mean([r['scen_avg'] for r in recs])} "
          f"frq={mean(frqs)} frq_submitted={len(frqs)}/{len(recs)}")
print("dim means:", {dict(DIMS)[k]: v for k, v in dim_means.items()})
print(f"needs_encouragement={len(enc)} comprehension_watch={len(comp_watch)} "
      f"high={len(stars)} refl_pending={len(refl_pend)} flagged_questions={flagged_q}")
if unmatched:
    print("UNMATCHED:", {k: sorted(v) for k, v in unmatched.items()})
