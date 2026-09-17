"use client";

/**
 * Access-code entry. Rendered as an optional invitation during the
 * grace period and as a required gate once enforcement is on (or after
 * a 401 anywhere in the student flow).
 */

import { useMutation } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { ApiClientError, redeemClaim } from "@/lib/api/client";
import type { ClaimRedeemResponse } from "@/lib/api/types";

interface ClaimCodeFormProps {
  studentName: string;
  /** Passed when known (join pages); essay-style callers omit it. */
  joinCode?: string;
  /** Required = blocking gate copy; optional = grace-period invitation. */
  required: boolean;
  onClaimed: (resp: ClaimRedeemResponse) => void;
}

export default function ClaimCodeForm({
  studentName,
  joinCode,
  required,
  onClaimed,
}: ClaimCodeFormProps) {
  const [code, setCode] = useState("");

  const redeemMutation = useMutation({
    mutationFn: () =>
      redeemClaim({
        claim_code: code,
        student_name: studentName,
        ...(joinCode ? { join_code: joinCode } : {}),
      }),
    onSuccess: onClaimed,
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (code.trim() !== "") redeemMutation.mutate();
  }

  const err = redeemMutation.error;
  let errorCopy: string | null = null;
  if (err instanceof ApiClientError) {
    if (err.code === "claim_code_not_found") {
      errorCopy =
        "That code isn't valid. Check it carefully, or ask your teacher for a new one.";
    } else if (err.code === "claim_code_wrong_name") {
      errorCopy = `This code belongs to a different name — make sure you picked yourself (${studentName}).`;
    } else {
      errorCopy = err.message;
    }
  } else if (err) {
    errorCopy = (err as Error).message;
  }

  return (
    <form
      onSubmit={submit}
      className={`rounded-lg border p-4 shadow-sm ${
        required ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-white"
      }`}
    >
      <label
        htmlFor="claim-code"
        className="block text-sm font-semibold text-gray-700"
      >
        {required
          ? `Enter your access code to see your work, ${studentName}`
          : "Have an access code from your teacher? Enter it here"}
      </label>
      {!required && (
        <p className="mt-1 text-xs text-gray-500">
          Soon your access code will be needed to open your work. The same
          code works on the essays site.
        </p>
      )}
      <div className="mt-2 flex gap-2">
        <input
          id="claim-code"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          placeholder="e.g. XK7RP2WM"
          className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-base uppercase tracking-widest outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
          autoComplete="off"
        />
        <button
          type="submit"
          disabled={code.trim() === "" || redeemMutation.isPending}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {redeemMutation.isPending ? "Checking" : "Unlock"}
        </button>
      </div>
      {errorCopy && <p className="mt-3 text-sm text-red-700">{errorCopy}</p>}
    </form>
  );
}
