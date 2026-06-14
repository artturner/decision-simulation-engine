import { ApiClientError } from "./client";
import type {
  AssignmentCreate,
  AssignmentUpdate,
  ClassRoll,
  ClassRollCreate,
  ClassRollUpdate,
  PublishedScenario,
  RollGradebook,
  RollScenario,
} from "./teacherTypes";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function teacherFetch<T>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}/api/v1/teacher${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
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
      // Keep generic message.
    }
    throw new ApiClientError(res.status, message);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export function listRolls(token: string): Promise<ClassRoll[]> {
  return teacherFetch<ClassRoll[]>(token, "/rolls");
}

export function createRoll(
  token: string,
  body: ClassRollCreate,
): Promise<ClassRoll> {
  return teacherFetch<ClassRoll>(token, "/rolls", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateRoll(
  token: string,
  rollId: string,
  body: ClassRollUpdate,
): Promise<ClassRoll> {
  return teacherFetch<ClassRoll>(token, `/rolls/${rollId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deleteRoll(token: string, rollId: string): Promise<void> {
  return teacherFetch<void>(token, `/rolls/${rollId}`, {
    method: "DELETE",
  });
}

export function listPublishedScenarios(
  token: string,
): Promise<PublishedScenario[]> {
  return teacherFetch<PublishedScenario[]>(token, "/scenarios/published");
}

export function listRollScenarios(
  token: string,
  rollId: string,
): Promise<RollScenario[]> {
  return teacherFetch<RollScenario[]>(token, `/rolls/${rollId}/scenarios`);
}

export function assignScenario(
  token: string,
  rollId: string,
  body: AssignmentCreate,
): Promise<RollScenario> {
  return teacherFetch<RollScenario>(token, `/rolls/${rollId}/scenarios`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateAssignment(
  token: string,
  rollId: string,
  scenarioId: string,
  body: AssignmentUpdate,
): Promise<RollScenario> {
  return teacherFetch<RollScenario>(
    token,
    `/rolls/${rollId}/scenarios/${scenarioId}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export function getRollGradebook(
  token: string,
  rollId: string,
  scenarioId: string,
): Promise<RollGradebook> {
  return teacherFetch<RollGradebook>(
    token,
    `/rolls/${rollId}/scenarios/${scenarioId}/gradebook`,
  );
}
