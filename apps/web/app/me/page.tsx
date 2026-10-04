"use client";

/**
 * /me — the student's live progress dashboard.
 *
 * Keyed to the claimed access code: with no (valid) session the page is a
 * sign-in gate that redeems the 8-character code alone, the same name-less
 * redeem the join page uses for its access-code recovery.
 */

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import DashboardView from "@/components/dashboard/DashboardView";
import {
  ApiClientError,
  getStudentDashboard,
  isStudentTokenError,
  redeemClaim,
  retryUnlessAuth,
} from "@/lib/api/client";
import { useStudentAccess } from "@/lib/useStudentAccess";
import "./dashboard.css";

function SignInGate({ reason, onClaimed }: { reason: string | null; onClaimed: ReturnType<typeof useStudentAccess>["claim"] }) {
  const [code, setCode] = useState("");
  const redeem = useMutation({
    mutationFn: () => redeemClaim({ claim_code: code.replace(/[\s-]/g, "").toUpperCase() }),
    onSuccess: (resp) => onClaimed(resp, resp.join_code),
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (code.trim()) redeem.mutate();
  }
  const err = redeem.error;
  const errText =
    err instanceof ApiClientError && err.code === "claim_code_not_found"
      ? "That code isn't valid. Check it carefully (no class code here — use your personal 8-character access code), or ask your teacher for a new one."
      : err
        ? (err as Error).message
        : null;
  return (
    <div className="dsh-gate">
      <h1>Your personal dashboard</h1>
      <p>
        See every grade in one place, what&apos;s due next, your best next move, and tips to raise your grade. Live
        across videos, scenarios, and FRQs.
      </p>
      {reason && <div className="dsh-warn">{reason}</div>}
      <form onSubmit={submit}>
        <input
          aria-label="Personal access code"
          placeholder="ACCESS CODE"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          maxLength={12}
        />
        <button className="dsh-go" type="submit" disabled={redeem.isPending}>
          {redeem.isPending ? "…" : "Unlock"}
        </button>
      </form>
      {errText && <div className="dsh-err" role="alert">{errText}</div>}
      <p style={{ fontSize: 13, marginTop: 14 }}>
        Your access code is the 8-character code on the slip from your teacher. Lost it? Ask for a new one.
      </p>
      <div className="dsh-teaser">
        <div><b>Next best move</b>The one task that helps your grade most right now.</div>
        <div><b>Live checklist</b>Every assignment, ticked off as you finish.</div>
        <div><b>XP &amp; badges</b>Level up from Bystander to Founder.</div>
      </div>
    </div>
  );
}

export default function MyDashboardPage() {
  const { session, claim, signOut } = useStudentAccess();
  const [hydrated, setHydrated] = useState(false);
  const [gateReason, setGateReason] = useState<string | null>(null);
  useEffect(() => setHydrated(true), []);

  const q = useQuery({
    queryKey: ["student-dashboard", session?.token ?? ""],
    queryFn: getStudentDashboard,
    enabled: !!session,
    retry: retryUnlessAuth,
    staleTime: 60_000,
    refetchInterval: 5 * 60_000,
  });

  // A revoked/expired code: drop the session and show the gate with a reason.
  useEffect(() => {
    if (q.error && isStudentTokenError(q.error)) {
      signOut();
      setGateReason("Your access code was reset or expired. Enter your current code to continue.");
    }
  }, [q.error, signOut]);

  let body: React.ReactNode;
  if (!hydrated) {
    body = null;
  } else if (!session) {
    body = (
      <SignInGate
        reason={gateReason}
        onClaimed={(resp, jc) => {
          setGateReason(null);
          return claim(resp, jc);
        }}
      />
    );
  } else if (q.error) {
    body = (
      <div className="dsh-warn" style={{ marginTop: 40 }} role="alert">
        Couldn&apos;t load your dashboard ({(q.error as Error).message}).{" "}
        <button className="dsh-btn" onClick={() => q.refetch()}>Try again</button>
      </div>
    );
  } else if (!q.data) {
    body = (
      <div style={{ display: "grid", gap: 16, marginTop: 28 }} aria-busy="true" aria-label="Loading your dashboard">
        <div className="dsh-skel" style={{ height: 44, width: "40%" }} />
        <div className="dsh-skel" style={{ height: 190 }} />
        <div className="dsh-skel" style={{ height: 130 }} />
        <div className="dsh-skel" style={{ height: 320 }} />
      </div>
    );
  } else if (!q.data.plan_available || !q.data.dashboard) {
    body = (
      <div className="dsh-gate">
        <h1>Almost there</h1>
        <p>
          You&apos;re signed in as <b>{q.data.student.name}</b>, but your teacher&apos;s course isn&apos;t set up for the
          dashboard yet. Your assignments are still on the <Link href={`/join?code=${q.data.student.join_code}`} style={{ textDecoration: "underline" }}>class page</Link>.
        </p>
      </div>
    );
  } else {
    body = <DashboardView data={q.data} />;
  }

  return (
    <main className="dsh">
      <div className="dsh-wrap">
        <header className="dsh-top">
          <div className="dsh-brand">
            Crux <b>Labs</b> · My Progress
          </div>
          {session && (
            <div className="dsh-who">
              <span>
                Signed in as <strong>{session.student_name}</strong>
              </span>
              <Link className="dsh-btn" href={`/join?code=${session.join_code}`}>Class page</Link>
              <button className="dsh-btn" onClick={() => q.refetch()} disabled={q.isFetching}>
                {q.isFetching ? "Refreshing…" : "Refresh"}
              </button>
              <button className="dsh-btn" onClick={signOut}>Not you? Sign out</button>
            </div>
          )}
        </header>
        {body}
      </div>
    </main>
  );
}
