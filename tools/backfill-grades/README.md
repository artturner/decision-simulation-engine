# Reflection grade backfill

When AI grading is unavailable — `ANTHROPIC_API_KEY` unset, or the teacher's
monthly quota (`AI_GRADER_MONTHLY_TEACHER_LIMIT`, counted in `grading_calls`)
is exhausted — the student reflection form silently falls back to plain
submission: answers are stored, but no grade or coaching is produced and the
gradebook shows "—". This tool finds those stored-but-ungraded reflections and
grades them retroactively.

It is a pure API client (no database access): it walks every class gradebook
via the teacher API, then re-posts each stored reflection to the public grade
endpoint `POST /public/plays/{id}/reflection/grade`, so the grade is produced
by exactly the same server code path a live student submission uses. Grades
land as attempt 1; students can still revise and accept afterwards.

## Usage

```
python backfill_reflection_grades.py                 # dry run: list candidates
python backfill_reflection_grades.py --apply         # grade them
python backfill_reflection_grades.py --since 2026-09-01 --apply
python backfill_reflection_grades.py --roll "2305" --scenario "Whistle"
```

- Credentials: reuses `../d2l-import/.env` (`SUPABASE_TEACHER_EMAIL` /
  `SUPABASE_TEACHER_PASSWORD`); override with `--env`.
- Safe to re-run: already-graded and accepted reflections are filtered out, so
  a re-run only retries failures.
- Each grading call costs about 1 cent in API tokens and counts against the
  monthly quota; the run aborts immediately if the server reports grading
  unavailable (HTTP 503).
- Paced at one call per 6.5 s to stay under the endpoint's 10/min rate limit.
- "Unmatched" plays (student renamed after playing) are only counted — restore
  the old roster spelling to re-link them, then re-run.

Check quota usage: `GET /api/v1/admin/grading-usage` with the `X-Admin-Key`
header (key in the Railway service variables).
