# Handoff — Porting the AI Grading Process to Essay Grading

**Source project:** decision-simulation-engine (grades post-scenario student
*reflections*) · **Target:** a new project grading student *essays* ·
**Written:** 2026-07-05

This document is self-contained: it explains the proven grading architecture,
the design decisions and *why* they were made, the exact API mechanics, and
what to change for essays. Source files worth copying are listed at the end.

---

## 1. What you are porting (TL;DR)

A student-facing AI grading loop with these properties, all battle-tested in
production for reflection grading:

1. **The AI never does arithmetic.** It assigns an anchored *level* per rubric
   dimension (`full | solid | minimal | low_effort`); the server converts
   levels to points deterministically. Totals are always correct and auditable.
2. **Grade + coach, then let the student revise.** Grading returns warm,
   specific coaching feedback (never mentioning points). The student may revise
   and re-grade up to a cap (3), then *accept* to lock the grade — or the cap
   forces acceptance of the last score. This turns grading into a revision
   loop, which is the pedagogical point.
3. **Effort-based, never outcome-based.** The rubric rewards sincere engagement
   and reasoning, explicitly refuses to punish unconventional opinions, and has
   a **low-effort gate** ("idk", one-worders, prompt copy-paste → floor score).
4. **Structured output, one call, no parsing games.** The Anthropic API is
   constrained to a JSON schema, so the response is always machine-readable.
5. **Graceful degradation.** No API key → the feature turns itself off (HTTP
   503; the frontend falls back to plain submission). API failure → HTTP 502,
   student's work is never lost.
6. **Human-in-the-loop escape hatch.** The model sets `needs_human_review` +
   reason for borderline, distressed, or AI-generated-looking answers; the
   teacher dashboard surfaces it.

---

## 2. Architecture (small on purpose)

```
student submits essay ──► POST /…/grade ──► ai_grader.grade(…)  (one module)
                              │                    │
                              │        Anthropic messages.create
                              │        (rubric system prompt + JSON schema)
                              │                    │
                              ▼                    ▼
                    persist: total, breakdown JSONB, feedback,
                    attempts, model, graded_at
                              │
             student revises & re-grades (≤ cap) … or
                    POST /…/accept  → locks the row (idempotent)
```

Three pieces, ~500 lines total in the source project:

- **Grader service** (`services/api/app/services/ai_grader.py`) — pure
  function: inputs → `GradeResult` dataclass. No DB, no HTTP. Copy this file
  and edit the rubric/dimensions; the mechanics port unchanged.
- **Two endpoints** (`services/api/app/api/v1/public.py`, `…/grade` and
  `…/accept`) — enforce the state machine: completed-work-only, attempt cap,
  accepted = locked (409), unavailable = 503, API failure = 502.
- **A few columns** on the submission row (see §6).

Deliberately deferred in v1 (still sensible defaults): teacher manual score
override (view-only dashboard instead), per-assignment rubric overrides
(single global rubric), async/queued grading (calls take ~2–5 s inline).

---

## 3. Design decisions that must survive the port (and why)

| Decision | Why it matters |
|---|---|
| **Levels, not numbers, from the AI** | Models miscompute totals and drift on numeric scales. Anchored levels (`full/solid/minimal/low_effort`) with server-side `LEVEL_FRACTION` mapping (1.0 / 0.8 / 0.4 / 0.0) make scores deterministic, re-gradable, and rubric-tunable without re-prompting. |
| **Per-dimension `evidence` quote** | The model must justify each level with a one-sentence quote/paraphrase. This is your audit trail for disputes and your teacher-facing explanation. |
| **Low-effort gate as an ABSOLUTE RULE** | Without it, models award sympathy points to non-answers. State it bluntly in the system prompt with concrete examples of non-answers. |
| **Coaching feedback that never mentions scores** | Students act on "here's how to deepen your argument", not "you got 17/25". Keeping numbers out of the prose also prevents contradiction between prose and server-computed totals. |
| **Redo cap + accept-lock** | Unlimited re-grading invites prompt-gaming and cost blowups; no redo kills the revision loop. Cap of 3 worked well. Submission is **mutable until accepted, then locked**; "best attempt" (highest total) is what reports/gradebooks show. |
| **Server-side "completion" points** | In the source, 20/100 points are for finishing the scenario — computed from server state, never by the AI. For essays, the analog is submission/on-time/word-count-met: anything checkable in code should be scored in code. |
| **Optionality via the API key** | `ai_grading_enabled = bool(ANTHROPIC_API_KEY)`. Lets you deploy the feature dark and turn it on per environment. |

---

## 4. The exact API call pattern (copy this)

Model: `claude-sonnet-4-6` (config: `AI_GRADER_MODEL`) — fast/cheap tier is
the right choice; grading is a constrained judgment task, not generation.
`max_tokens=1024` (output is a small JSON object regardless of essay length).

```python
client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
response = client.messages.create(
    model=settings.AI_GRADER_MODEL,
    max_tokens=1024,
    system=RUBRIC,                       # the full rubric IS the system prompt
    messages=[{"role": "user", "content": user_prompt}],  # the student work
    extra_body={
        "thinking": {"type": "disabled"},               # fast + cheap
        "output_config": {
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}
        },
    },
)
text = next((b.text for b in response.content if b.type == "text"), None)
data = json.loads(text)
```

Notes learned the hard way:

- `extra_body` keeps the request shape independent of the installed SDK
  version's typed kwargs — it survives SDK upgrades.
- The JSON schema uses **flat keys** (`thesis_level`, `thesis_evidence`, …)
  with `"additionalProperties": false` and every key `required` — nested
  optionality invites omissions.
- Defensive parse anyway: unknown level → treat as `low_effort` (fail-closed),
  missing evidence → empty string. Never 500 on a weird-but-parseable reply.
- Wrap ALL API exceptions into your own `GradingError`; map
  `GradingUnavailable` → 503 (feature off) and `GradingError` → 502 (retry
  later) at the endpoint. The student's text is persisted *before* the call.

---

## 5. What changes for essays

**Rubric dimensions.** Replace the reflection trio (engagement 25 / reasoning
30 / insight 25 + completion 20) with essay dimensions. A starting point that
preserves the level machinery:

```python
DIMENSION_POINTS = {
    "thesis_and_focus":   20,   # clear claim, stays on prompt
    "evidence_and_support": 30, # specific, relevant, explained — not just quoted
    "analysis_and_reasoning": 30, # why the evidence matters; counterpoints
    "organization_and_clarity": 20, # structure, transitions, readable prose
}
```

Anchor each level with one concrete sentence per dimension (what does "full"
look like vs "minimal") — the anchors, not the point values, are what make
grading consistent. Keep the low-effort gate verbatim.

**Decide what replaces "completion" points.** Score in code whatever code can
check: submitted on time, meets length requirement, includes required sections.
Keep the AI out of it.

**Outcome-neutrality translates to prompt-neutrality.** The source rubric's
"never consider whether the outcome was good or bad" becomes: *never grade the
position taken, only the quality of its defense*. Say it as an ABSOLUTE RULE —
this matters most for persuasive/opinion essays.

**Input assembly.** The source builds a user prompt of Q&A pairs plus the
student's decision path (context for judging specificity). For essays:
assignment prompt + any teacher instructions + the essay text. Essays are
longer but still trivial for the context window (a 2,000-word essay ≈ 2,600
tokens); no chunking needed. Grade the essay as ONE call — per-dimension calls
cost more and lose whole-text coherence.

**Make the rubric a parameter from day one.** The source hardcoded one global
rubric (`DEFAULT_RUBRIC`) and deferred per-scenario overrides; for essays,
per-assignment rubrics are the obvious near-term need. Pass
`(rubric_text, dimension_points)` into the grader instead of importing
constants — the rest of the machinery doesn't care.

**AI-written-essay detection.** The `needs_human_review` flag already asks the
model to flag "looks AI-generated". For essays this will fire more and matters
more — surface it prominently to teachers, and treat it as *route to human*,
never as an automatic penalty (false positives are real).

## 5a. Optional reliability upgrade for high-stakes grades

A separate workstream in the source project proved that **a single LLM
judgment is noisy — run-to-run variance is real — and that K-sample majority
voting stabilizes it** (see `scenario_iterations/stabilize_judge.py`: judge
K=5 times, act only on the majority verdict; one-off verdicts are noise).

Reflection grading skipped this (low stakes, redo loop self-corrects). For
essay grades that count toward report cards, consider: run the grading call
K=3 times and take the **modal level per dimension** (ties → the middle
level, or route to human review). Triples the per-essay cost, still cheap in
absolute terms, and removes most grade lottery. Implement as a wrapper around
the single-call function so it stays optional per assignment.

---

## 6. Persistence (columns to add to your submission row)

From the source's migration (`0004_add_reflection_grades`), adapted names:

| column | type | purpose |
|---|---|---|
| `grade_total` | int, nullable | server-computed total |
| `grade_breakdown` | JSONB | per-dimension `{level, points, max_points, evidence}` + `needs_human_review`, `review_reason`, `low_effort_flags` |
| `feedback` | text | student-facing coaching |
| `graded_at` | timestamptz | |
| `grader_model` | text | which model graded (audit/regrade) |
| `grade_attempts` | int, default 0 | enforces the redo cap |
| `accepted` / `accepted_at` | bool / timestamptz | the lock |

The JSONB breakdown means new dimensions never need a migration.

**Endpoint state machine** (port as-is): grade requires completed/submitted
work → 409 if `accepted` → if `attempts >= cap`, return last grade with
`can_redo=false` (no new API call) → upsert text, call grader, save, return
`{total, dimensions, feedback, attempts_used, attempts_remaining, can_redo,
accepted}`. Accept endpoint is idempotent.

**Frontend pattern** (source: `apps/web/components/ReflectionForm.tsx`):
two-phase form — submit-for-feedback shows score + coaching + "Revise" /
"Accept my grade" buttons; disable revise when `can_redo=false`; a 503 from
the grade endpoint silently downgrades to the plain submit flow.

---

## 7. Ops & cost

- **Env:** `ANTHROPIC_API_KEY` (empty = feature off), `AI_GRADER_MODEL`
  (default `claude-sonnet-4-6`), `AI_GRADER_MAX_ATTEMPTS` (default 3).
- **Cost scale:** one grading call ≈ (rubric ~700 tokens + essay) input,
  ~400 tokens output, on the Sonnet tier with thinking disabled — small even
  at K=3 voting; check current per-token pricing against your volumes.
- **Latency:** 2–5 s inline was fine for reflections; essays (longer input)
  will be similar since output is fixed-size. If you queue it, keep the
  synchronous path for the student-facing revise loop — waiting 3 s for
  coaching is fine; polling for it is worse.
- **Testing:** the grader is a pure function — unit-test `_build_result`
  (level→points math, low-effort flags, unknown-level fail-closed) with no
  network. Endpoint tests stub the grader. The source's tests are in
  `services/api/tests/` (reflection grading) as a template.

---

## 8. Porting checklist

1. Copy `ai_grader.py`; rename dimensions; rewrite `DEFAULT_RUBRIC` anchors
   for essays; make `(rubric, dimension_points)` parameters.
2. Decide the code-scored component (on-time/length) — keep it out of the AI.
3. Copy the two endpoints' state machine + error mapping (503/502/409/cap).
4. Add the grade columns (JSONB breakdown) to your submission model.
5. Port the two-phase frontend form + graceful 503 fallback.
6. Unit tests: level math, low-effort gate, cap behavior, accept-lock.
7. Pilot with `needs_human_review` routing visible to teachers from day one.
8. (High-stakes only) add the K=3 modal-level voting wrapper (§5a).

## 9. Source files to pull from this repo

- `services/api/app/services/ai_grader.py` — the whole grading engine
- `services/api/app/api/v1/public.py` — `…/reflection/grade` + `…/reflection/accept`
- `services/api/app/models/play.py` — reflection/grade columns (`PlayReflection`)
- `services/api/app/core/config.py` — the three settings + `ai_grading_enabled`
- `apps/web/components/ReflectionForm.tsx` — two-phase student UX
- `scenario_iterations/stabilize_judge.py` — K-vote stabilization pattern (§5a)
- Memory/design log: grading decisions were user-confirmed on 2026-06-22
  (outcome-neutral rubric, cap 3, view-only teacher override, global rubric).
