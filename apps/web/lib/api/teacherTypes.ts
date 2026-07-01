export interface ClassRoll {
  id: string;
  name: string;
  join_code: string;
  student_names: string[];
  created_at: string;
}

export interface ClassRollCreate {
  name: string;
  student_names: string[];
}

export interface ClassRollUpdate {
  name?: string;
  student_names?: string[];
}

export interface PublishedScenario {
  id: string;
  slug: string;
  title: string;
  description: string;
  published_version_id: string;
  version_number: number;
}

export type GradingDifficulty = "strict" | "standard" | "lenient";

export interface RollScenario {
  id: string;
  scenario_id: string;
  class_roll_id: string;
  visible: boolean;
  sort_order: number | null;
  grading_difficulty: GradingDifficulty;
  created_at: string;
  slug: string;
  title: string;
  description: string;
}

export interface AssignmentCreate {
  scenario_id: string;
  visible?: boolean;
  sort_order?: number | null;
  grading_difficulty?: GradingDifficulty;
}

export interface AssignmentUpdate {
  visible?: boolean;
  sort_order?: number | null;
  grading_difficulty?: GradingDifficulty;
}

export interface RollGradebookReflection {
  student_name: string | null;
  submitted_at: string;
  responses: Record<string, string>;
  grade_total: number | null;
  feedback: string | null;
  accepted: boolean;
  needs_human_review: boolean;
  graded_at: string | null;
  difficulty: GradingDifficulty | null;
}

export interface RollGradebookAttempt {
  play_id: string;
  started_at: string;
  ended_at: string | null;
  completed: boolean;
  outcome: string | null;
  reflection: RollGradebookReflection | null;
}

export interface RollGradebookStudent {
  student_name: string;
  status: "not_started" | "in_progress" | "completed";
  in_progress_play_id: string | null;
  submitted_count: number;
  latest_submitted_at: string | null;
  best_attempt: RollGradebookAttempt | null;
  attempts: RollGradebookAttempt[];
}

export interface RollGradebook {
  roll_id: string;
  scenario_id: string;
  scenario_title: string;
  grading_difficulty: GradingDifficulty;
  students: RollGradebookStudent[];
}
