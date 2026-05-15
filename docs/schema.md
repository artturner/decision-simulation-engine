# Database Schema (MVP)

## scenarios
- id (UUID, PK)
- slug (unique)
- title
- description
- created_at
- updated_at

## scenario_versions
- id (UUID, PK)
- scenario_id (FK → scenarios.id)
- version_number (INT, monotonic per scenario)
- status (ENUM: draft | published | archived)
- scenario_json (JSONB)
- created_at
- UNIQUE (scenario_id, version_number)

## plays
- id (UUID, PK)
- scenario_version_id (FK)
- learner_label (nullable)
- started_at
- ended_at
- completed (bool)
- outcome (nullable)
- outcome_message (nullable)

## events (immutable)
- id (UUID, PK)
- play_id (FK)
- seq (INT, monotonic per play)
- ts
- event_type (ENUM)
- scene_id (nullable)
- choice_index (nullable)
- choice_text (nullable)
- next_scene_id (nullable)
- delta_json (JSONB)

## reflections
- id (UUID, PK)
- play_id (FK, unique)
- submitted_at
- student_name
- responses_json (JSONB)
