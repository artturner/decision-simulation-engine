"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Session } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  assignScenario,
  createRoll,
  downloadRollGradebookCsv,
  getRollGradebook,
  listPublishedScenarios,
  listRolls,
  listRollScenarios,
  updateAssignment,
  updateRoll,
} from "@/lib/api/teacher";
import type {
  ClassRoll,
  GradingDifficulty,
  PublishedScenario,
  RollGradebook,
  RollGradebookStudent,
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

  const difficultyMutation = useMutation({
    mutationFn: (vars: {
      assignment: RollScenario;
      difficulty: GradingDifficulty;
    }) =>
      updateAssignment(token, selectedRollId, vars.assignment.scenario_id, {
        grading_difficulty: vars.difficulty,
      }),
    onSuccess: (_data, vars) => {
      setNotice(`Grading difficulty set to ${vars.difficulty}.`);
      queryClient.invalidateQueries({ queryKey: ["teacher-roll-scenarios"] });
      queryClient.invalidateQueries({ queryKey: ["teacher-gradebook"] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      downloadRollGradebookCsv(token, selectedRollId, selectedScenarioId),
    onSuccess: (blob) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `gradebook-${selectedRoll?.join_code ?? selectedRollId}-${selectedScenarioId}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setNotice("Gradebook CSV downloaded.");
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
                    (difficultyMutation.error as Error | null)?.message ??
                    null
                  }
                  onAssignmentScenarioChange={setAssignmentScenarioId}
                  onAssign={() => assignMutation.mutate()}
                  onSelectScenario={setSelectedScenarioId}
                  onToggleVisible={(assignment) =>
                    visibilityMutation.mutate(assignment)
                  }
                  onChangeDifficulty={(assignment, difficulty) =>
                    difficultyMutation.mutate({ assignment, difficulty })
                  }
                  difficultyBusy={difficultyMutation.isPending}
                />

                <ResultsPanel
                  gradebook={gradebookQuery.data ?? null}
                  loading={gradebookQuery.isLoading}
                  error={
                    (gradebookQuery.error as Error | null)?.message ??
                    (exportMutation.error as Error | null)?.message ??
                    null
                  }
                  exporting={exportMutation.isPending}
                  onExport={() => exportMutation.mutate()}
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
  onChangeDifficulty,
  difficultyBusy,
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
  onChangeDifficulty: (
    assignment: RollScenario,
    difficulty: GradingDifficulty,
  ) => void;
  difficultyBusy: boolean;
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
              <div className="mt-3 flex flex-col gap-1 border-t border-gray-200 pt-3 sm:flex-row sm:items-center sm:justify-between">
                <label
                  htmlFor={`difficulty-${assignment.id}`}
                  className="text-sm font-semibold text-gray-700"
                >
                  Grading difficulty
                </label>
                <select
                  id={`difficulty-${assignment.id}`}
                  value={assignment.grading_difficulty}
                  disabled={difficultyBusy}
                  onChange={(event) =>
                    onChangeDifficulty(
                      assignment,
                      event.target.value as GradingDifficulty,
                    )
                  }
                  className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:opacity-50"
                >
                  <option value="lenient">Lenient — generous, formative</option>
                  <option value="standard">Standard — balanced</option>
                  <option value="strict">Strict — high-stakes</option>
                </select>
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

const DIFFICULTY_LABELS: Record<GradingDifficulty, string> = {
  lenient: "Lenient",
  standard: "Standard",
  strict: "Strict",
};

function difficultyLabel(value: string | null): string {
  if (value && value in DIFFICULTY_LABELS) {
    return DIFFICULTY_LABELS[value as GradingDifficulty];
  }
  return "—";
}

function reflectionQuestionLabel(key: string): string {
  const match = key.match(/^reflection_(\d+)$/);
  return match ? `Reflection ${match[1]}` : key;
}

function ResultsPanel({
  gradebook,
  loading,
  error,
  exporting,
  onExport,
}: {
  gradebook: RollGradebook | null;
  loading: boolean;
  error: string | null;
  exporting: boolean;
  onExport: () => void;
}) {
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const scenarioId = gradebook?.scenario_id;

  // Clear the open detail when the teacher switches scenario.
  useEffect(() => {
    setSelectedName(null);
  }, [scenarioId]);

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

  const selectedStudent =
    selectedName != null
      ? gradebook.students.find((s) => s.student_name === selectedName) ?? null
      : null;

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold">
            Results: {gradebook.scenario_title}
          </h2>
          <div className="mt-1 flex items-center gap-2 text-sm text-gray-600">
            <span>Grading difficulty:</span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-gray-700">
              {difficultyLabel(gradebook.grading_difficulty)}
            </span>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            Best attempt is the highest-scoring completed attempt. Select a
            student to read their reflection and coaching.
          </p>
        </div>
        <button
          type="button"
          onClick={onExport}
          disabled={exporting}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {exporting ? "Exporting" : "Export CSV"}
        </button>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-600">
              <th className="py-2 pr-3 font-semibold">Student</th>
              <th className="py-2 pr-3 font-semibold">Status</th>
              <th className="py-2 pr-3 font-semibold">Attempts</th>
              <th className="py-2 pr-3 font-semibold">Grade</th>
              <th className="py-2 pr-3 font-semibold">Best submitted</th>
              <th className="py-2 pr-3 font-semibold">Best outcome</th>
              <th className="py-2 pr-3 font-semibold">Reflection</th>
            </tr>
          </thead>
          <tbody>
            {gradebook.students.map((student) => {
              const bestAttempt = student.best_attempt;
              const bestReflection = bestAttempt?.reflection;
              const isSelected = selectedName === student.student_name;
              return (
                <tr
                  key={student.student_name}
                  className={`border-b border-gray-100 ${
                    isSelected ? "bg-blue-50" : ""
                  }`}
                >
                  <td className="py-3 pr-3 font-medium">
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedName(
                          isSelected ? null : student.student_name,
                        )
                      }
                      className="text-left font-medium text-blue-700 underline-offset-2 hover:underline"
                    >
                      {student.student_name}
                    </button>
                  </td>
                  <td className="py-3 pr-3">{statusLabel(student.status)}</td>
                  <td className="py-3 pr-3">{student.submitted_count}</td>
                  <td className="py-3 pr-3 whitespace-nowrap">
                    {bestReflection?.grade_total != null ? (
                      <span className="flex items-center gap-1">
                        <span className="font-semibold">
                          {bestReflection.grade_total}/100
                        </span>
                        {bestReflection.accepted && (
                          <span
                            title="Accepted by student"
                            className="text-green-600"
                          >
                            ✓
                          </span>
                        )}
                        {bestReflection.needs_human_review && (
                          <span
                            title="Flagged for review"
                            className="text-amber-600"
                          >
                            ⚑
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-3">
                    {bestAttempt?.ended_at
                      ? new Date(bestAttempt.ended_at).toLocaleString()
                      : ""}
                  </td>
                  <td className="py-3 pr-3">{bestAttempt?.outcome ?? ""}</td>
                  <td className="py-3 pr-3">
                    {bestReflection ? (
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedName(
                            isSelected ? null : student.student_name,
                          )
                        }
                        className="rounded-md border border-gray-300 px-3 py-1 text-xs font-semibold text-gray-700 hover:bg-gray-50"
                      >
                        {isSelected ? "Hide" : "View"}
                      </button>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedStudent && (
        <StudentReflectionDetail
          student={selectedStudent}
          onClose={() => setSelectedName(null)}
        />
      )}
    </section>
  );
}

function StudentReflectionDetail({
  student,
  onClose,
}: {
  student: RollGradebookStudent;
  onClose: () => void;
}) {
  const attempt = student.best_attempt;
  const reflection = attempt?.reflection ?? null;

  return (
    <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50/40 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold">{student.student_name}</h3>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-600">
            {reflection?.grade_total != null && (
              <span className="font-semibold text-gray-800">
                {reflection.grade_total}/100
              </span>
            )}
            {reflection?.difficulty && (
              <span>Graded: {difficultyLabel(reflection.difficulty)}</span>
            )}
            {attempt?.ended_at && (
              <span>Submitted {new Date(attempt.ended_at).toLocaleString()}</span>
            )}
            {attempt?.outcome && <span>Outcome: {attempt.outcome}</span>}
            {reflection?.accepted && (
              <span className="text-green-700">✓ Accepted</span>
            )}
            {reflection?.needs_human_review && (
              <span className="text-amber-700">⚑ Flagged for review</span>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded-md border border-gray-300 bg-white px-3 py-1 text-sm font-semibold text-gray-700 hover:bg-gray-50"
        >
          Close
        </button>
      </div>

      {reflection ? (
        <div className="mt-4 space-y-3">
          {Object.entries(reflection.responses).map(([key, value]) => (
            <div key={key}>
              <p className="text-sm font-semibold text-gray-700">
                {reflectionQuestionLabel(key)}
              </p>
              <p className="mt-0.5 whitespace-pre-wrap text-sm text-gray-800">
                {value}
              </p>
            </div>
          ))}
          {reflection.feedback && (
            <div className="rounded-md border border-gray-200 bg-white p-3">
              <p className="text-sm font-semibold text-gray-700">Coaching</p>
              <p className="mt-0.5 whitespace-pre-wrap text-sm italic text-gray-600">
                {reflection.feedback}
              </p>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm text-gray-500">
          No reflection submitted for this student yet.
        </p>
      )}
    </div>
  );
}
