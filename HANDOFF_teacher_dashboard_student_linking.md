# Handoff — Teacher Dashboard, Student Linking & Name Selection

**Source project:** decision-simulation-engine · **Target:** any classroom
project needing teacher accounts, accountless students, and a gradebook (e.g.
the essay-grading project — companion doc: `HANDOFF_essay_grading.md`) ·
**Written:** 2026-07-05, verified against current code.

---

## 1. TL;DR — what this system is

A classroom access model with exactly **one kind of account: the teacher's**.
Students never register, never log in, never have passwords. A student is
identified by *(class roll, chosen name)*:

1. Teacher signs in (Supabase Auth) and creates a **class roll** — a named,
   reusable list of student names with an auto-generated 6-character
   **join code**.
2. Teacher assigns work to the roll (per-assignment visibility + ordering).
3. Student goes to `/join`, types the class code, **picks their name from a
   dropdown** of the roster, and sees their assignments with live status
   (Resume / Start / Start another attempt).
4. Everything the student does is recorded against `(class_roll_id,
   learner_label)`; the server validates the name against the roster on every
   session start.
5. The teacher dashboard shows a **roster-complete gradebook** (every student
   appears, even those who never started) with CSV export.

This shipped for scenario plays; §7 maps the concepts to essay submissions.

---

## 2. The load-bearing design decision: no student accounts

**Identity = a `(class_roll_id, learner_label)` pair, where `learner_label`
must exactly match a name on the teacher's roster.** Chosen because student
accounts add registration, email verification, password resets, and parental
consent friction that a single-teacher/small-school deployment doesn't need.

Consequences you must accept (all fine in practice for classroom use):

- **Trust model is classroom-level.** Any student who knows the code can pick
  any name. Acceptable where the teacher knows the room; not for high-stakes
  anonymous assessment. (Mitigation if ever needed: per-student PINs — the
  schema extends naturally.)
- **The name string IS the foreign key.** Renaming a student on the roster
  does NOT retroactively relabel their existing work — old rows keep the old
  string and silently drop off the roster-keyed gradebook. Either warn on
  rename, or (better, in the new project) relabel existing rows in the same
  transaction.
- **Duplicate names on one roll merge identities.** Enforce uniqueness within
  a roll at creation time ("Last, First" + middle initial when needed). The
  source project does not enforce this — do it in yours.
- **Free-text escape hatch:** direct links still work for open/public use
  with a typed name and `class_roll_id = NULL`. Null-roll work is *excluded
  from the gradebook* — that's the feature: teachers only see roster-validated
  rows.

---

## 3. Data model (4 pieces — copy-ready)

```
users
  id UUID PK            -- equals the Supabase Auth "sub" claim (see §4)
  email TEXT UNIQUE
  role ENUM(teacher, admin)
  created_at

class_rolls
  id UUID PK
  owner_id UUID FK→users ON DELETE CASCADE
  name TEXT                      -- "Period 3, Spring 2026"
  join_code VARCHAR(16) UNIQUE INDEXED   -- 6 chars, A–Z + 0–9
  student_names JSONB            -- ordered list of canonical names
  created_at

scenario_roll_assignments        -- rename to e.g. assignment_roll_links
  id UUID PK
  scenario_id FK  / class_roll_id FK   (CASCADE both ways)
  visible BOOLEAN DEFAULT false  -- per-assignment, per-class visibility
  sort_order INT NULL            -- teacher-controlled display order
  UNIQUE(scenario_id, class_roll_id)

plays (≈ "submissions" in your project)
  learner_label TEXT             -- the chosen roster name (or free text)
  class_roll_id UUID FK NULL     -- NULL = direct link, outside gradebook
  ... work-specific columns
```

Design points that proved right:

- `student_names` as a JSONB array (not a table) — rosters are pasted, edited
  wholesale, and small; a join table buys nothing at this scale.
- **Visibility lives on the junction row**, not the scenario: the same
  assignment can be live for Period 3 and hidden for Period 5.
- Join code generated with `secrets.choice` over `A-Z0-9`, length 6, unique
  index (collisions effectively never; the DB constraint is the backstop):

```python
JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits
def generate_join_code() -> str:
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(6))
```

---

## 4. Teacher auth: Supabase JWT → local user row (no webhooks)

Frontend: Supabase Auth (`signInWithPassword` / `signUp`) at
`/teacher/login`; the API client sends the session's access token as a Bearer
header. Backend never talks to Supabase except to fetch public keys.

The FastAPI dependency (`app/api/deps.py`, copy nearly verbatim):

1. **Verify via JWKS**: fetch `settings.supabase_jwks_url` (cached with
   `lru_cache`), match the token's `kid`, allow only `ES256`/`RS256`, require
   header alg == key alg, `verify_aud=False`.
2. **Legacy fallback** to HS256 with a shared `JWT_SECRET` (kept for local dev
   and key-migration windows; refuse if the secret is still the placeholder).
3. **First-request upsert**: `sub` claim = user UUID = local PK. If no `users`
   row exists, create it (`role=teacher`); if the email changed in Supabase,
   sync it. **This removes any need for auth webhooks** — the local table
   lazily mirrors Supabase.

```python
user = db.get(User, uuid.UUID(payload["sub"]))
if user is None:
    user = User(id=user_id, email=email, role=UserRole.teacher)
    db.add(user); db.commit()
```

Every teacher endpoint takes `current_user: User = Depends(get_current_user)`
and scopes queries by `owner_id == current_user.id`. There is also a separate
legacy `X-Admin-Key` header dependency for machine/admin endpoints (content
import) — keep the two auth paths separate.

Gotchas: JWKS fetch failure must map to 401 (not 500); the `lru_cache` means
a Supabase key rotation needs a process restart (fine at this scale — or add
TTL in the new project).

---

## 5. Student linking & name selection (the `/join` flow)

**One page, three steps, no client-side persistence.** All state a returning
student needs is derived server-side from `(roll, name)` — closing the tab
loses nothing.

```
/join
 1. type class code  → normalize .trim().toUpperCase()
    GET /public/classes/code/{join_code}
      → { roll_id, roll_name, join_code, student_names[], scenarios[] }  (404 → "check the code")
 2. pick name from <select> of student_names
    GET /public/classes/code/{join_code}/students/{student_name}
      → per assignment: { title, sort_order,
          in_progress_play_id,        -- resume target
          submitted_count,            -- prior completed attempts
          latest_submitted_play_id }
      (422 if the name isn't on the roster)
 3. click through:
      in_progress_play_id present → route straight to it ("Resume")
      else POST /plays/start { version, learner_label, class_roll_id } ("Start"
           or "Start another attempt" when submitted_count > 0)
```

Server-side rules that make this trustworthy:

- **Roster validation on start** (the only write): if `class_roll_id` is
  provided, `learner_label` must be an exact member of
  `roll.student_names`, else 422. Nothing else about the student is trusted.
- **Resume is a server lookup** (`find_in_progress(roll, label, version)`),
  not a cookie — students hop devices freely.
- **Multiple attempts allowed, all recorded, none blocked**; the gradebook
  picks the best (§6).
- A UUID variant `GET /public/class/{roll_id}` serves the same picker for
  teacher-shared direct links; the code path is friendlier to type.

Dashboard side: a **SharePanel** shows the class code plus a copy-paste
instruction block ("go to `<site>/join`, enter code `ABC123`, pick your
name") — one button, `navigator.clipboard`. This tiny panel is what makes
classroom rollout work; don't skip it.

---

## 6. Teacher dashboard & gradebook semantics

Single Next.js client page (`apps/web/app/teacher/page.tsx`), master-detail,
React Query for all data; ~5 components worth porting as a set:

| panel | behavior worth keeping |
|---|---|
| **Classes** (sidebar) | list rolls, select one; create form |
| **ClassEditor** | roll name + roster as a **one-name-per-line textarea** (`parseRoster` splits/trims/drops empties). Teachers paste from Excel; never make them add names one-by-one. |
| **SharePanel** | join code + copy-instructions button (§5) |
| **ScenarioAssignments** | dropdown of *published* content → assign to roll; per-row `visible` toggle and sort order (junction-row updates) |
| **ResultsPanel** | roll+assignment gradebook table + CSV export button |

**Gradebook contract** (`GET /teacher/rolls/{roll}/scenarios/{id}/gradebook`
+ `.csv`) — the semantics are the valuable part:

- **Roster-complete**: one row per roster name, always — status is
  `not_started | in_progress | submitted`. Teachers grade by scanning for
  gaps, so absent students must be visible rows, not missing rows.
- **Best attempt = highest `grade_total`, ties → most recent.** All attempts
  remain queryable; the summary row shows the best.
- Only roll-linked work counts (`class_roll_id IS NOT NULL`) — free-text
  plays never pollute the gradebook.
- Row includes the AI-grade fields (total, accepted, `needs_human_review`,
  coaching feedback) — this is where the grading handoff's review flag
  surfaces to the teacher.
- **CSV**: fixed columns + **dynamically discovered response columns** (union
  of response keys across students, in first-seen order), blank cells for
  not-started students. Filename carries roll + assignment ids.

Ownership: every teacher endpoint verifies the roll (and content, where
relevant) belongs to `current_user` before answering — do this in a shared
helper, it's the easiest thing to forget on a new endpoint.

---

## 7. Mapping to an essay-grading project

| here | there |
|---|---|
| scenario / published version | assignment (essay prompt + rubric version) |
| `scenario_roll_assignments` | `assignment_roll_links` (same columns) |
| play (`learner_label`, `class_roll_id`) | essay submission |
| `in_progress_play_id` → Resume | draft-in-progress → "Continue writing" |
| `submitted_count` / best attempt | prior submissions / best grade (pairs with the redo-cap loop in `HANDOFF_essay_grading.md`) |
| play outcome column | grade columns from the grading handoff |

Transfers verbatim: users table + JWKS dependency, class_rolls + join codes,
the `/join` three-step UX, roster validation on submission start, gradebook
semantics, CSV export. The only genuinely scenario-specific code is the play
engine itself — which you're replacing with essay submission anyway.

## 8. Porting checklist

1. Tables: `users`, `class_rolls` (+ join-code generator), junction table,
   `class_roll_id`/`learner_label` on your submission row.
2. Copy `app/api/deps.py` (JWKS verify + first-login upsert); wire Supabase
   env (`supabase_jwks_url`, legacy `JWT_SECRET` fallback).
3. Public endpoints: picker by code, per-student status, submission start
   with roster validation (404 / 422 exactly as §5).
4. Teacher endpoints: rolls CRUD, assignment CRUD (visible/sort), gradebook +
   CSV — every one scoped to `owner_id`.
5. Frontend: `/join` page, `/teacher/login` (Supabase), dashboard panels
   (roster textarea! share panel!).
6. New-project improvements to make on day one: enforce unique names within a
   roll; relabel existing submissions when a roster name is edited; TTL on
   the JWKS cache.

## 9. Source files to pull from this repo

- `services/api/app/models/user.py` — User, ClassRoll, join-code generator
- `services/api/app/models/assignment.py` — the junction table
- `services/api/app/api/deps.py` — JWKS auth + first-login upsert (copy whole)
- `services/api/app/api/v1/public.py` — picker/status/start endpoints (§5)
- `services/api/app/api/v1/admin.py` — teacher router: rolls, assignments,
  gradebook + CSV (`_build_roll_gradebook`)
- `apps/web/app/join/page.tsx` — the whole student flow in one small file
- `apps/web/app/teacher/page.tsx` + `apps/web/app/teacher/login/page.tsx`
- `apps/web/lib/auth/supabase.ts`, `apps/web/lib/api/client.ts` — token plumbing
- Tests: `services/api/tests/test_public_class_code.py`,
  `test_teacher_auth_jwks.py`, `test_teacher_setup.py`, `test_admin_*` —
  port alongside the code they cover.
