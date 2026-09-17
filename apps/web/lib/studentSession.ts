/**
 * Client-side persistence for the student's claimed access token.
 *
 * The only localStorage usage in the app: one JSON blob under a versioned
 * key. A session is per-name — on shared lab machines the join pages show
 * "Signed in as {name} — Not you?" so a classmate can switch cleanly.
 * Single active session by design: a student on multiple rolls re-claims
 * when switching classes (codes are multi-use, so this is painless).
 */

const STORAGE_KEY = "student-session.v1";

export interface StudentSession {
  token: string;
  roll_id: string;
  /** Canonical roster spelling returned by the redeem endpoint. */
  student_name: string;
  join_code: string;
  expires_at: string;
  claimed_at: string;
}

export function loadSession(): StudentSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as StudentSession;
    if (!session.token || !session.student_name) return null;
    if (session.expires_at && new Date(session.expires_at) <= new Date()) {
      clearSession();
      return null;
    }
    return session;
  } catch {
    return null;
  }
}

export function saveSession(session: StudentSession): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // Private windows / blocked storage: the claim still works for this
    // page view via in-memory state; the student just re-enters next time.
  }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
