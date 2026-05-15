# Branching Scenarios MVP (v1.0)

**Next.js (frontend) + FastAPI (backend) + Postgres (events + reflections + analytics)**

A production-ready MVP for interactive branching scenarios (decision-based simulations) powered by a JSON-defined state machine. This project modernizes an existing Streamlit/Python engine by extracting a **pure Python runner** and wrapping it with a **FastAPI execution API**, a **Next.js learner UI**, and a **Postgres event/reflection store**.

This MVP is **player-first**:
- Deliver scenarios via shareable links
- Support **Go Back** (rewind)
- Capture **reflections** as first-class learning artifacts
- Generate **analytics + CSV export**

Authoring UI is out of scope for v1, but the platform supports **scenario import + versioning** from day one.

---

## Quickstart

> **Prerequisites:** Docker Desktop, Git

```bash
# 1. Clone and start the full stack
git clone <repo-url> decision-simulation-engine
cd decision-simulation-engine
cd infra && docker compose up --build
```

Wait for the `api` healthcheck to pass (≈ 30 s on first build), then in a second terminal:

```bash
# 2. Seed the sample Cherokee Crossroads scenario
python services/api/scripts/seed.py

# Or, if you prefer to run from inside the container:
# docker compose exec api python scripts/seed.py
```

```
✓  Imported as version 1.
   Scenario page : http://localhost:3000/cherokee-crossroads
   API docs      : http://localhost:8000/docs
```

**Service URLs**

| Service | URL |
|---------|-----|
| Learner UI (Next.js) | http://localhost:3000 |
| API (FastAPI + OpenAPI) | http://localhost:8000/docs |
| Database GUI (Adminer) | http://localhost:8080 |

**Running tests**

```bash
# API unit + integration tests (requires running Postgres)
cd services/api && python -m pytest

# Frontend unit tests (Jest)
cd apps/web && npm test

# E2E smoke tests (Playwright — requires full stack running)
cd apps/web && npm run test:e2e
```

**Seeding your own scenario**

```bash
# Point the seed script at any fixture JSON
python services/api/scripts/seed.py --file path/to/my-scenario.json
```

See `SAMPLE_SCENARIO.json` at the repo root for the full JSON contract.

---

## 1) Product Definition

### One-liner
Deliver interactive branching scenarios with reflection and analytics — powered by JSON state machines.

### MVP Must Support (from existing format)
- Scene types: `choice`, `auto_advance`, `conditional`, `end`
- `scenes` keyed by string scene IDs (e.g., `"1"`, `"1.1"`, `"3a"`)
- `choice.choices[]` uses `{ text, next }`
- Optional `effects`: `{ "confidence": 1, "risk": -1 }`
- `conditional.conditions[] = [{ condition, next }, ...]` with optional `default`
- Reflection: `reflection_questions[]`, `reflection_prompts[]`
- Images: relative paths (e.g., `"scene_1.png"` or `"images/scene_1.png"`)

### Improvements Introduced in MVP
- `start_scene_id` (defaults to `"1"` if absent)
- DB-backed scenarios with **versioning** (`scenario_versions`)
- Postgres as source of truth (Sheets optional exporter later)
- Safe expression parser (no `eval`)
- Backend is sole authority for state

---

## 2) Architecture Overview

**Stack**
- Frontend: Next.js (App Router)
- Backend: FastAPI (Python 3.11+)
- DB: Postgres
- Media: relative paths + `MEDIA_BASE_URL` (CDN/S3/R2/GCS compatible)

**Execution Model**
Backend is authoritative for:
- scenario execution
- variable state
- condition evaluation
- event logging
- rewind (“Go Back”)

Frontend is a pure renderer + command dispatcher.

**Go Back (Event Sourcing)**
- Immutable events
- Rewind by truncating last step and replaying events deterministically

**Why Versioning Now**
- Edit safety for live learners
- Rollbacks
- Draft vs published without schema churn

---

## 3) Repo Structure

```
decision-simulation-engine/
  apps/
    web/
  services/
    api/
  packages/
    engine/
    expr/
  infra/
    docker-compose.yml
  docs/
    api.md
    schema.md
    decisions/
      ADR-001-stack.md
      ADR-002-event-sourcing-go-back.md
      ADR-003-versioning.md
      ADR-004-safe-expressions.md
  README.md
```

---

## 4) Scenario JSON Contract

**Top-Level**
- `metadata`: title, description, page_title, page_icon, author, version, completion_tracking
- `reflection_questions[]`
- `reflection_prompts[]`
- `variables` (optional)
- `start_scene_id` (optional; default `"1"`)
- `scenes` keyed by scene id

**Scene Types**
- `choice`: `{ choices: [{ text, next, effects? }] }`
- `auto_advance`: `{ next }`
- `conditional`: `{ conditions: [{ condition, next }], default? }`
- `end`: `{ outcome, outcome_message }`

**Media Resolution**
JSON uses relative paths. API resolves:

`${MEDIA_BASE_URL}/${scenario_slug}/${version_number}/${relative_path}`

---

## 5) Safe Expression Grammar (Author Contract)

**Identifiers**: case-sensitive variable names  
**Literals**: integers, floats (negatives allowed); optional booleans  
**Operators (precedence)**:
1. `!`
2. `== != < <= > >=`
3. `&&`
4. `||`
5. `( )`

**Rules**
- Variables only from scenario state
- Unknown variables or parse errors → **false (fail-closed)**
- No functions, no concatenation, no `eval()`

**Examples**
```
LargeStateFavor >= -2 && LargeStateFavor <= 2 && SouthernStateFavor >= -2 && SouthernStateFavor <= 2
LargeStateFavor > 3 || LargeStateFavor < -3 || SouthernStateFavor < -3
```

---

## 6) API Contract (MVP)

Base path: `/v1`

**Public**
- `GET /public/scenarios/{slug}`
- `POST /public/plays/start`
- `GET /public/plays/{play_id}`
- `POST /public/plays/{play_id}/step`
- `POST /public/plays/{play_id}/back`
- `POST /public/plays/{play_id}/reflection`

**Admin (X-Admin-Key)**
- `POST /admin/scenarios/import`
- `POST /admin/scenarios/{scenario_id}/versions`
- `POST /admin/scenarios/{scenario_id}/versions/{version_number}/publish`
- `GET /admin/scenarios/{scenario_id}/analytics`
- `GET /admin/scenarios/{scenario_id}/export.csv`

---

## 7) Engine Package (Pure Python)

Functions:
```python
validate(scenario_json) -> list[str]
start(scenario_json) -> (state, scene_dto)
step(scenario_json, state, choice_index?) -> (state, scene_dto, done, outcome?)
rewind(scenario_json, events) -> (state, scene_dto)
```

State shape:
```json
{
  "current_scene_id": "2",
  "variables": { "confidence": 1 },
  "history": [
    { "scene_id": "2", "choice_index": 0, "choice_text": "...", "next_scene_id": "3a" }
  ]
}
```

---

## 8) Local Dev

**Prereqs**: Node 20+, Python 3.11+, Docker

```bash
docker compose up -d db
cd services/api && uvicorn app.main:app --reload --port 8000
cd apps/web && npm install && npm run dev
```

---

## 9) Env Vars

**services/api/.env**
```
DATABASE_URL=postgresql+psycopg://...
CORS_ORIGINS=http://localhost:3000
ADMIN_API_KEY=dev-secret
MEDIA_BASE_URL=https://cdn.example.com/scenarios
```

**apps/web/.env.local**
```
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 10) TDD Milestones
- M1: expr (safe parser)
- M2: engine (pure runner)
- M3: DB + API
- M4: UI + Playwright E2E
