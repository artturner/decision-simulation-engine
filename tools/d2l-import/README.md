# D2L Grade Import Prep

Converts grade exports from the three apps (video quiz, essay grader, scenario
engine) into D2L-ready import CSVs keyed on ETAMU OrgDefinedId.

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
