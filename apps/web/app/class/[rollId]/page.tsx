"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import {
  ApiClientError,
  getClassPicker,
  getStudentClassStatus,
  startPlay,
} from "@/lib/api/client";
import type { StudentScenarioStatus } from "@/lib/api/types";

export default function ClassPickerPage() {
  const params = useParams();
  const rollId = params.rollId as string;
  const router = useRouter();

  const [selectedName, setSelectedName] = useState<string>("");

  // ------------------------------------------------------------------
  // Fetch roll + visible scenarios
  // ------------------------------------------------------------------
  const {
    data: roll,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["class", rollId],
    queryFn: () => getClassPicker(rollId),
    enabled: Boolean(rollId),
  });

  const {
    data: status,
    isLoading: statusLoading,
    error: statusError,
  } = useQuery({
    queryKey: ["student-class-status", roll?.join_code, selectedName],
    queryFn: () => getStudentClassStatus(roll!.join_code, selectedName),
    enabled: Boolean(roll?.join_code && selectedName),
  });

  // ------------------------------------------------------------------
  // Start play mutation — passes name + roll context to the API
  // ------------------------------------------------------------------
  const startMutation = useMutation({
    mutationFn: (scenario: StudentScenarioStatus) =>
      startPlay({
        scenario_version_id: scenario.scenario_version_id,
        learner_label: selectedName,
        class_roll_id: rollId,
      }),
    onSuccess: (data, scenario) => {
      router.push(`/${scenario.slug}/play/${data.play_id}`);
    },
  });

  function openScenario(scenario: StudentScenarioStatus) {
    if (scenario.in_progress_play_id) {
      router.push(`/${scenario.slug}/play/${scenario.in_progress_play_id}`);
      return;
    }
    startMutation.mutate(scenario);
  }

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">Loading class…</p>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Error
  // ------------------------------------------------------------------
  if (error || !roll) {
    const is404 = error instanceof ApiClientError && error.status === 404;
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-bold text-gray-800">
          {is404 ? "Class not found" : "Something went wrong"}
        </h1>
        <p className="text-gray-500">
          {is404
            ? "This class link is no longer valid. Ask your teacher for a new one."
            : (error as Error).message}
        </p>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Class picker UI
  // ------------------------------------------------------------------
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 p-4 md:p-8">
      <div className="w-full max-w-lg space-y-6">

        {/* Header */}
        <header>
          <h1 className="text-2xl font-bold text-gray-900">{roll.roll_name}</h1>
          <p className="mt-1 text-sm text-gray-500">
            Select your name and a scenario to begin.
          </p>
        </header>

        {/* Name picker */}
        <section className="rounded-2xl bg-white p-6 shadow-sm">
          <label
            htmlFor="student-name"
            className="block text-sm font-semibold text-gray-700"
          >
            Your name
          </label>
          <select
            id="student-name"
            value={selectedName}
            onChange={(e) => setSelectedName(e.target.value)}
            className="mt-2 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">— Choose your name —</option>
            {roll.student_names.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </section>

        {/* Scenario list */}
        {statusLoading && selectedName ? (
          <p className="text-center text-sm text-gray-400">
            Loading assignments...
          </p>
        ) : statusError ? (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {(statusError as Error).message}
          </p>
        ) : status && status.scenarios.length === 0 ? (
          <p className="text-center text-sm text-gray-400">
            No scenarios are available yet. Check back later.
          </p>
        ) : status ? (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Choose a scenario
            </h2>
            {status.scenarios.map((scenario) => {
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
                <button
                  key={scenario.scenario_version_id}
                  onClick={() => openScenario(scenario)}
                  disabled={isStarting}
                  className="w-full rounded-xl border-2 border-gray-200 bg-white p-4 text-left transition hover:border-blue-300 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="font-semibold text-gray-900">{scenario.title}</p>
                    <span className="shrink-0 text-sm font-semibold text-blue-700">
                      {isStarting ? "Starting" : label}
                    </span>
                  </div>
                  {scenario.description && (
                    <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                      {scenario.description}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-gray-500">
                    Submitted attempts: {scenario.submitted_count}
                  </p>
                </button>
              );
            })}
          </section>
        ) : selectedName ? null : (
          <p className="text-center text-sm text-gray-400">
            Choose your name to see assigned scenarios.
          </p>
        )}

        {/* Error from start */}
        {startMutation.error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {(startMutation.error as Error).message}
          </p>
        )}

      </div>
    </main>
  );
}
