"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { ApiClientError, getPlay } from "@/lib/api/client";
import ReflectionForm from "@/components/ReflectionForm";

export default function CompletePage() {
  const params = useParams();
  const slug = params.slug as string;
  const playId = params.playId as string;
  const router = useRouter();

  const {
    data: play,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["play", playId],
    queryFn: () => getPlay(playId),
    enabled: Boolean(playId),
  });

  // ------------------------------------------------------------------
  // Loading
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">Loading…</p>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Error
  // ------------------------------------------------------------------
  if (error || !play) {
    const is404 = error instanceof ApiClientError && error.status === 404;
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-bold text-gray-800">
          {is404 ? "Session not found" : "Something went wrong"}
        </h1>
        <p className="text-gray-500">
          {(error as Error)?.message ?? "Play session not found."}
        </p>
        <button
          onClick={() => router.push(`/${slug}`)}
          className="mt-2 rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
        >
          Return to start
        </button>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Not yet done — learner arrived here early
  // ------------------------------------------------------------------
  if (!play.done) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-bold text-gray-800">
          Scenario not completed yet
        </h1>
        <p className="text-gray-500">
          Please finish the scenario before submitting your reflection.
        </p>
        <button
          onClick={() => router.push(`/${slug}/play/${playId}`)}
          className="mt-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Return to scenario
        </button>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Done, reflection not required — show simple completion card
  // ------------------------------------------------------------------
  if (!play.reflection_required) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center p-8">
        <div className="w-full max-w-lg rounded-2xl bg-white p-8 shadow-md text-center">
          <h1 className="text-2xl font-bold text-gray-900">
            {play.scene.title}
          </h1>
          {play.outcome && (
            <p className="mt-2 text-sm font-semibold uppercase tracking-wide text-blue-600">
              {play.outcome}
            </p>
          )}
          {play.outcome_message && (
            <p className="mt-4 text-gray-700">{play.outcome_message}</p>
          )}
          <p className="mt-4 text-gray-500">
            You have completed this scenario.
          </p>
          <button
            onClick={() => router.push(`/${slug}`)}
            className="mt-6 w-full rounded-lg bg-gray-100 px-6 py-3 text-sm font-medium text-gray-700 hover:bg-gray-200"
          >
            Back to start
          </button>
        </div>
      </main>
    );
  }

  // ------------------------------------------------------------------
  // Done + reflection required — show form
  // ------------------------------------------------------------------
  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="mx-auto max-w-2xl">
        <header className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Reflection</h1>
          <p className="mt-1 text-sm text-gray-500">
            Take a moment to reflect on what you experienced.
          </p>
        </header>

        <ReflectionForm
          playId={playId}
          questions={play.reflection_questions}
          prompts={play.reflection_prompts}
          choicesMade={play.progress.choices_made}
          initialStudentName={play.learner_label}
        />
      </div>
    </main>
  );
}
