# D2L Grade Import Prep

Two tools, keyed on ETAMU OrgDefinedId:

- **`export_all_grades.py`** — fetches every grade from all three production
  apps itself and writes ONE wide import CSV covering every assignment.
- **`d2l_prep.py`** — the original one-assignment tool: converts a manually
  downloaded app export into a single-column import CSV.

## All-grades export (the weekly workflow)

```
python export_all_grades.py            # fetch everything, write the CSV
python export_all_grades.py --check    # fetch + report only, write nothing
python export_all_grades.py --discover # snapshot live titles into assignments_map.csv
```

One-time setup: `copy .env.example .env` and fill in your teacher logins
(Supabase email/password for scenarios+essays; video credentials are read
from the video-quiz repo's `.env` automatically if left blank).

What it does:

1. Logs in headlessly — Supabase password grant for the scenarios and essays
   APIs (same token works for both), cookie login for the video-quiz admin API.
2. Fans out over every class × assignment gradebook in each app and merges
   grades across classes (same student in two classes: best grade wins,
   conflict reported).
3. Matches assignment titles to the template's D2L grade item names —
   normalized exact match by default (punctuation/case-insensitive), with
   `assignments_map.csv` (`d2l_item,source,app_title`) as the override for
   anything that doesn't line up. `--discover` writes that file from live
   titles so you can see and edit the matching. A map row with a blank
   `app_title` means "leave this column alone".
4. Matches student names against the rosetta stone (same rules as d2l_prep,
   never interactive: fuzzy candidates are reported, not applied) and writes
   `all_grades_import_<date>.csv` to `OUT_DIR` (default: the OneDrive
   `2026 Fall\grade-imports` folder) with the exact template columns.

Import that one file into D2L. Blank cells are skipped by D2L, so a partial
export can never wipe existing grades; re-importing the same file is
idempotent. Grade rules live in `d2l_prep.py` (`video_grade()`); scenario
`grade_total` and essay `effective_total` pass through unchanged.

The template header comes from `all_grade_import_template.csv` (a D2L
"all grades" export with the student rows deleted). When you add a grade
item in D2L, re-export a fresh template over that file.

To run it weekly (Sunday 7am, on top of running it on demand whenever):

```
schtasks /Create /TN "D2L all-grades export" /SC WEEKLY /D SUN /ST 07:00 /TR "cmd /c cd /d C:\Users\arttu\decision-simulation-engine\tools\d2l-import && python export_all_grades.py >> export.log 2>&1"
```

Keep this local — the output and the rosetta stone hold student PII, so this
job does not belong in GitHub Actions.

## Single-assignment prep (original tool)

```
python d2l_prep.py <export.csv>
```

The tool auto-detects the export type from its columns, prompts for the
assignment name (must exactly match the D2L grade item name), matches student
names against the rosetta stone, and writes `<Assignment>_import.csv` next to
the export with columns:

```
OrgDefinedId,Last Name,First Name,<Assignment> Points Grade,End-of-Line Indicator
```

## Rosetta stone

`C:\Users\arttu\OneDrive - Grand Prairie ISD\2026 Fall\rosetta_stone.csv`

Columns: `OrgDefinedId` (ETAMU), `Last Name`, `First Name`, `HS Student ID`,
`Campus` (SGPHS/GPHS), `Aliases` (semicolon-separated alternate first names,
e.g. `Gwen` for Gwendolyn). Add GPHS students as new rows when that roster
is available.

## Matching

Exact normalized match (case, accents, hyphens, periods ignored) -> alias
column -> fuzzy match with y/N confirmation. Unmatched names with grades are
reported loudly and excluded — fix by adding an alias and re-running.

## Grades

- **Video**: `75 + 25 * first_try_correct / total_questions` for students
  who completed the video, else no grade. Both export generations are
  supported: the post-cutover format (`student_name`, `status`,
  `total_questions`) reads the question count per row; the pre-cutover
  format (`student`, `completed`) derives it (max `questions_answered`)
  and confirms at the prompt. The rule lives in `video_grade()` at the
  top of the script — edit there when it changes.
- **Scenario** (`grade_total`) and **essay** (`effective_total`): pass
  through as exported.
- Students without a grade are omitted (D2L leaves them unchanged).

## Flags

`--assignment NAME` skip the prompt · `--total N` override video question
count · `--no-input` never prompt (fuzzy matches reported, not applied) ·
`--rosetta PATH` / `--out PATH` overrides · `--force` overwrite output.
