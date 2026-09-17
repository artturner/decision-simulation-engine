"use client";

/**
 * Owns the student's claimed session on the client.
 *
 * Used by both class-picker pages (/join and /class/[rollId]) so the
 * claim/switch logic cannot drift between them, and by any page that
 * needs to re-claim inline after a 401.
 */

import { useCallback, useEffect, useState } from "react";
import type { ClaimRedeemResponse } from "@/lib/api/types";
import { namesEquivalent } from "@/lib/names";
import {
  clearSession,
  loadSession,
  saveSession,
  type StudentSession,
} from "@/lib/studentSession";

export function useStudentAccess() {
  // Hydrate from localStorage after mount (SSR-safe).
  const [session, setSession] = useState<StudentSession | null>(null);
  useEffect(() => {
    setSession(loadSession());
  }, []);

  /** Persist a successful redeem. Stores the canonical roster spelling. */
  const claim = useCallback(
    (resp: ClaimRedeemResponse, joinCode: string) => {
      const next: StudentSession = {
        token: resp.token,
        roll_id: resp.roll_id,
        student_name: resp.student_name,
        join_code: joinCode,
        expires_at: resp.expires_at,
        claimed_at: new Date().toISOString(),
      };
      saveSession(next);
      setSession(next);
      return next;
    },
    [],
  );

  /** The shared-computer "Not you?" affordance. */
  const signOut = useCallback(() => {
    clearSession();
    setSession(null);
  }, []);

  /** The session, but only when it belongs to this student name. */
  const sessionFor = useCallback(
    (studentName: string): StudentSession | null =>
      session && namesEquivalent(session.student_name, studentName)
        ? session
        : null,
    [session],
  );

  return { session, claim, signOut, sessionFor };
}
