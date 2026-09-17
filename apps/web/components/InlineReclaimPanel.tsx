"use client";

/**
 * Inline recovery for student-token failures mid-flow.
 *
 * Rendered IN PLACE (never navigates away) so typed work — a half-written
 * reflection especially — survives the re-claim. Handles:
 *  - 401 student_token_* : re-enter the access code (when we know whose
 *    work this is) or route through /join (when we don't);
 *  - 403 student_token_mismatch : someone else's session on this device.
 *
 * Returns null for unrelated errors — callers keep their own error UI.
 */

import { useRouter } from "next/navigation";
import ClaimCodeForm from "@/components/ClaimCodeForm";
import { isStudentMismatchError, isStudentTokenError } from "@/lib/api/client";
import { useStudentAccess } from "@/lib/useStudentAccess";

interface InlineReclaimPanelProps {
  error: unknown;
  /** Whose work this is (e.g. play.learner_label); falls back to the
   *  stored session's name when the record couldn't be loaded at all. */
  studentName?: string | null;
  /** Called after a successful re-claim — retry the failed request. */
  onReclaimed: () => void;
}

export default function InlineReclaimPanel({
  error,
  studentName,
  onReclaimed,
}: InlineReclaimPanelProps) {
  const router = useRouter();
  const { session, claim, signOut } = useStudentAccess();

  if (isStudentMismatchError(error)) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-semibold">This work belongs to a different student.</p>
        {session && (
          <p className="mt-1">
            This device is signed in as <b>{session.student_name}</b>.
          </p>
        )}
        <button
          type="button"
          onClick={() => {
            signOut();
            router.push(session?.join_code ? `/join?code=${session.join_code}` : "/join");
          }}
          className="mt-3 rounded-md bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-700"
        >
          Switch student
        </button>
      </div>
    );
  }

  if (!isStudentTokenError(error)) return null;

  const name = studentName?.trim() || session?.student_name || "";
  if (!name) {
    // Fresh device, deep link, no session — the join page owns name entry.
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-semibold">Your class access code is needed.</p>
        <p className="mt-1">
          Go to the class page, pick your name, and enter the access code
          from your teacher — then come back to this page.
        </p>
        <button
          type="button"
          onClick={() =>
            router.push(session?.join_code ? `/join?code=${session.join_code}` : "/join")
          }
          className="mt-3 rounded-md bg-amber-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-amber-700"
        >
          Open the class page
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-amber-900">
        Your class access expired — re-enter your access code to continue.
        Nothing you typed is lost.
      </p>
      <ClaimCodeForm
        studentName={name}
        joinCode={session?.join_code}
        required
        onClaimed={(resp) => {
          claim(resp, session?.join_code ?? "");
          onReclaimed();
        }}
      />
    </div>
  );
}
