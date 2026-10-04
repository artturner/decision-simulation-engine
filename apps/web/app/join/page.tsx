"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import ClaimCodeForm from "@/components/ClaimCodeForm";
import {
  ApiClientError,
  getClassPickerByCode,
  getStudentClassStatus,
  isStudentMismatchError,
  isStudentTokenError,
  looksLikeAccessCode,
  redeemClaim,
  startPlay,
} from "@/lib/api/client";
import type { StudentScenarioStatus } from "@/lib/api/types";
import { useStudentAccess } from "@/lib/useStudentAccess";

function JoinPageContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const codeFromUrl = (searchParams.get("code") ?? "").trim().toUpperCase();
  const [codeInput, setCodeInput] = useState(codeFromUrl);
  const [joinCode, setJoinCode] = useState(codeFromUrl);
  const [selectedName, setSelectedName] = useState("");
  const { session, claim, signOut, sessionFor } = useStudentAccess();

  const classQuery = useQuery({
    queryKey: ["class-code", joinCode],
    queryFn: () => getClassPickerByCode(joinCode),
    enabled: joinCode !== "",
    retry: false,
  });

  const statusQuery = useQuery({
    // Keyed on the session token too, so a successful claim refetches.
    queryKey: ["student-class-status", joinCode, selectedName, session?.token ?? ""],
    queryFn: () => getStudentClassStatus(joinCode, selectedName),
    enabled: joinCode !== "" && selectedName !== "",
    retry: false,
  });

  const startMutation = useMutation({
    mutationFn: (scenario: StudentScenarioStatus) =>
      startPlay({
        scenario_version_id: scenario.scenario_version_id,
        learner_label: selectedName,
        class_roll_id: classQuery.data!.roll_id,
      }),
    onSuccess: (data, scenario) => {
      router.push(`/${scenario.slug}/play/${data.play_id}`);
    },
  });

  function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = codeInput.trim().toUpperCase();
    setSelectedName("");
    setJoinCode(normalized);
  }

  // Recovery: students often type their personal ACCESS code (8 chars,
  // the big bold one on the handout) into this CLASS-code box. When the
  // class lookup 404s on something access-code-shaped, try redeeming it
  // directly — the server resolves the class AND the student from the
  // code, and the page lands on "Signed in as X" with their assignments.
  const directClaimMutation = useMutation({
    mutationFn: (code: string) => redeemClaim({ claim_code: code }),
    onSuccess: (resp) => {
      claim(resp, resp.join_code);
      setCodeInput(resp.join_code);
      setJoinCode(resp.join_code);
      setSelectedName(resp.student_name);
      queryClient.invalidateQueries({ queryKey: ["student-class-status"] });
    },
  });
  const triedDirectClaim = useRef<string>("");
  const classLookup404 =
    classQuery.error instanceof ApiClientError && classQuery.error.status === 404;
  useEffect(() => {
    if (
      classLookup404 &&
      looksLikeAccessCode(joinCode) &&
      triedDirectClaim.current !== joinCode &&
      !directClaimMutation.isPending
    ) {
      triedDirectClaim.current = joinCode;
      directClaimMutation.mutate(joinCode);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classLookup404, joinCode]);

  function openScenario(scenario: StudentScenarioStatus) {
    if (scenario.in_progress_play_id) {
      router.push(`/${scenario.slug}/play/${scenario.in_progress_play_id}`);
      return;
    }
    startMutation.mutate(scenario);
  }

  const classNotFound =
    classQuery.error instanceof ApiClientError && classQuery.error.status === 404;

  // Access-code state for the selected name. During the grace period the
  // form is an optional invitation; after a student_token_* 401 it is the
  // blocking gate.
  const activeSession = selectedName ? sessionFor(selectedName) : null;
  const statusBlocked =
    isStudentTokenError(statusQuery.error) ||
    isStudentMismatchError(statusQuery.error);
  const showClaimForm = selectedName !== "" && !activeSession;
  // A leftover session for someone else (shared lab computer).
  const foreignSession = selectedName && session && !activeSession ? session : null;

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 text-gray-950 md:px-8">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <header>
          <h1 className="text-3xl font-bold">Join your class</h1>
          <p className="mt-2 text-sm text-gray-600">
            Enter the class code from your teacher, then choose your name.
          </p>
        </header>

        <form
          onSubmit={submitCode}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
        >
          <label
            htmlFor="join-code"
            className="block text-sm font-semibold text-gray-700"
          >
            Class code
          </label>
          <div className="mt-2 flex gap-2">
            <input
              id="join-code"
              value={codeInput}
              onChange={(event) => setCodeInput(event.target.value)}
              className="min-w-0 flex-1 rounded-md border border-gray-300 px-3 py-2 text-base uppercase tracking-wider outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
              autoComplete="off"
            />
            <button
              type="submit"
              disabled={codeInput.trim() === "" || classQuery.isFetching}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {classQuery.isFetching ? "Finding" : "Find"}
            </button>
          </div>
          {classNotFound && directClaimMutation.isPending && (
            <p className="mt-3 text-sm text-gray-600">
              Checking that code&hellip;
            </p>
          )}
          {classNotFound &&
            !directClaimMutation.isPending &&
            (looksLikeAccessCode(joinCode) && directClaimMutation.isError ? (
              <p className="mt-3 text-sm text-red-700">
                That looks like a personal access code, but it didn&apos;t
                match one. Double-check it, or enter your <b>class code</b>{" "}
                (6 characters) from your teacher first.
              </p>
            ) : (
              <p className="mt-3 text-sm text-red-700">
                Class not found. Check the code and try again. (The class
                code is 6 characters — your personal access code comes
                after you pick your name.)
              </p>
            ))}
          {classQuery.error && !classNotFound && (
            <p className="mt-3 text-sm text-red-700">
              {(classQuery.error as Error).message}
            </p>
          )}
        </form>

        {classQuery.data && (
          <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div>
              <h2 className="text-xl font-semibold">{classQuery.data.roll_name}</h2>
              <p className="mt-1 text-sm text-gray-500">
                Code {classQuery.data.join_code}
              </p>
            </div>

            <label
              htmlFor="student-name"
              className="mt-5 block text-sm font-semibold text-gray-700"
            >
              Your name
            </label>
            <select
              id="student-name"
              value={selectedName}
              onChange={(event) => setSelectedName(event.target.value)}
              className="mt-2 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-base outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            >
              <option value="">Choose your name</option>
              {classQuery.data.student_names.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </section>
        )}

        {activeSession && (
          <p className="flex items-center justify-between rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-900">
            <span>
              Signed in as <b>{activeSession.student_name}</b>
            </span>
            <Link
              href="/me"
              className="rounded-md bg-green-700 px-3 py-1 font-semibold text-white hover:bg-green-800"
            >
              My dashboard →
            </Link>
            <button
              type="button"
              onClick={() => {
                signOut();
                setSelectedName("");
              }}
              className="font-semibold text-green-800 underline hover:text-green-900"
            >
              Not you?
            </button>
          </p>
        )}

        {foreignSession && (
          <p className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900">
            <span>
              This device is signed in as <b>{foreignSession.student_name}</b>.
            </span>
            <button
              type="button"
              onClick={signOut}
              className="font-semibold text-amber-800 underline hover:text-amber-900"
            >
              Sign them out
            </button>
          </p>
        )}

        {showClaimForm && (
          <ClaimCodeForm
            studentName={selectedName}
            joinCode={joinCode}
            required={statusBlocked}
            onClaimed={(resp) => {
              claim(resp, joinCode);
              // The status query key includes the token, so it refetches;
              // drop any stale blocked result immediately.
              queryClient.invalidateQueries({
                queryKey: ["student-class-status"],
              });
            }}
          />
        )}

        {statusQuery.isFetching && selectedName && (
          <p className="text-sm text-gray-500">Loading assignments...</p>
        )}

        {statusQuery.error && !statusBlocked && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {(statusQuery.error as Error).message}
          </p>
        )}

        {statusQuery.data && (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Assigned scenarios
            </h2>
            {statusQuery.data.scenarios.length === 0 ? (
              <p className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-500">
                No scenarios are available yet.
              </p>
            ) : (
              statusQuery.data.scenarios.map((scenario) => {
                const isStarting =
                  startMutation.isPending &&
                  startMutation.variables?.scenario_version_id ===
                    scenario.scenario_version_id;
                const label = scenario.in_progress_play_id
                  ? "Resume"
                  : scenario.submitted_count > 0
                    ? "Start another attempt"
                    : "Start";

                return (
                  <article
                    key={scenario.scenario_version_id}
                    className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
                  >
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h3 className="font-semibold">{scenario.title}</h3>
                        {scenario.description && (
                          <p className="mt-1 text-sm text-gray-500">
                            {scenario.description}
                          </p>
                        )}
                        <p className="mt-2 text-xs text-gray-500">
                          Submitted attempts: {scenario.submitted_count}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => openScenario(scenario)}
                        disabled={isStarting}
                        className="shrink-0 rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isStarting ? "Starting" : label}
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </section>
        )}

        {startMutation.error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {(startMutation.error as Error).message}
          </p>
        )}
      </div>
    </main>
  );
}

export default function JoinPage() {
  return (
    <Suspense fallback={null}>
      <JoinPageContent />
    </Suspense>
  );
}
