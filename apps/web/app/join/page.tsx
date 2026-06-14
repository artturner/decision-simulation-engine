"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import {
  ApiClientError,
  getClassPickerByCode,
  getStudentClassStatus,
  startPlay,
} from "@/lib/api/client";
import type { StudentScenarioStatus } from "@/lib/api/types";

export default function JoinPage() {
  const router = useRouter();
  const [codeInput, setCodeInput] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [selectedName, setSelectedName] = useState("");

  const classQuery = useQuery({
    queryKey: ["class-code", joinCode],
    queryFn: () => getClassPickerByCode(joinCode),
    enabled: joinCode !== "",
    retry: false,
  });

  const statusQuery = useQuery({
    queryKey: ["student-class-status", joinCode, selectedName],
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

  function openScenario(scenario: StudentScenarioStatus) {
    if (scenario.in_progress_play_id) {
      router.push(`/${scenario.slug}/play/${scenario.in_progress_play_id}`);
      return;
    }
    startMutation.mutate(scenario);
  }

  const classNotFound =
    classQuery.error instanceof ApiClientError && classQuery.error.status === 404;

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
          {classNotFound && (
            <p className="mt-3 text-sm text-red-700">
              Class not found. Check the code and try again.
            </p>
          )}
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

        {statusQuery.isFetching && selectedName && (
          <p className="text-sm text-gray-500">Loading assignments...</p>
        )}

        {statusQuery.error && (
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
