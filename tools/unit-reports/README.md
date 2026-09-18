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
