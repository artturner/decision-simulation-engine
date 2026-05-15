/**
 * TypeScript types for the Branching Scenarios public API.
 *
 * All types mirror the Pydantic schemas in services/api/app/schemas/public.py
 * exactly — field names, optionality, and value shapes are kept in sync.
 */

// ---------------------------------------------------------------------------
// Shared
// ---------------------------------------------------------------------------

export interface Choice {
  text: string;
}

export interface SceneDTO {
  scene_id: string;
  type: "choice" | "auto_advance" | "conditional" | "end";
  title: string;
  narration: string;
  description: string;
  image_url: string | null;
  /** Populated only for type="choice" scenes. */
  choices: Choice[] | null;
  /** Populated only for type="end" scenes. */
  outcome: string | null;
  /** Populated only for type="end" scenes. */
  outcome_message: string | null;
}

export interface Progress {
  step_count: number;
  choices_made: string[];
}

// ---------------------------------------------------------------------------
// GET /public/scenarios/{slug}
// ---------------------------------------------------------------------------

export interface ScenarioMetadata {
  title: string;
  description: string;
  page_title: string;
  page_icon: string;
  author: string;
  version: string;
  completion_tracking: boolean;
  cover_image_url: string | null;
}

export interface ScenarioPublicResponse {
  slug: string;
  scenario_version_id: string;
  version_number: number;
  metadata: ScenarioMetadata;
  start_scene_id: string;
  reflection_questions: string[];
  reflection_prompts: string[];
}

// ---------------------------------------------------------------------------
// POST /public/plays/start
// ---------------------------------------------------------------------------

export interface PlayStartRequest {
  scenario_version_id: string;
  learner_label?: string;
}

export interface PlayStartResponse {
  play_id: string;
  scenario_version_id: string;
  scene: SceneDTO;
  progress: Progress;
}

// ---------------------------------------------------------------------------
// GET /public/plays/{play_id}
// ---------------------------------------------------------------------------

export interface PlayViewResponse {
  play_id: string;
  scene: SceneDTO;
  progress: Progress;
  done: boolean;
  outcome: string | null;
  outcome_message: string | null;
  reflection_required: boolean;
  reflection_questions: string[];
  reflection_prompts: string[];
}

// ---------------------------------------------------------------------------
// POST /public/plays/{play_id}/step
// ---------------------------------------------------------------------------

export interface StepRequest {
  choice_index?: number;
}

export interface StepResponse {
  play_id: string;
  scene: SceneDTO;
  progress: Progress;
  done: boolean;
  outcome: string | null;
  outcome_message: string | null;
}

// ---------------------------------------------------------------------------
// POST /public/plays/{play_id}/back
// ---------------------------------------------------------------------------

export interface BackResponse {
  play_id: string;
  scene: SceneDTO;
  progress: Progress;
  done: false;
}

// ---------------------------------------------------------------------------
// POST /public/plays/{play_id}/reflection
// ---------------------------------------------------------------------------

export interface ReflectionRequest {
  /** Maps question keys (e.g. "reflection_1") to free-text answers. */
  responses: Record<string, string>;
  student_name?: string;
}

export interface ReflectionResponse {
  ok: true;
}

// ---------------------------------------------------------------------------
// Error shape returned by the API on 4xx / 5xx
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string | { message: string; errors: string[] };
}
