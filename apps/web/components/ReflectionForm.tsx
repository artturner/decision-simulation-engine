"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiClientError, submitReflection } from "@/lib/api/client";

interface ReflectionFormProps {
  playId: string;
  questions: string[];
  prompts: string[];
  choicesMade: string[];
  initialStudentName?: string | null;
}

type Errors = Record<string, string>;

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
  const [submitted, setSubmitted] = useState(false);
  const [isDuplicate, setIsDuplicate] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      submitReflection(playId, { student_name: studentName, responses }),
    onSuccess: () => {
      setSubmitted(true);
    },
    onError: (error) => {
      if (error instanceof ApiClientError && error.status === 409) {
        setSubmitted(true);
        setIsDuplicate(true);
      }
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
      mutation.mutate();
    }
  };

  const isDisabled = submitted || mutation.isPending;

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

      {/* ------------------------------------------------------------------ */}
      {/* Status banner                                                        */}
      {/* ------------------------------------------------------------------ */}
      {submitted && (
        <div
          role="alert"
          className={`mb-6 rounded-lg px-4 py-3 text-sm font-medium ${
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

      {/* ------------------------------------------------------------------ */}
      {/* Form                                                                 */}
      {/* ------------------------------------------------------------------ */}
      <form
        onSubmit={handleSubmit}
        noValidate
        className="rounded-2xl bg-white p-6 shadow-sm"
      >
        <h2 className="text-lg font-semibold text-gray-900">
          Reflection Questions
        </h2>

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
            disabled={isDisabled}
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
                disabled={isDisabled}
                aria-describedby={errors[key] ? errorId : undefined}
                aria-invalid={Boolean(errors[key])}
                className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
              />
              {errors[key] && (
                <p id={errorId} role="alert" className="mt-1 text-xs text-red-600">
                  {errors[key]}
                </p>
              )}
            </div>
          );
        })}

        {/* General API error (not 409) */}
        {mutation.error &&
          !(
            mutation.error instanceof ApiClientError &&
            mutation.error.status === 409
          ) && (
            <p role="alert" className="mt-4 text-sm text-red-600">
              {(mutation.error as Error).message}
            </p>
          )}

        {/* Submit */}
        <button
          type="submit"
          disabled={isDisabled}
          className="mt-6 w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {mutation.isPending ? "Submitting…" : "Submit Reflection"}
        </button>
      </form>
    </div>
  );
}
