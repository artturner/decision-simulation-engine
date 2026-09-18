#!/usr/bin/env python
"""Per-student Unit 2 checklist sheets from the fetched status data.

One Letter page per student, period-sorted with divider pages, printable
PDFs (plain + duplex-safe with blank backs), mirroring analyze_unit1.py.
Items are pre-checked from live data; unchecked boxes are real boxes the
student can tick with a pen. Students who haven't claimed their access
code see it printed on the sheet.

Outputs (OneDrive 2026 Fall/unit2-checklists/):
  unit2_checklists_<campus>_<date>.html / .pdf / _duplexsafe.pdf
"""
import html
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent / "d2l-import"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(HERE.parent.parent / "services" / "api"))

from d2l_prep import DEFAULT_ROSETTA, Roster, norm, split_name  # noqa: E402
from export_all_grades import load_config  # noqa: E402
from app.services.names import student_name_key  # noqa: E402

RAW = HERE / "unit2_raw"
OUT_DIR = Path(r"C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\unit2-checklists")
OUT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = date.today().isoformat()

JOIN_URL = "scenarios.cruxlabs.academy/join"

VIDEOS = {  # canonical title -> chapter (matches fetch_unit2 canon)
    "Civil Liberties": 4, "Applying Our Freedoms": 4,
    "The Rights of Suspects": 4, "Unwritten Rights": 4,
    "Civil Rights: Rules of Equality": 5, "The Struggle for Equality": 5,
    "Wider Struggle for Rights": 5,
    "The Polling Puzzle": 6, "Demystifying the Polls": 6,
    "What Is Public Opinion": 6, "Effects of Public Opinion": 6,
    "Voter Registration and Turnout": 7, "Elections, Campaigns and Voting": 7,
    "Direct Democracy": 7,
}
SCENARIOS = {
    "ch4_probable_cause": "Probable Cause: Traffic Stop Investigation",
    "ch7_motor_voter": "The Motor Voter Decision",
}


def campus_from(label: str) -> str:
    up = (label or "").upper()
    if "SGPHS" in up:
        return "SGPHS"
    return "GPHS" if "GPHS" in up else "?"


def esc(s):
    return html.escape(str(s if s is not None else ""))


# ---------------------------------------------------------------------------
# Load + merge (same identity plumbing as analyze_unit1)
# ---------------------------------------------------------------------------
cfg = load_config(TOOLS / ".env")
IGNORED = {norm(split_name(n)) for n in cfg["IGNORE_STUDENTS"].split(";") if n.strip()}
roster = Roster(DEFAULT_ROSETTA)
students: dict[str, dict] = {}
unmatched: set[str] = set()


def resolve(raw_name: str, campus_hint: str = "?"):
    key = norm(split_name(raw_name))
    if key in IGNORED:
        return None
    row, _note = roster.match(raw_name, interactive=False)
    if row is None:
        unmatched.add(split_name(raw_name))
        oid = f"name:{key}"
        if oid not in students:
            parts = split_name(raw_name).rsplit(" ", 1)
            first, last = (parts if len(parts) == 2 else (raw_name, ""))
            students[oid] = {"oid": "", "last": last, "first": first,
                             "campus": campus_hint, "period": "?",
                             "videos": {}, "scenarios": {}, "essay": None,
                             "claim": None}
        return students[oid]
    oid = row["OrgDefinedId"]
    if oid not in students:
        students[oid] = {
            "oid": oid, "last": row["Last Name"], "first": row["First Name"],
            "campus": (row.get("Campus") or "").strip() or "?",
            "period": (row.get("Period") or "").strip() or "?",
            "videos": {}, "scenarios": {}, "essay": None, "claim": None,
        }
    return students[oid]


for block in json.loads((RAW / "scenarios.json").read_text(encoding="utf-8")):
    hint = campus_from(block["roll"])
    for r in block["rows"]:
        rec = resolve(r["student_name"], hint)
        if rec is None:
            continue
        cur = rec["scenarios"].get(block["scenario"])
        entry = {
            "status": r["status"],
            "reflected": bool(r.get("reflection_submitted_at") or r.get("grade_total")),
        }
        # keep the most-advanced record across rolls
        rank = {"completed": 2, "in_progress": 1}.get
        if cur and (rank(cur["status"], 0), cur["reflected"]) >= (rank(entry["status"], 0), entry["reflected"]):
            continue
        rec["scenarios"][block["scenario"]] = entry

for block in json.loads((RAW / "essays.json").read_text(encoding="utf-8")):
    hint = campus_from(block["roll"])
    for r in block["rows"]:
        rec = resolve(r["student_name"], hint)
        if rec is None:
            continue
        status = r.get("status") or "not_started"
        cur = rec["essay"]
        rank = {"accepted": 3, "graded": 2, "draft": 1}.get
        if cur and rank(cur, 0) >= rank(status, 0):
            continue
        rec["essay"] = status

for block in json.loads((RAW / "videos.json").read_text(encoding="utf-8")):
    hint = campus_from(block["class"])
    for r in block["rows"]:
        rec = resolve(r["student_name"], hint)
        if rec is None:
            continue
        status = r.get("status") or "not_started"
        cur = rec["videos"].get(block["video"])
        rank = {"completed": 2, "in_progress": 1}.get
        if cur and rank(cur, 0) >= rank(status, 0):
            continue
        rec["videos"][block["video"]] = status

for block in json.loads((RAW / "claims.json").read_text(encoding="utf-8")):
    hint = campus_from(block["roll"])
    for c in block["codes"]:
        rec = resolve(c["student_name"], hint)
        if rec is None:
            continue
        rec["claim"] = {"code": c["code"], "claimed": bool(c["last_claimed_at"])}

roll = sorted(students.values(), key=lambda r: (r["campus"], r["last"], r["first"]))
by_campus = defaultdict(list)
for rec in roll:
    by_campus[rec["campus"]].append(rec)

# ---------------------------------------------------------------------------
# Sheet rendering
# ---------------------------------------------------------------------------
CSS = """
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:12px/1.35 'Segoe UI',Arial,sans-serif;color:#222;margin:0;padding:20px;background:#fff}
.sheet{max-width:740px;margin:0 auto 30px;page-break-after:always;border:1px solid #ddd;
 border-radius:8px;padding:14px 22px 10px}
h1{font-size:17px;margin:0 0 2px} .sub{color:#666;font-size:10.5px;margin-bottom:8px}
h2{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#3c6291;margin:9px 0 3px;
 border-bottom:1px solid #e4e8ef;padding-bottom:2px}
h2 .when{float:right;color:#888;text-transform:none;letter-spacing:0;font-weight:400}
.item{display:flex;align-items:flex-start;gap:8px;padding:2.5px 0;font-size:11.5px}
.box{flex:none;width:13px;height:13px;border:1.5px solid #9aa4b2;border-radius:3px;margin-top:1px;
 text-align:center;font:700 10px/12px Arial;color:#fff}
.done .box{background:#1a7a2e;border-color:#1a7a2e}
.done .label{color:#5a5f66;text-decoration:line-through;text-decoration-color:#b9c0c9}
.prog{color:#b3550e;font-weight:600;font-size:10px;margin-left:6px}
.code-callout{background:#fdf6ec;border:1.5px dashed #b3550e;border-radius:6px;padding:6px 12px;
 margin:2px 0 4px;font-size:11.5px}
.code-callout b.code{font:700 15px/1.3 Consolas,monospace;letter-spacing:.14em}
.footer{margin-top:8px;border-top:2px solid #ccc;padding-top:6px;display:flex;
 justify-content:space-between;align-items:center;font-size:11px}
.bar{height:9px;background:#eceff3;border-radius:5px;overflow:hidden;flex:1;margin:0 12px}
.bar>div{height:100%;background:#1a7a2e}
.blankpage{page-break-after:always}
@page{size:letter;margin:0}
@media print{body{padding:0}
 .sheet{border:none;border-radius:0;padding:26px 36px 0;margin:0;max-width:none;page-break-inside:avoid}}
"""


def item(done: bool, label: str, note: str = "") -> str:
    cls = "item done" if done else "item"
    mark = "&#10003;" if done else "&nbsp;"
    extra = f'<span class="prog">{esc(note)}</span>' if note else ""
    return (f'<div class="{cls}"><span class="box">{mark}</span>'
            f'<span class="label">{label}</span>{extra}</div>')


def video_item(rec, title: str) -> tuple[str, bool]:
    st = rec["videos"].get(title, "not_started")
    done = st == "completed"
    return item(done, f"Watch <b>{esc(title)}</b>",
                "in progress" if st == "in_progress" else ""), done


def sheet(rec) -> str:
    parts = [f'<div class="sheet"><h1>{esc(rec["first"])} {esc(rec["last"])} — Unit 2 Checklist</h1>'
             f'<div class="sub">PSCI 2305 · Individual Agency &amp; Action (Chapters 4–7) · '
             f'{esc(rec["campus"])}'
             f'{" · Period " + esc(rec["period"]) if rec["period"] != "?" else ""}'
             f' · progress as of {TODAY}</div>']
    done_count, total = 0, 0

    # --- setup
    claim = rec["claim"]
    claimed = bool(claim and claim["claimed"])
    parts.append('<h2>Get set up <span class="when">once, takes a minute</span></h2>')
    parts.append(item(claimed, f"Enter your <b>access code</b> at <b>{JOIN_URL}</b> "
                               "(pick your name first). It unlocks your work here and on the essays site."))
    total += 1
    done_count += claimed
    if claim and not claimed:
        parts.append(f'<div class="code-callout">Your access code: '
                     f'<b class="code">{esc(claim["code"])}</b> — keep this sheet.</div>')

    def section(title, when, entries):
        nonlocal done_count, total
        parts.append(f'<h2>{title} <span class="when">{when}</span></h2>')
        for html_row, done in entries:
            parts.append(html_row)
            total += 1
            done_count += done

    def scen_items(key):
        title = SCENARIOS[key]
        s = rec["scenarios"].get(key, {"status": "not_started", "reflected": False})
        played = s["status"] == "completed"
        rows = [item(played, f"Play <b>{esc(title)}</b>",
                     "in progress" if s["status"] == "in_progress" else "")]
        rows_done = [played]
        reflected = s["reflected"]
        rows.append(item(reflected, "Submit its <b>reflection</b> — the reflection is the grade"))
        rows_done.append(reflected)
        return list(zip(rows, rows_done))

    ch45 = [video_item(rec, t) for t, ch in VIDEOS.items() if ch in (4, 5)]
    section("Chapters 4 &amp; 5 — Civil Liberties &amp; Civil Rights",
            "week of Sep 14 (this week!)", ch45 + scen_items("ch4_probable_cause"))
    ch6 = [video_item(rec, t) for t, ch in VIDEOS.items() if ch == 6]
    section("Chapter 6 — Public Opinion", "week of Sep 21", ch6)
    ch7 = [video_item(rec, t) for t, ch in VIDEOS.items() if ch == 7]
    section("Chapter 7 — Voting &amp; Elections", "week of Sep 28",
            ch7 + scen_items("ch7_motor_voter"))

    es = rec["essay"] or "not_started"
    frq_done = es in ("graded", "accepted")
    section("Unit 2 FRQ — Equal Protection &amp; Civil Rights",
            "due Thu, Oct 8 — a Thursday!",
            [(item(frq_done, "Write and submit <b>FRQ 2</b> on the essays site "
                             "(you can revise until the due date)",
                   "in progress" if es == "draft" else ""), frq_done)])

    pct = round(100 * done_count / total) if total else 0
    parts.append(f'<div class="footer"><span><b>{done_count} of {total}</b> done</span>'
                 f'<span class="bar"><div style="width:{pct}%"></div></span>'
                 f'<span>Catch-up deadline: <b>Tue, Oct 6</b></span></div>')
    parts.append('</div>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# Output (period sort + dividers + PDFs, as in analyze_unit1)
# ---------------------------------------------------------------------------
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


_PROFILE_DIR: Path | None = None


def html_to_pdf(browser, html_path: Path, pdf_path: Path):
    """Render via headless Edge. One throwaway profile dir is reused for
    the whole run and removed best-effort — Crashpad can briefly hold
    files after exit, which made TemporaryDirectory's strict cleanup
    race and fail."""
    global _PROFILE_DIR
    import subprocess
    import tempfile
    if _PROFILE_DIR is None:
        _PROFILE_DIR = Path(tempfile.mkdtemp(prefix="edge-pdf-"))
    subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--no-first-run",
         f"--user-data-dir={_PROFILE_DIR}", f"--print-to-pdf={pdf_path}",
         "--print-to-pdf-no-header", html_path.resolve().as_uri()],
        check=True, capture_output=True, timeout=600)
    # Under OneDrive the finished PDF can take a moment to become visible
    # (Edge writes temp-then-rename; OneDrive intercepts) — poll briefly.
    import time
    for _ in range(30):
        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return
        time.sleep(0.5)
    raise RuntimeError(f"Edge exited cleanly but wrote no PDF: {pdf_path}")


def pdf_page_count(path: Path) -> int:
    import re as _re
    data = path.read_bytes()
    counts = [int(m) for m in _re.findall(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", data)]
    return max(counts) if counts else len(_re.findall(rb"/Type\s*/Page[^s]", data))


BROWSER = find_browser()
for campus, recs in sorted(by_campus.items()):
    recs = sorted(recs, key=lambda r: (period_key(r), r["last"].lower(), r["first"].lower()))
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
                f'{n} Unit 2 checklists · {TODAY}</div></div></div>')
        parts.append(sheet(r))
    head_html = (f"<!doctype html><html><head><meta charset='utf-8'><title>Unit 2 checklists — "
                 f"{campus}</title><style>{CSS}</style></head><body>")
    path = OUT_DIR / f"unit2_checklists_{campus}_{TODAY}.html"
    path.write_text(head_html + "".join(parts) + "</body></html>", encoding="utf-8")
    n_pages = len(parts)
    print(f"wrote {path.name} ({len(recs)} sheets)")

    blank = '<div class="blankpage">&nbsp;</div>'
    dup_html = OUT_DIR / f"_duplex_{campus}.html"
    dup_html.write_text(head_html + blank.join(parts) + blank + "</body></html>",
                        encoding="utf-8")
    if BROWSER:
        for src, suffix, expect in ((path, "", n_pages),
                                    (dup_html, "_duplexsafe", n_pages * 2)):
            pdf = OUT_DIR / f"unit2_checklists_{campus}_{TODAY}{suffix}.pdf"
            html_to_pdf(BROWSER, src, pdf)
            got = pdf_page_count(pdf)
            status = "OK" if got == expect else f"MISMATCH (expected {expect})"
            print(f"  {pdf.name}: {got} pages {status}")
    dup_html.unlink(missing_ok=True)

if _PROFILE_DIR is not None:
    import shutil
    shutil.rmtree(_PROFILE_DIR, ignore_errors=True)

if unmatched:
    print("UNMATCHED (not in rosetta):", sorted(unmatched))
