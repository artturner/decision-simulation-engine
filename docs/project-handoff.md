# Decision Simulation Engine Project Handoff

Last updated: 2026-06-17

## Start Here

This project is a classroom-ready branching scenario platform. Teachers sign in, create class rolls, assign published scenarios, share a class code, and review student completion/reflection results. Students do not need accounts; they enter a class code, choose their roster name, start or resume a scenario, complete it, and submit reflections.

Current live MVP status: the core classroom workflow is deployed and verified. The next likely product goal is paid teacher entitlement with a payment processor.

## Current Product State

Verified live:

- Teacher sign-up/sign-in works through Supabase Auth.
- Teacher dashboard loads for authenticated teachers.
- Teacher can create a class by pasting one student name per line.
- Class roll gets a short join code.
- Teacher can assign Liberty Park or other published scenarios.
- Student can join at `/join` with class code and roster name.
- Student can resume an in-progress attempt.
- Student can submit multiple attempts.
- Completed reflection carries the selected roster name into the reflection data.
- Teacher dashboard shows status, attempts, best-attempt data, and reflection responses.
- Teacher can export a gradebook CSV.

Current best-attempt convention:

- `best_attempt` means latest completed attempt.
- There is no score model yet, so “best” is not calculated from performance.

## Architecture

Frontend:

- Next.js app in `apps/web`.
- Deployed to Vercel at `https://decision-simulation-engine-seven.vercel.app`.
- Uses `@supabase/supabase-js` for teacher auth.
- Public student routes remain accountless.

Backend:

- FastAPI service in `services/api`.
- Deployed to Railway at `https://decision-simulation-engine-production.up.railway.app`.
- PostgreSQL database on Railway.
- Alembic migrations run through Railway `preDeployCommand`.

Auth:

- Supabase Auth handles teacher email/password login.
- Backend verifies Supabase access tokens through JWKS.
- Railway backend env var required:
  - `SUPABASE_URL=https://ldtrukooegjbyrlopcfi.supabase.co`
- Legacy `JWT_SECRET` is only a fallback when explicitly set to a non-default value.

Deployment:

- GitHub push to `master` triggers Vercel and Railway deploys.
- Latest verified commit:
  - `ced6995 Add gradebook CSV export and best attempts`

## Important URLs And Env Vars

Live frontend:

- `https://decision-simulation-engine-seven.vercel.app`

Live backend:

- `https://decision-simulation-engine-production.up.railway.app`

Supabase project URL:

- `https://ldtrukooegjbyrlopcfi.supabase.co`

Vercel env vars:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

Railway env vars:

- `DATABASE_URL`
- `SUPABASE_URL`
- `ADMIN_API_KEY`
- Media/R2 settings as already configured.

Supabase Auth URL settings:

- Site URL: `https://decision-simulation-engine-seven.vercel.app`
- Redirect URL: `https://decision-simulation-engine-seven.vercel.app/**`
- Redirect URL: `https://decision-simulation-engine-seven.vercel.app`

## Key Files

Frontend:

- `apps/web/app/teacher/login/page.tsx`
  - Supabase sign-in/sign-up page.
  - Signup uses `emailRedirectTo` so email confirmation returns to `/teacher/login`.

- `apps/web/app/teacher/page.tsx`
  - Teacher dashboard.
  - Class creation/editing, roster paste, scenario assignment, student instructions, results table, CSV export.

- `apps/web/app/join/page.tsx`
  - Student class-code entry flow.

- `apps/web/app/class/[rollId]/page.tsx`
  - Backward-compatible roll-id class picker.

- `apps/web/app/[slug]/play/[playId]/page.tsx`
  - Scenario play page.

- `apps/web/app/[slug]/complete/[playId]/page.tsx`
  - Reflection completion page.
  - Prefills student name from `play.learner_label`.

- `apps/web/lib/api/teacher.ts`
  - Teacher API client, including CSV download helper.

- `apps/web/lib/api/teacherTypes.ts`
  - Teacher API TypeScript types.

- `apps/web/lib/api/client.ts`
  - Public API client.

Backend:

- `services/api/app/api/deps.py`
  - Teacher JWT verification.
  - Supports Supabase JWKS/ES256.

- `services/api/app/api/v1/admin.py`
  - Admin routes and teacher routes.
  - Teacher roll CRUD, scenario assignment, roll-scoped gradebook, CSV export.

- `services/api/app/api/v1/public.py`
  - Public scenario, class-code, play, step, back, reflection endpoints.

- `services/api/app/schemas/admin.py`
  - Teacher/admin schemas, including roll gradebook and `best_attempt`.

- `services/api/app/schemas/public.py`
  - Public schemas, including play view `learner_label`.

- `services/api/app/repositories/roll_repo.py`
  - Class roll and assignment helpers.

- `services/api/app/repositories/play_repo.py`
  - Play attempt and reflection helpers.

Tests:

- `apps/web/app/teacher/login/page.test.tsx`
- `apps/web/lib/api/teacher.test.ts`
- `apps/web/app/[slug]/complete/[playId]/page.test.tsx`
- `apps/web/app/[slug]/play/[playId]/page.test.tsx`
- `services/api/tests/test_teacher_auth_jwks.py`
- `services/api/tests/test_teacher_setup.py`
- `services/api/tests/test_public_class_code.py`
- `services/api/tests/test_public_play_view.py`
- `services/api/tests/test_public_play_reflection.py`

## Verified Commands

Frontend:

```powershell
cd apps/web
npm run type-check
npm test -- --runTestsByPath lib/api/teacher.test.ts
npm test -- --runTestsByPath app/teacher/login/page.test.tsx
npm test -- --runTestsByPath app/[slug]/complete/[playId]/page.test.tsx app/[slug]/play/[playId]/page.test.tsx
```

Backend:

```powershell
cd services/api
python -m compileall app tests
uv run --with-requirements requirements.txt --with pytest pytest tests/test_teacher_auth_jwks.py
uv run --with-requirements requirements.txt --with pytest --with httpx --with-editable ..\..\packages\engine --with-editable ..\..\packages\expr pytest tests/test_teacher_setup.py
```

Known local test limitation:

- DB-backed pytest files collect but skip locally when Postgres is unavailable.
- This is expected unless a reachable test database is running.

## Current Git State At Handoff

Committed and pushed production work through:

- `f153218 Fix teacher signup confirmation redirect`
- `c923aa6 Verify Supabase teacher JWTs with JWKS`
- `6213f29 Carry roster name into reflections`
- `ced6995 Add gradebook CSV export and best attempts`

Known untracked local note files:

- `.codex/`
- `eod-summary-06142026.md`
- `eod-summary-06142026.txt`
- `newprompt.md`

These are notes/process artifacts. They were intentionally not committed.

## Next Recommended Goal

Build paid teacher entitlement with a payment processor.

Recommended MVP shape:

- Use Stripe Checkout, unless the user chooses a simpler alternative like Lemon Squeezy.
- Keep teacher signup open.
- Let unpaid teachers sign in but show a locked dashboard with a payment call to action.
- Let active paid teachers create classes, assign scenarios, view results, and export gradebooks.
- Preserve data when subscription expires or is canceled.

Suggested acceptance criteria:

- Unpaid teacher can sign in but cannot create classes or export gradebooks.
- Unpaid teacher sees a clear subscribe/upgrade screen.
- Teacher can start checkout.
- Payment webhook records active entitlement.
- Active teacher can access the dashboard workflow.
- Canceled/expired subscription removes paid access.
- Backend enforces entitlement, not just frontend UI.

Suggested backend additions:

- `teacher_entitlements` or `subscriptions` table.
- Stripe webhook endpoint.
- Entitlement repository/service.
- Dependency/helper such as `require_active_teacher_entitlement`.
- Apply entitlement checks to paid teacher actions:
  - create/update class rolls
  - assign scenarios
  - view/export gradebook

Suggested frontend additions:

- Teacher billing/status API methods.
- Locked dashboard state for unpaid teachers.
- Checkout button.
- Post-checkout success/cancel states.

## Product Risks And Open Decisions

- Teacher signups are currently open. That is fine for testing but should be considered before public launch.
- Duplicate student names are allowed and can create ambiguity.
- Best attempt currently means latest completed attempt, not highest score.
- There is no organization/school abstraction.
- There is no billing/subscription/entitlement layer yet.
- There is no server-side Next auth middleware; backend JWT checks are the real security boundary.
- Local DB tests need a reachable Postgres instance for full execution.

## Rehydration Instructions For Future Codex

Start by reading this file, then run:

```powershell
git status --short
```

Then inspect:

- `apps/web/app/teacher/page.tsx`
- `apps/web/lib/api/teacher.ts`
- `services/api/app/api/v1/admin.py`
- `services/api/app/api/deps.py`
- `services/api/tests/test_teacher_setup.py`

Assume the classroom MVP and gradebook export have been live-verified. Do not rework them unless a current bug is reported. The next major sellable-MVP goal is payment and entitlement gating.

