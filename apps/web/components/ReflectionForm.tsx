"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  ApiClientError,
  acceptReflection,
  gradeReflection,
  submitReflection,
} from "@/lib/api/client";
import type { GradeResult } from "@/lib/api/types";

interface ReflectionFormProps {
  playId: string;
  questions: string[];
  prompts: string[];
  choicesMade: string[];
  initialStudentName?: string | null;
}

type Errors = Record<string, string>;
type Phase = "edit" | "feedback" | "done";

const DIMENSION_LABELS: Record<string, string> = {
  engagement: "Engagement",
  reasoning: "Reasoning",
  insight: "Insight",
};

export default function ReflectionForm({
  playId,
  questions,
  prompts,
  choicesMade,
  initialStudentName,
}: ReflectionFormProps) {
  const [studentName, setStudentName] = useState(initialStudentName ?? "");
  const [responses, setResponses] = useState<Record<string, string>>(() =>
    Object.fromEntries(questions.map((_, i) => [`reflection_${i + 1}`, ""])),
  );
  const [errors, setErrors] = useState<Errors>({});
  const [phase, setPhase] = useState<Phase>("edit");
  const [grade, setGrade] = useState<GradeResult | null>(null);
  // Set when grading is unavailable and we fell back to plain submission.
  const [plainSubmitted, setPlainSubmitted] = useState(false);
  const [isDuplicate, setIsDuplicate] = useState(false);

  // Plain (no-AI) submission fallback.
  const submitMutation = useMutation({
    mutationFn: () =>
      submitReflection(playId, { student_name: studentName, responses }),
    onSuccess: () => {
      setPlainSubmitted(true);
      setPhase("done");
    },
    onError: (error) => {
      if (error instanceof ApiClientError && error.status === 409) {
        setPlainSubmitted(true);
        setIsDuplicate(true);
        setPhase("done");
      }
    },
  });

  const gradeMutation = useMutation({
    mutationFn: () =>
      gradeReflection(playId, { student_name: studentName, responses }),
    onSuccess: (result) => {
      setGrade(result);
      setPhase("feedback");
    },
    onError: (error) => {
      if (error instanceof ApiClientError) {
        // 503: grading not configured — fall back to plain submission.
        if (error.status === 503) {
          submitMutation.mutate();
          return;
        }
        // 409: already accepted and locked.
        if (error.status === 409) {
          setIsDuplicate(true);
          setPhase("done");
          return;
        }
      }
    },
  });

  const acceptMutation = useMutation({
    mutationFn: () => acceptReflection(playId),
    onSuccess: (result) => {
      setGrade(result);
      setPhase("done");
    },
  });

  const validate = (): boolean => {
    const next: Errors = {};
    if (!studentName.trim()) {
      next.student_name = "Name is required.";
    }
    questions.forEach((_, i) => {
      const key = `reflection_${i + 1}`;
      if (!responses[key]?.trim()) {
        next[key] = "This field is required.";
      }
    });
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validate()) {
      gradeMutation.mutate();
    }
  };

  const isWorking =
    gradeMutation.isPending ||
    submitMutation.isPending ||
    acceptMutation.isPending;

  return (
    <div className="mx-auto w-full max-w-2xl">
      {/* ------------------------------------------------------------------ */}
      {/* Journey summary                                                      */}
      {/* ------------------------------------------------------------------ */}
      {choicesMade.length > 0 && (
        <aside className="mb-6 rounded-xl bg-white p-5 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-400">
            Your Journey
          </h2>
          <ol className="mt-3 space-y-1">
            {choicesMade.map((choice, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-gray-700"
              >
                <span className="mt-0.5 shrink-0 text-blue-400">✓</span>
                {choice}
              </li>
            ))}
          </ol>
        </aside>
      )}

      {/* ================================================================== */}
      {/* FEEDBACK / DONE: AI grade + coaching                                */}
      {/* ================================================================== */}
      {(phase === "feedback" || (phase === "done" && grade)) && grade && (
        <GradeCard
          grade={grade}
          final={phase === "done"}
          canRedo={phase === "feedback" && grade.can_redo}
          onRedo={() => setPhase("edit")}
          onAccept={() => acceptMutation.mutate()}
          accepting={acceptMutation.isPending}
        />
      )}

      {/* DONE via plain fallback (no AI grade) */}
      {phase === "done" && !grade && (
        <div
          role="alert"
          className={`rounded-2xl px-6 py-5 text-sm font-medium shadow-sm ${
            isDuplicate
              ? "bg-yellow-50 text-yellow-800"
              : "bg-green-50 text-green-800"
          }`}
        >
          {isDuplicate
            ? "Already submitted — your reflection has been recorded."
            : "Reflection submitted successfully!"}
        </div>
      )}

      {/* ================================================================== */}
      {/* EDIT: the reflection form                                           */}
      {/* ================================================================== */}
      {phase === "edit" && (
        <form
          onSubmit={handleSubmit}
          noValidate
          className="rounded-2xl bg-white p-6 shadow-sm"
        >
          <h2 className="text-lg font-semibold text-gray-900">
            Reflection Questions
          </h2>
          {grade && (
            <p className="mt-1 text-sm text-gray-500">
              Revise your answers below, then submit again for new feedback.
            </p>
          )}

          {/* Student name */}
          <div className="mt-5">
            <label
              htmlFor="student_name"
              className="block text-sm font-medium text-gray-700"
            >
              Your Name
            </label>
            <input
              id="student_name"
              type="text"
              value={studentName}
              onChange={(e) => setStudentName(e.target.value)}
              disabled={isWorking}
              aria-describedby={
                errors.student_name ? "student_name-error" : undefined
              }
              aria-invalid={Boolean(errors.student_name)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
            />
            {errors.student_name && (
              <p
                id="student_name-error"
                role="alert"
                className="mt-1 text-xs text-red-600"
              >
                {errors.student_name}
              </p>
            )}
          </div>

          {/* Reflection questions */}
          {questions.map((question, i) => {
            const key = `reflection_${i + 1}`;
            const errorId = `${key}-error`;
            return (
              <div key={key} className="mt-6">
                <label
                  htmlFor={key}
                  className="block text-sm font-medium text-gray-700"
                >
                  {i + 1}. {question}
                </label>
                {prompts[i] && (
                  <p className="mt-1 text-xs text-gray-500">{prompts[i]}</p>
                )}
                <textarea
                  id={key}
                  rows={3}
                  value={responses[key] ?? ""}
                  onChange={(e) =>
                    setResponses((prev) => ({ ...prev, [key]: e.target.value }))
                  }
                  disabled={isWorking}
                  aria-describedby={errors[key] ? errorId : undefined}
                  aria-invalid={Boolean(errors[key])}
                  className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
                />
                {errors[key] && (
                  <p
                    id={errorId}
                    role="alert"
                    className="mt-1 text-xs text-red-600"
                  >
                    {errors[key]}
                  </p>
                )}
              </div>
            );
          })}

          {/* General error (grading or submission failure) */}
          {(() => {
            const err = gradeMutation.error ?? submitMutation.error;
            const isHandled =
              err instanceof ApiClientError &&
              (err.status === 409 || err.status === 503);
            return err && !isHandled ? (
              <p role="alert" className="mt-4 text-sm text-red-600">
                {(err as Error).message}
              </p>
            ) : null;
          })()}

          <button
            type="submit"
            disabled={isWorking}
            className="mt-6 w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isWorking ? "Checking your reflection…" : "Submit Reflection"}
          </button>
        </form>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Grade + coaching card
// ---------------------------------------------------------------------------

function GradeCard({
  grade,
  final,
  canRedo,
  onRedo,
  onAccept,
  accepting,
}: {
  grade: GradeResult;
  final: boolean;
  canRedo: boolean;
  onRedo: () => void;
  onAccept: () => void;
  accepting: boolean;
}) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-900">
          {final ? "Your Reflection Score" : "Reflection Feedback"}
        </h2>
        <span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-semibold text-blue-700">
          {grade.grade_total} / 100
        </span>
      </div>

      {grade.feedback && (
        <p className="mt-4 rounded-lg bg-blue-50/60 px-4 py-3 text-sm text-gray-800">
          {grade.feedback}
        </p>
      )}

      <ul className="mt-5 space-y-3">
        {Object.entries(grade.dimensions).map(([name, dim]) => (
          <li key={name} className="text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium text-gray-800">
                {DIMENSION_LABELS[name] ?? name}
              </span>
              <span className="text-gray-500">
                {dim.points} / {dim.max_points}
              </span>
            </div>
            {dim.evidence && (
              <p className="mt-0.5 text-xs text-gray-500">{dim.evidence}</p>
            )}
          </li>
        ))}
      </ul>

      {final ? (
        <p className="mt-6 rounded-lg bg-green-50 px-4 py-3 text-sm font-medium text-green-800">
          Your score has been recorded. Thank you for reflecting!
        </p>
      ) : (
        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          {canRedo ? (
            <>
              <button
                type="button"
                onClick={onRedo}
                disabled={accepting}
                className="w-full rounded-lg border border-blue-600 px-6 py-3 text-base font-semibold text-blue-700 transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Revise &amp; resubmit
                <span className="ml-1 text-xs font-normal text-blue-400">
                  ({grade.attempts_remaining} left)
                </span>
              </button>
              <button
                type="button"
                onClick={onAccept}
                disabled={accepting}
                className="w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {accepting ? "Saving…" : "Accept score"}
              </button>
            </>
          ) : (
            <button
              type="button"
              onClick={onAccept}
              disabled={accepting}
              className="w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {accepting ? "Saving…" : "Accept score"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
