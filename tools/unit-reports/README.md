# Unit performance reports

Pulls rich per-assignment data from all three apps and builds a multi-dimensional
unit summary: printable per-student sheets, a teacher monitoring report, and a
master CSV. Built for Unit 1 (Ch 1–3); clone the two scripts and edit the
`VIDEOS` / `SCENARIOS` lists and the essay-title filter for later units.

```
python fetch_unit1.py      # raw gradebooks + video item stats -> unit1_raw/
python analyze_unit1.py    # reports -> OneDrive "2026 Fall/unit1-reports/"

python fetch_unit2.py      # Unit 2 status + claim-code pickup -> unit2_raw/
python checklist_unit2.py  # per-student printable checklists (live progress
                           #  pre-checked; unclaimed students see their access
                           #  code) -> OneDrive "2026 Fall/unit2-checklists/"
```

```
python student_report.py                  # pick a student -> one-page PDF
python student_report.py --student garcia # start with a name filter
python student_report.py --refresh        # pull live grades first
```

`student_report.py` builds a one-page, front-only progress report for one
student (FERPA banner, current weighted grade, every assignment's grade,
progress by type and overall on the 60 items, and ahead / on track /
behind against the pacing-guide target dates) into OneDrive
`2026 Fall/student-reports/<Last>_<First>_<date>.pdf`. Grades come from the
newest `all_grades_import_*.csv` (`--refresh` runs `export_all_grades.py`
first). Target dates, item types and weights live in the shared course plan
`services/api/app/data/course_plan_fall2026.json` — the same file the live
student dashboard (`/me`) uses, so the two always agree. The report refuses to
run if the plan drifts from the D2L template.

Re-run both unit-2 scripts right before printing so the pre-checked marks
reflect current progress.

Student summaries come out period-sorted (divider page per period) as HTML
plus print-ready PDFs rendered with headless Edge — every student fits exactly
one Letter page (verified by page count), browser headers suppressed via the
zero-@page-margin trick. The `*_duplexsafe.pdf` variant puts a blank page
behind every page so a copier stuck on 2-sided printing still yields
front-only sheets; use the plain PDF when printing single-sided.

Both reuse auth, roster matching, and the video grade rule from
`../d2l-import/` (credentials in that folder's `.env`, roster from the
rosetta stone).

What it adds over the D2L all-grades export (one number per assignment):

- **Videos**: status / first-try accuracy / attempts per question, plus
  per-question item analysis (miss rate, which wrong option students pick).
- **Scenarios**: outcome/path reached, reflection grade, plays used,
  needs-human-review flags, played-but-no-reflection detection.
- **Essay FRQ**: rubric dimension levels + points, on-time, word count,
  revision attempts, low-effort flags.
- Course-weighted unit composite (20/35/45) with missing-as-zero, missing-item
  lists, and tiered watchlists.

Network note: on the district network the Palo Alto firewall SSL-intercepts
`videos.cruxlabs.academy`, which breaks Python cert verification. The fetch
script therefore talks to the same service via its Railway domain
`app-production-a23d.up.railway.app`, which is not intercepted.

## Emailing students their progress + access code

```
python fetch_unit2.py                                   # refresh live data
python email_merge_unit2.py --emails <D2L export with Email>.csv
python email_merge_unit2.py --emails ... --test-to Arthur.Turner@etamu.edu   # 3-row test file
```

Writes a mail-merge file (one row per student: ETAMU email, access code,
Unit 2 summary from the same rules as the checklists, and a ready
`Subject` / `BodyHTML` / `BodyText`) to OneDrive `2026 Fall/email-merge/`.
Nothing is sent by the script. Send from your own ETAMU mailbox so the mail
comes from a trusted university sender:

**Power Automate (browser only)** — copy the `.xlsx` into your **ETAMU**
OneDrive, then at make.powerautomate.com (signed in with ETAMU) create an
*Instant cloud flow*:
1. *Excel Online (Business) → List rows present in a table* — your file,
   table `Merge`.
2. *Apply to each* over `value`; under its Settings set concurrency **off**.
3. Inside it: *Office 365 Outlook → Send an email (V2)* — To = `Email`,
   Subject = `Subject`, Body = `BodyHTML` (switch the body to code view `</>`
   first so the HTML is used).
4. *Delay* 2 seconds (keeps well under Exchange's 30 messages/minute).

Run it on the `_TEST` file first and check the result in your inbox.
**Word mail merge** needs desktop (classic) Outlook; use the `.csv`.

The files contain access codes and grades — delete them after sending.
