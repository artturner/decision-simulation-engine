"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ApiClientError, getClassPicker, startPlay } from "@/lib/api/client";
import type { ClassPickerScenario } from "@/lib/api/types";

export default function ClassPickerPage() {
  const params = useParams();
  const rollId = params.rollId as string;
  const router = useRouter();

  const [selectedName, setSelectedName] = useState<string>("");
  const [selectedScenario, setSelectedScenario] =
    useState<ClassPickerScenario | null>(null);

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

  // ------------------------------------------------------------------
  // Start play mutation — passes name + roll context to the API
  // ------------------------------------------------------------------
  const startMutation = useMutation({
    mutationFn: () =>
      startPlay({
        scenario_version_id: selectedScenario!.scenario_version_id,
        learner_label: selectedName,
        class_roll_id: rollId,
      }),
    onSuccess: (data) => {
      router.push(`/${selectedScenario!.slug}/play/${data.play_id}`);
    },
  });

  const canStart = selectedName !== "" && selectedScenario !== null;

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
        {roll.scenarios.length === 0 ? (
          <p className="text-center text-sm text-gray-400">
            No scenarios are available yet. Check back later.
          </p>
        ) : (
          <section className="space-y-3">
            <h2 className="text-sm font-semibold text-gray-700">
              Choose a scenario
            </h2>
            {roll.scenarios.map((scenario) => {
              const isSelected =
                selectedScenario?.scenario_version_id ===
                scenario.scenario_version_id;
              return (
                <button
                  key={scenario.scenario_version_id}
                  onClick={() =>
                    setSelectedScenario(isSelected ? null : scenario)
                  }
                  className={`w-full rounded-xl border-2 p-4 text-left transition ${
                    isSelected
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 bg-white hover:border-blue-300"
                  }`}
                >
                  <p className="font-semibold text-gray-900">{scenario.title}</p>
                  {scenario.description && (
                    <p className="mt-1 text-sm text-gray-500 line-clamp-2">
                      {scenario.description}
                    </p>
                  )}
                </button>
              );
            })}
          </section>
        )}

        {/* Error from start */}
        {startMutation.error && (
          <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {(startMutation.error as Error).message}
          </p>
        )}

        {/* Start button */}
        <button
          onClick={() => startMutation.mutate()}
          disabled={!canStart || startMutation.isPending}
          className="w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {startMutation.isPending ? "Starting…" : "Begin Scenario"}
        </button>

      </div>
    </main>
  );
}
