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
// GET /public/class/{rollId}
// ---------------------------------------------------------------------------

export interface ClassPickerScenario {
  scenario_version_id: string;
  slug: string;
  title: string;
  description: string;
  sort_order: number | null;
}

export interface ClassPickerResponse {
  roll_id: string;
  roll_name: string;
  join_code: string;
  student_names: string[];
  scenarios: ClassPickerScenario[];
}

export interface StudentScenarioStatus {
  scenario_version_id: string;
  slug: string;
  title: string;
  description: string;
  sort_order: number | null;
  in_progress_play_id: string | null;
  submitted_count: number;
  latest_submitted_play_id: string | null;
}

export interface StudentClassStatusResponse {
  roll_id: string;
  roll_name: string;
  join_code: string;
  student_name: string;
  scenarios: StudentScenarioStatus[];
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
  class_roll_id?: string;
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
  learner_label: string | null;
  class_roll_id: string | null;
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
// POST /public/plays/{play_id}/reflection/grade  and  .../accept
// ---------------------------------------------------------------------------

export interface GradeDimension {
  level: "full" | "solid" | "minimal" | "low_effort";
  points: number;
  max_points: number;
  evidence: string;
}

export interface GradeResult {
  grade_total: number;
  completion_points: number;
  dimensions: Record<string, GradeDimension>;
  feedback: string;
  needs_human_review: boolean;
  low_effort_flags: string[];
  accepted: boolean;
  attempts_used: number;
  attempts_remaining: number;
  can_redo: boolean;
}

// ---------------------------------------------------------------------------
// Error shape returned by the API on 4xx / 5xx
// ---------------------------------------------------------------------------

export interface ApiError {
  detail: string | { message: string; errors: string[] };
}

// ---------------------------------------------------------------------------
// POST /public/claims/redeem  and  GET /public/student-session
// ---------------------------------------------------------------------------

export interface ClaimRedeemRequest {
  claim_code: string;
  /** Optional wrong-slip check — omit to resolve the student from the
   *  code alone (the class-code-box recovery path). */
  student_name?: string;
  /** Optional extra check; essay-app callers omit it. */
  join_code?: string;
}

export interface ClaimRedeemResponse {
  token: string;
  expires_at: string;
  /** Canonical roster spelling — store this, not what the student typed. */
  student_name: string;
  roll_id: string;
  roll_name: string;
  /** The class join code, so a claim-code-first entry can load the class. */
  join_code: string;
}

export interface StudentSessionResponse {
  valid: boolean;
  reason: "missing" | "invalid" | "revoked" | null;
  student_name: string | null;
  roll_id: string | null;
}

// ---------------------------------------------------------------------------
// Student dashboard (GET /api/v1/student/dashboard)
// ---------------------------------------------------------------------------

export type DashItemType = "video" | "scenario" | "frq";
export type DashStatus =
  | "done_on_time"
  | "done"
  | "done_late"
  | "pending_grade"
  | "missing"
  | "in_progress"
  | "upcoming";

export interface DashChecklistRow {
  key: string;
  title: string;
  type: DashItemType;
  unit: number;
  chapter: number | null;
  target: string;
  flexible: boolean;
  status: DashStatus;
  state: string;
  score: number | null;
  completed_at: string | null;
  link: string | null;
  alt_link: string | null;
  available: boolean;
  almost_label: string | null;
  can_revise: boolean;
  revisions_left: number | null;
  detail: Record<string, unknown>;
}

export interface DashMove {
  key: string;
  title: string;
  type: DashItemType;
  kind: "finish" | "resume" | "start" | "revise";
  label: string | null;
  target: string;
  days_until_due: number;
  past_due: boolean;
  grade_delta: number;
  effort_minutes: number;
  link: string;
  alt_link: string | null;
}

export interface DashTip {
  kind: string;
  title: string;
  body: string;
  quote?: string | null;
  review?: { video: string; prompt: string }[];
}

export interface DashBadge {
  id: string;
  name: string;
  description: string;
  icon: string;
  earned: boolean;
  progress: number | null;
  goal: number | null;
}

export interface DashTypeStat {
  type: DashItemType;
  label: string;
  weight: number;
  total: number;
  done: number;
  due: number;
  missing: number;
  avg_submitted: number | null;
  avg_counted: number | null;
}

export interface DashUnit {
  unit: number;
  name: string;
  done: number;
  total: number;
  start: string;
  end: string;
  state: "cleared" | "current" | "future" | "open_past";
  missing: number;
}

export interface StudentDashboard {
  as_of: string;
  course: string;
  term: string;
  late_policy: string;
  summary: {
    grade: number | null;
    letter: string | null;
    grade_submitted: number | null;
    letter_submitted: string | null;
    pace: "ahead" | "ok" | "slight" | "behind";
    pace_label: string;
    missing_count: number;
    early_count: number;
    done_count: number;
    due_count: number;
    total_count: number;
    pending_count: number;
    catch_up: { items: number; grade_after: number | null; letter_after: string | null } | null;
  };
  by_type: DashTypeStat[];
  this_week: { start: string; end: string; keys: string[] };
  next_moves: DashMove[];
  units: DashUnit[];
  checklist: DashChecklistRow[];
  stats: {
    video_first_try_pct: number | null;
    video_questions: number;
    videos_completed: number;
    reflection_dimensions: { key: string; avg_rank: number; count: number; typical_level: string }[];
    frq_dimensions: { key: string; title: string; pct: number | null }[];
    scores_over_time: { key: string; type: DashItemType; title: string; date: string; score: number }[];
  };
  tips: DashTip[];
  game: {
    xp: number;
    level: {
      number: number;
      name: string;
      floor: number;
      next_at: number | null;
      next_name: string | null;
      progress: number;
    };
    streak: { current_weeks: number; best_weeks: number; weeks_counted: number };
    activity: { weeks: { start: string; completed: number }[]; last_7_days: number };
    badges: DashBadge[];
  };
}

export interface StudentDashboardResponse {
  student: { name: string; roll_name: string; join_code: string };
  plan_available: boolean;
  sources: Record<string, "ok" | "unavailable" | "not_configured">;
  dashboard: StudentDashboard | null;
}
