/**
 * Typed API client for the Branching Scenarios public API.
 *
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL at build/runtime.
 * All functions throw an ApiClientError on non-2xx responses so callers
 * can display a meaningful error without inspecting raw Response objects.
 */

import { loadSession } from "../studentSession";
import type {
  BackResponse,
  ClaimRedeemRequest,
  ClaimRedeemResponse,
  ClassPickerResponse,
  GradeResult,
  PlayStartRequest,
  PlayStartResponse,
  PlayViewResponse,
  ReflectionRequest,
  ReflectionResponse,
  ScenarioPublicResponse,
  StudentClassStatusResponse,
  StudentSessionResponse,
  StepRequest,
  StepResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Base fetch wrapper
// ---------------------------------------------------------------------------

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiClientError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    /** Machine-readable error code from a structured `detail` (e.g.
     *  "quota_exhausted" on the grading endpoint), null otherwise. */
    public readonly code: string | null = null,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}/api/v1/public${path}`;

  // Ride the claimed student token on every request. The server decides
  // what needs it; anonymous flows simply have no session.
  const session = loadSession();

  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(session ? { "X-Student-Token": session.token } : {}),
      ...init.headers,
    },
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    let code: string | null = null;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail?.message) {
        message = body.detail.message;
        if (typeof body.detail.code === "string") {
          code = body.detail.code;
        }
      }
    } catch {
      // response body was not JSON — keep the generic message
    }
    throw new ApiClientError(res.status, message, code);
  }

  // 204 No Content or similar — return undefined cast to T
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as unknown as T;
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Public API functions
// ---------------------------------------------------------------------------

/**
 * GET /public/class/{rollId}
 *
 * Returns the class roll's student name list and its visible scenarios.
 * Used to render the class picker page at /class/[rollId].
 */
export function getClassPicker(rollId: string): Promise<ClassPickerResponse> {
  return apiFetch<ClassPickerResponse>(`/class/${rollId}`);
}

/**
 * GET /public/classes/code/{joinCode}
 *
 * Returns the class roll's student name list and visible scenarios by
 * student-facing join code.
 */
export function getClassPickerByCode(
  joinCode: string,
): Promise<ClassPickerResponse> {
  return apiFetch<ClassPickerResponse>(
    `/classes/code/${encodeURIComponent(joinCode)}`,
  );
}

/**
 * GET /public/classes/code/{joinCode}/students/{studentName}
 *
 * Returns visible scenarios plus attempt status for the selected student.
 */
export function getStudentClassStatus(
  joinCode: string,
  studentName: string,
): Promise<StudentClassStatusResponse> {
  return apiFetch<StudentClassStatusResponse>(
    `/classes/code/${encodeURIComponent(joinCode)}/students/${encodeURIComponent(studentName)}`,
  );
}

/**
 * GET /public/scenarios/{slug}
 *
 * Returns metadata for the latest published version of the scenario.
 * Throws ApiClientError(404) if the slug does not exist or has no
 * published version.
 */
export function getScenario(slug: string): Promise<ScenarioPublicResponse> {
  return apiFetch<ScenarioPublicResponse>(`/scenarios/${slug}`);
}

/**
 * POST /public/plays/start
 *
 * Create a new play session for a specific scenario version.
 * Returns the play ID and the initial scene.
 */
export function startPlay(body: PlayStartRequest): Promise<PlayStartResponse> {
  return apiFetch<PlayStartResponse>("/plays/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * GET /public/plays/{playId}
 *
 * Reconstruct and return the full current state of a play session.
 * Safe to call on page refresh or deep-link navigation.
 */
export function getPlay(playId: string): Promise<PlayViewResponse> {
  return apiFetch<PlayViewResponse>(`/plays/${playId}`);
}

/**
 * POST /public/plays/{playId}/restart
 *
 * Start a fresh attempt of the same scenario, carrying over the source
 * play's learner_label and class_roll_id so gradebook attribution survives.
 */
export function restartPlay(playId: string): Promise<PlayViewResponse> {
  return apiFetch<PlayViewResponse>(`/plays/${playId}/restart`, {
    method: "POST",
  });
}

/**
 * POST /public/plays/{playId}/step
 *
 * Advance the play by one step.
 * Pass choice_index for choice scenes; omit for auto_advance / conditional.
 */
export function stepPlay(
  playId: string,
  body: StepRequest,
): Promise<StepResponse> {
  return apiFetch<StepResponse>(`/plays/${playId}/step`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /public/plays/{playId}/back
 *
 * Undo the last step and return the previous scene.
 * Returns 400 if already at the start.
 */
export function backPlay(playId: string): Promise<BackResponse> {
  return apiFetch<BackResponse>(`/plays/${playId}/back`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/**
 * POST /public/plays/{playId}/reflection
 *
 * Submit a learner reflection for a completed play.
 * Returns 409 if a reflection was already submitted.
 */
export function submitReflection(
  playId: string,
  body: ReflectionRequest,
): Promise<ReflectionResponse> {
  return apiFetch<ReflectionResponse>(`/plays/${playId}/reflection`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /public/plays/{playId}/reflection/grade
 *
 * Grade (or re-grade) a reflection and return the score plus coaching feedback.
 * Throws ApiClientError(503) if AI grading is not configured — callers should
 * fall back to submitReflection. When the teacher's monthly grading quota is
 * exhausted, the 503 carries code "quota_exhausted" so callers can tell the
 * student AI feedback is temporarily unavailable. Throws 409 if the
 * reflection is already accepted, 502 if the grading API fails.
 */
export function gradeReflection(
  playId: string,
  body: ReflectionRequest,
): Promise<GradeResult> {
  return apiFetch<GradeResult>(`/plays/${playId}/reflection/grade`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * POST /public/plays/{playId}/reflection/accept
 *
 * Accept the current grade, locking the reflection. Idempotent.
 */
export function acceptReflection(playId: string): Promise<GradeResult> {
  return apiFetch<GradeResult>(`/plays/${playId}/reflection/accept`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

/**
 * POST /public/claims/redeem
 *
 * Exchange a teacher-issued per-student access code for a student token.
 * Throws 404 (code "claim_code_not_found") for an unknown or regenerated
 * code, 403 (code "claim_code_wrong_name") when the code belongs to a
 * different roster name.
 */
export function redeemClaim(
  body: ClaimRedeemRequest,
): Promise<ClaimRedeemResponse> {
  return apiFetch<ClaimRedeemResponse>("/claims/redeem", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * GET /public/student-session
 *
 * Report whether the stored student token is still valid. Never throws
 * for auth reasons — invalid/revoked tokens come back as { valid: false }.
 */
export function getStudentSession(): Promise<StudentSessionResponse> {
  return apiFetch<StudentSessionResponse>("/student-session");
}

/** True when an ApiClientError means the student must (re-)enter a code. */
export function isStudentTokenError(err: unknown): err is ApiClientError {
  return (
    err instanceof ApiClientError &&
    err.status === 401 &&
    typeof err.code === "string" &&
    err.code.startsWith("student_token_")
  );
}

/** True when a valid token belongs to a different student (switch flow). */
export function isStudentMismatchError(err: unknown): err is ApiClientError {
  return (
    err instanceof ApiClientError &&
    err.status === 403 &&
    err.code === "student_token_mismatch"
  );
}

/**
 * Query retry policy: never retry auth failures (a 401/403 will not fix
 * itself — the student must re-claim), one retry for everything else.
 */
export function retryUnlessAuth(failureCount: number, err: unknown): boolean {
  if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
    return false;
  }
  return failureCount < 1;
}
