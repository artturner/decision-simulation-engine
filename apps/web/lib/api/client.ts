/**
 * Typed API client for the Branching Scenarios public API.
 *
 * Base URL is read from NEXT_PUBLIC_API_BASE_URL at build/runtime.
 * All functions throw an ApiClientError on non-2xx responses so callers
 * can display a meaningful error without inspecting raw Response objects.
 */

import type {
  BackResponse,
  ClassPickerResponse,
  PlayStartRequest,
  PlayStartResponse,
  PlayViewResponse,
  ReflectionRequest,
  ReflectionResponse,
  ScenarioPublicResponse,
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

  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail?.message) {
        message = body.detail.message;
      }
    } catch {
      // response body was not JSON — keep the generic message
    }
    throw new ApiClientError(res.status, message);
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
