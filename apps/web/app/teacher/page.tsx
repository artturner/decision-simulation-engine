"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  assignScenario,
  createRoll,
  getRollGradebook,
  listPublishedScenarios,
  listRolls,
  listRollScenarios,
  updateAssignment,
  updateRoll,
} from "@/lib/api/teacher";
import type {
  ClassRoll,
  PublishedScenario,
  RollGradebook,
  RollScenario,
} from "@/lib/api/teacherTypes";
import { getSupabaseClient } from "@/lib/auth/supabase";

function parseRoster(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((name) => name.trim())
    .filter(Boolean);
}

function rosterText(roll: ClassRoll | null): string {
  return roll ? roll.student_names.join("\n") : "";
}

function statusLabel(status: string): string {
  if (status === "in_progress") return "In progress";
  if (status === "completed") return "Completed";
  return "Not started";
}

export default function TeacherDashboardPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const supabase = getSupabaseClient();
  const [session, setSession] = useState<Session | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [selectedRollId, setSelectedRollId] = useState<string>("");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [className, setClassName] = useState("");
  const [studentNames, setStudentNames] = useState("");
  const [assignmentScenarioId, setAssignmentScenarioId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) {
      setCheckingAuth(false);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setCheckingAuth(false);
      if (!data.session) {
        router.replace("/teacher/login");
      }
    });

    const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      if (!next) {
        router.replace("/teacher/login");
      }
    });

    return () => listener.subscription.unsubscribe();
  }, [router, supabase]);

  const token = session?.access_token ?? "";

  const rollsQuery = useQuery({
    queryKey: ["teacher-rolls"],
    queryFn: () => listRolls(token),
    enabled: Boolean(token),
  });

  const scenariosQuery = useQuery({
    queryKey: ["teacher-published-scenarios"],
    queryFn: () => listPublishedScenarios(token),
    enabled: Boolean(token),
  });

  const selectedRoll = useMemo(() => {
    return rollsQuery.data?.find((roll) => roll.id === selectedRollId) ?? null;
  }, [rollsQuery.data, selectedRollId]);

  useEffect(() => {
    if (!selectedRollId && rollsQuery.data?.length) {
      setSelectedRollId(rollsQuery.data[0].id);
    }
  }, [rollsQuery.data, selectedRollId]);

  useEffect(() => {
    setClassName(selectedRoll?.name ?? "");
    setStudentNames(rosterText(selectedRoll));
  }, [selectedRoll]);

  const assignmentsQuery = useQuery({
    queryKey: ["teacher-roll-scenarios", selectedRollId],
    queryFn: () => listRollScenarios(token, selectedRollId),
    enabled: Boolean(token && selectedRollId),
  });

  useEffect(() => {
    if (!selectedScenarioId && assignmentsQuery.data?.length) {
      setSelectedScenarioId(assignmentsQuery.data[0].scenario_id);
    }
    if (
      selectedScenarioId &&
      assignmentsQuery.data &&
      !assignmentsQuery.data.some((item) => item.scenario_id === selectedScenarioId)
    ) {
      setSelectedScenarioId(assignmentsQuery.data[0]?.scenario_id ?? "");
    }
  }, [assignmentsQuery.data, selectedScenarioId]);

  const gradebookQuery = useQuery({
    queryKey: ["teacher-gradebook", selectedRollId, selectedScenarioId],
    queryFn: () => getRollGradebook(token, selectedRollId, selectedScenarioId),
    enabled: Boolean(token && selectedRollId && selectedScenarioId),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createRoll(token, {
        name: className.trim(),
        student_names: parseRoster(studentNames),
      }),
    onSuccess: (roll) => {
      setNotice(`Created ${roll.name}. Class code: ${roll.join_code}`);
      setSelectedRollId(roll.id);
      queryClient.invalidateQueries({ queryKey: ["teacher-rolls"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: () =>
      updateRoll(token, selectedRollId, {
        name: className.trim(),
        student_names: parseRoster(studentNames),
      }),
    onSuccess: () => {
      setNotice("Class updated.");
      queryClient.invalidateQueries({ queryKey: ["teacher-rolls"] });
      queryClient.invalidateQueries({ queryKey: ["teacher-gradebook"] });
    },
  });

  const assignMutation = useMutation({
    mutationFn: () =>
      assignScenario(token, selectedRollId, {
        scenario_id: assignmentScenarioId,
        visible: true,
      }),
    onSuccess: (assignment) => {
      setNotice("Scenario assigned.");
      setSelectedScenarioId(assignment.scenario_id);
      setAssignmentScenarioId("");
      queryClient.invalidateQueries({ queryKey: ["teacher-roll-scenarios"] });
    },
  });

  const visibilityMutation = useMutation({
    mutationFn: (assignment: RollScenario) =>
      updateAssignment(token, selectedRollId, assignment.scenario_id, {
        visible: !assignment.visible,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["teacher-roll-scenarios"] });
    },
  });

  const shareText = selectedRoll
    ? `Go to ${typeof window === "undefined" ? "" : window.location.origin}/join\nEnter class code: ${selectedRoll.join_code}\nSelect your name.`
    : "";

  async function signOut() {
    await supabase?.auth.signOut();
    router.replace("/teacher/login");
  }

  function submitClass(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);
    if (!className.trim() || parseRoster(studentNames).length === 0) {
      setNotice("Add a class name and at least one student.");
      return;
    }
    if (selectedRoll) {
      updateMutation.mutate();
    } else {
      createMutation.mutate();
    }
  }

  if (checkingAuth) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">Checking sign in...</p>
      </main>
    );
  }

  if (!supabase) {
    return (
      <main className="flex min-h-screen items-center justify-center p-8">
        <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
          Supabase environment variables are not configured.
        </p>
      </main>
    );
  }

  if (!session) {
    return null;
  }

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-6 text-gray-950 md:px-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="flex flex-col gap-3 border-b border-gray-200 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-bold">Teacher dashboard</h1>
            <p className="mt-1 text-sm text-gray-600">{session.user.email}</p>
          </div>
          <button
            type="button"
            onClick={signOut}
            className="self-start rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-white"
          >
            Sign out
          </button>
        </header>

        {notice && (
          <p className="rounded-lg bg-blue-50 px-4 py-3 text-sm text-blue-800">
            {notice}
          </p>
        )}

        <section className="grid gap-4 lg:grid-cols-[280px_1fr]">
          <aside className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">Classes</h2>
              <button
                type="button"
                onClick={() => {
                  setSelectedRollId("");
                  setClassName("");
                  setStudentNames("");
                  setSelectedScenarioId("");
                }}
                className="rounded-md bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                New
              </button>
            </div>

            {rollsQuery.isLoading ? (
              <p className="mt-4 text-sm text-gray-500">Loading classes...</p>
            ) : rollsQuery.data?.length ? (
              <div className="mt-4 space-y-2">
                {rollsQuery.data.map((roll) => (
                  <button
                    key={roll.id}
                    type="button"
                    onClick={() => setSelectedRollId(roll.id)}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm ${
                      selectedRollId === roll.id
                        ? "border-blue-500 bg-blue-50"
                        : "border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <span className="block font-semibold">{roll.name}</span>
                    <span className="text-gray-500">
                      {roll.join_code} · {roll.student_names.length} students
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-gray-500">
                Create your first class.
              </p>
            )}
          </aside>

          <div className="space-y-4">
            <ClassEditor
              selectedRoll={selectedRoll}
              classNameValue={className}
              studentNames={studentNames}
              busy={createMutation.isPending || updateMutation.isPending}
              error={
                (createMutation.error as Error | null)?.message ??
                (updateMutation.error as Error | null)?.message ??
                null
              }
              onClassNameChange={setClassName}
              onStudentNamesChange={setStudentNames}
              onSubmit={submitClass}
            />

            {selectedRoll && (
              <>
                <SharePanel
                  roll={selectedRoll}
                  shareText={shareText}
                  onCopy={() => {
                    navigator.clipboard?.writeText(shareText);
                    setNotice("Student instructions copied.");
                  }}
                />

                <ScenarioAssignments
                  scenarios={scenariosQuery.data ?? []}
                  assignments={assignmentsQuery.data ?? []}
                  selectedScenarioId={selectedScenarioId}
                  assignmentScenarioId={assignmentScenarioId}
                  busy={assignMutation.isPending}
                  error={
                    (assignMutation.error as Error | null)?.message ??
                    (visibilityMutation.error as Error | null)?.message ??
                    null
                  }
                  onAssignmentScenarioChange={setAssignmentScenarioId}
                  onAssign={() => assignMutation.mutate()}
                  onSelectScenario={setSelectedScenarioId}
                  onToggleVisible={(assignment) =>
                    visibilityMutation.mutate(assignment)
                  }
                />

                <ResultsPanel
                  gradebook={gradebookQuery.data ?? null}
                  loading={gradebookQuery.isLoading}
                  error={(gradebookQuery.error as Error | null)?.message ?? null}
                />
              </>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function ClassEditor({
  selectedRoll,
  classNameValue,
  studentNames,
  busy,
  error,
  onClassNameChange,
  onStudentNamesChange,
  onSubmit,
}: {
  selectedRoll: ClassRoll | null;
  classNameValue: string;
  studentNames: string;
  busy: boolean;
  error: string | null;
  onClassNameChange: (value: string) => void;
  onStudentNamesChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold">
        {selectedRoll ? "Edit class" : "Create class"}
      </h2>
      <form onSubmit={onSubmit} className="mt-4 grid gap-4">
        <label className="block">
          <span className="text-sm font-semibold text-gray-700">Class name</span>
          <input
            value={classNameValue}
            onChange={(event) => onClassNameChange(event.target.value)}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="Period 3"
          />
        </label>

        <label className="block">
          <span className="text-sm font-semibold text-gray-700">
            Student names
          </span>
          <textarea
            value={studentNames}
            onChange={(event) => onStudentNamesChange(event.target.value)}
            rows={8}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder={"Jane Smith\nMarcus Lee\nAva Johnson"}
          />
        </label>

        {error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="justify-self-start rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Saving" : selectedRoll ? "Save class" : "Create class"}
        </button>
      </form>
    </section>
  );
}

function SharePanel({
  roll,
  shareText,
  onCopy,
}: {
  roll: ClassRoll;
  shareText: string;
  onCopy: () => void;
}) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">Student access</h2>
          <p className="mt-1 text-sm text-gray-600">
            Class code: <span className="font-mono font-bold">{roll.join_code}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          Copy instructions
        </button>
      </div>
      <pre className="mt-4 whitespace-pre-wrap rounded-md bg-gray-50 p-3 text-sm text-gray-700">
        {shareText}
      </pre>
    </section>
  );
}

function ScenarioAssignments({
  scenarios,
  assignments,
  selectedScenarioId,
  assignmentScenarioId,
  busy,
  error,
  onAssignmentScenarioChange,
  onAssign,
  onSelectScenario,
  onToggleVisible,
}: {
  scenarios: PublishedScenario[];
  assignments: RollScenario[];
  selectedScenarioId: string;
  assignmentScenarioId: string;
  busy: boolean;
  error: string | null;
  onAssignmentScenarioChange: (value: string) => void;
  onAssign: () => void;
  onSelectScenario: (value: string) => void;
  onToggleVisible: (assignment: RollScenario) => void;
}) {
  const assignedIds = new Set(assignments.map((item) => item.scenario_id));
  const available = scenarios.filter((scenario) => !assignedIds.has(scenario.id));

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Scenario assignments</h2>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <select
          value={assignmentScenarioId}
          onChange={(event) => onAssignmentScenarioChange(event.target.value)}
          className="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        >
          <option value="">Choose a published scenario</option>
          {available.map((scenario) => (
            <option key={scenario.id} value={scenario.id}>
              {scenario.title}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={onAssign}
          disabled={!assignmentScenarioId || busy}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Assigning" : "Assign"}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      )}

      {assignments.length ? (
        <div className="mt-4 space-y-2">
          {assignments.map((assignment) => (
            <div
              key={assignment.id}
              className={`rounded-md border p-3 ${
                selectedScenarioId === assignment.scenario_id
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200"
              }`}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <button
                  type="button"
                  onClick={() => onSelectScenario(assignment.scenario_id)}
                  className="text-left"
                >
                  <span className="block font-semibold">{assignment.title}</span>
                  <span className="text-sm text-gray-500">
                    {assignment.visible ? "Visible to students" : "Hidden"}
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => onToggleVisible(assignment)}
                  className="rounded-md border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700 hover:bg-white"
                >
                  {assignment.visible ? "Hide" : "Show"}
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-gray-500">
          Assign Liberty Park or another published scenario to begin.
        </p>
      )}
    </section>
  );
}

function ResultsPanel({
  gradebook,
  loading,
  error,
}: {
  gradebook: RollGradebook | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <p className="text-sm text-gray-500">Loading results...</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </p>
      </section>
    );
  }

  if (!gradebook) {
    return (
      <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
        <p className="text-sm text-gray-500">
          Select an assigned scenario to view results.
        </p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Results: {gradebook.scenario_title}</h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-600">
              <th className="py-2 pr-3 font-semibold">Student</th>
              <th className="py-2 pr-3 font-semibold">Status</th>
              <th className="py-2 pr-3 font-semibold">Attempts</th>
              <th className="py-2 pr-3 font-semibold">Latest submitted</th>
              <th className="py-2 pr-3 font-semibold">Reflection</th>
            </tr>
          </thead>
          <tbody>
            {gradebook.students.map((student) => {
              const latestReflection = [...student.attempts]
                .reverse()
                .find((attempt) => attempt.reflection)?.reflection;
              return (
                <tr key={student.student_name} className="border-b border-gray-100">
                  <td className="py-3 pr-3 font-medium">{student.student_name}</td>
                  <td className="py-3 pr-3">{statusLabel(student.status)}</td>
                  <td className="py-3 pr-3">{student.submitted_count}</td>
                  <td className="py-3 pr-3">
                    {student.latest_submitted_at
                      ? new Date(student.latest_submitted_at).toLocaleString()
                      : ""}
                  </td>
                  <td className="py-3 pr-3">
                    {latestReflection ? (
                      <div className="space-y-1">
                        {Object.entries(latestReflection.responses).map(
                          ([key, value]) => (
                            <p key={key}>
                              <span className="font-semibold">{key}: </span>
                              {value}
                            </p>
                          ),
                        )}
                      </div>
                    ) : (
                      <span className="text-gray-400">None</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
