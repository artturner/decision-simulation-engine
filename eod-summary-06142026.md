## 1. PROJECT OVERVIEW

We are building a web-based decision simulation engine for classroom use. Teachers create classes, assign branching scenarios, direct students to join with a class code, and review completion/reflection data.

Core problem: teachers need a low-friction way to deliver interactive civic/decision scenarios and collect student work without requiring student accounts.

Intended users:
- Teachers: create classes, assign scenarios, review results.
- Students: join by class code/name, complete scenarios, submit reflections.
- Admin/content owner: imports and publishes scenarios.

Main value proposition: a classroom-ready branching scenario platform with simple student access, resumable attempts, and teacher-visible reflection/completion data.

## 2. CURRENT ARCHITECTURE

High-level architecture:
- **Frontend:** Next.js app on Vercel.
- **Backend:** FastAPI service on Railway.
- **Database:** PostgreSQL via Railway.
- **Auth:** Supabase Auth for teacher email/password login; backend verifies Supabase JWT using `JWT_SECRET`.
- **Scenario engine:** local Python packages under `packages/engine` and `packages/expr`.
- **Media:** scenario images served from configured media/R2 URLs.
- **Deployment:** GitHub push triggers Vercel/Railway deploys; Railway runs Alembic migrations via `preDeployCommand`.

Major flows:
- Public scenario flow:
  - `/scenarios/[slug]` or `/[slug]`
  - frontend calls `/api/v1/public/scenarios/{slug}`
  - student starts play, steps through scenario, submits reflection.
- Class-code student flow:
  - `/join`
  - student enters class code, selects roster name
  - frontend fetches class/status, resumes in-progress play or starts new attempt.
- Teacher setup flow:
  - `/teacher/login`
  - teacher signs in via Supabase
  - `/teacher` dashboard calls JWT-protected `/api/v1/teacher/*` endpoints.

Architectural decisions made today:
- Use **real Supabase login** instead of admin-key prototype.
- Keep students accountless for MVP.
- Use pasted roster names, one per line.
- Let teachers assign any published scenario, including legacy/global scenarios with `owner_id = null`.
- Add roll-scoped gradebook because scenario ownership should not block results for globally imported content like Liberty Park.
- Defer billing, CSV upload, best-attempt export, and student emails.

## 3. FILE & DIRECTORY STRUCTURE

```text
apps/web/
  package.json
    Adds @supabase/supabase-js dependency.
  package-lock.json
    Lockfile update for Supabase dependency.

  app/
    scenarios/
      [slug]/
        page.tsx
          Compatibility route so /scenarios/liberty-park reuses the existing scenario page.

    teacher/
      page.tsx
        Teacher dashboard for class creation, roster editing, scenario assignment, sharing class code, and viewing results.
      login/
        page.tsx
          Supabase-backed teacher sign-in/sign-up page.
        page.test.tsx
          Tests login rendering, missing Supabase config, and successful Supabase sign-in redirect.

  lib/
    auth/
      supabase.ts
        Creates/reuses the Supabase browser client from NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
    api/
      teacher.ts
        Bearer-token teacher API client for roll, assignment, scenario, and gradebook endpoints.
      teacherTypes.ts
        TypeScript mirrors of teacher API schemas.

services/api/
  app/
    api/
      v1/
        admin.py
          Adds teacher endpoints for published scenarios, roll scenario listing, and roll-scoped gradebook.
    schemas/
      admin.py
        Adds PublishedScenarioOut, RollScenarioOut, RollGradebook* schemas.

  tests/
    test_teacher_setup.py
      Backend tests for teacher scenario listing, assignment listing, ownership rules, and roll gradebook behavior.
```

Also recently added before today’s teacher flow:

```text
apps/web/
  app/
    join/
      page.tsx
        Public class-code entry flow for students.
    class/
      [rollId]/
        page.tsx
          Existing roll-link class picker updated for resume/start-another behavior.
  lib/api/
    client.ts
      Adds public class-code and student-status API calls.
    types.ts
      Adds public class-code and student-status response types.

services/api/
  alembic/versions/
    20260613_0003_class_roll_join_codes.py
      Adds class_rolls.join_code and backfills existing rolls.
  app/
    api/v1/public.py
      Adds public class-code lookup and student assignment status endpoints.
    models/user.py
      Adds join_code generation/storage to ClassRoll.
    repositories/play_repo.py
      Adds attempt summary helpers.
    repositories/roll_repo.py
      Adds join-code lookup and unique code generation.
    schemas/public.py
      Adds class-code and student-status schemas.
  tests/
    test_public_class_code.py
      Tests class-code lookup and resumable attempt behavior.
```

## 4. KEY IMPLEMENTATION DETAILS

Important backend APIs:
- `GET /api/v1/teacher/scenarios/published`
  - Lists assignable published scenarios.
  - Includes global/imported scenarios where `owner_id IS NULL`.
- `GET /api/v1/teacher/rolls/{roll_id}/scenarios`
  - Lists assigned scenarios for a teacher-owned roll.
- `POST /api/v1/teacher/rolls/{roll_id}/scenarios`
  - Assigns scenario to roll and returns enriched scenario metadata.
- `PATCH /api/v1/teacher/rolls/{roll_id}/scenarios/{scenario_id}`
  - Toggles visibility/sort order and returns enriched scenario metadata.
- `GET /api/v1/teacher/rolls/{roll_id}/scenarios/{scenario_id}/gradebook`
  - Roll-scoped results table.
  - Requires teacher owns roll and scenario is assigned to roll.
  - Does not require teacher to own the scenario.

Important frontend patterns:
- Public API client remains unauthenticated.
- Teacher API client requires Supabase access token:
  - `Authorization: Bearer <access_token>`
- `/teacher` is guarded client-side:
  - unauthenticated users redirect to `/teacher/login`.
- Roster parsing:
  - split by newline
  - trim whitespace
  - drop blank lines
  - preserve order
  - duplicate names allowed for now.

Important invariants:
- Students are still roster names, not user accounts.
- `class_rolls.join_code` is student-facing and must remain unique.
- In-progress attempt means:
  - same `class_roll_id`
  - same `learner_label`
  - same `scenario_version_id`
  - `completed = false`
- Completed attempts are not resumed.
- New attempts after completion are allowed.
- Gradebook is roll-scoped, not scenario-owner-scoped.
- Legacy/global scenarios must remain assignable.

Verification completed:
- `npm run type-check` passed.
- Teacher login Jest tests passed.
- `python -m compileall app tests` passed.
- Targeted backend pytest collected but skipped because local test Postgres was unavailable.

## 5. OUTSTANDING TODOS

1. **Commit and push current implementation.**
   - Smallest safe command: `git add apps/web services/api && git commit -m "Add teacher setup flow" && git push`.

2. **Set Vercel environment variables.**
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`

3. **Confirm Supabase URL configuration.**
   - Site URL: `https://decision-simulation-engine-seven.vercel.app`
   - Redirect URL: `https://decision-simulation-engine-seven.vercel.app/**`

4. **Fix signup confirmation redirect.**
   - Update signup call to pass `emailRedirectTo: ${window.location.origin}/teacher/login`.
   - This is not yet implemented.

5. **Redeploy Vercel and Railway from pushed code.**
   - Railway should already run Alembic migrations via `preDeployCommand`.

6. **Live-test teacher flow.**
   - Sign up/sign in.
   - Create class.
   - Paste roster.
   - Assign Liberty Park.
   - Copy instructions.
   - Join as student.
   - Start, interrupt, resume, complete, submit reflection.
   - Confirm teacher dashboard results update.

7. **Run backend tests with reachable Postgres.**
   - Start local DB or use a configured test DB.
   - Run targeted teacher/public class-code tests.

8. **Improve teacher dashboard polish.**
   - Add clearer loading/error states.
   - Add delete class if needed.
   - Add better empty-state copy.

9. **Add CSV export for gradebook.**
   - Deferred, but likely next high-value feature.

10. **Add best-attempt reporting/export.**
   - Needed before grading workflows are complete.

Blocking / clarification:
- Backend DB tests are blocked locally until Postgres is reachable.
- Need confirmation whether teacher signup should remain open to anyone or become invite/admin-controlled later.

## 6. RISKS & OPEN QUESTIONS

Risks:
- Teacher signup is currently open if Supabase allows new users. This is fine for testing but may be risky for production.
- Email confirmation currently redirects to the home page unless `emailRedirectTo` is added.
- Dashboard is client-side guarded only; backend JWT checks are the real security boundary.
- Duplicate student names are allowed, which can confuse class-code/name-picker identity.
- Gradebook currently shows basic completion/reflection data, not best attempt or scores.
- Frontend teacher dashboard is MVP-dense and may need UX refinement before paying users.
- Local backend pytest did not execute DB assertions because test Postgres was unavailable.

Open questions:
- Should teacher signups be restricted before public launch?
- Should duplicate student names require disambiguation soon?
- Should class roll assignment default all assigned scenarios to visible?
- Should teacher results show “latest attempt” or “best attempt” first once scoring exists?
- Should email confirmation redirect to `/teacher/login` or directly to `/teacher`?

Technical debt / shortcuts:
- No server-side Next middleware auth guard yet.
- No CSV roster upload yet.
- No CSV gradebook export yet.
- No organization/school abstraction yet.
- Existing legacy gradebook endpoint remains, but new UI should use roll-scoped gradebook.

## 7. REHYDRATION INSTRUCTIONS

Tomorrow’s Codex should start by reading `git status`, then inspect `apps/web/app/teacher/page.tsx`, `apps/web/app/teacher/login/page.tsx`, `apps/web/lib/api/teacher.ts`, `services/api/app/api/v1/admin.py`, and `services/api/tests/test_teacher_setup.py`. The next likely task is to implement the Supabase email confirmation redirect fix, confirm Vercel/Supabase env configuration, then guide or run a live teacher-to-student smoke test.