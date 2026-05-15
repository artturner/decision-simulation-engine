"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { backPlay, getPlay, stepPlay } from "@/lib/api/client";
import type { PlayViewResponse } from "@/lib/api/types";
import SceneRenderer from "@/components/SceneRenderer";

export default function PlayPage() {
  const params = useParams();
  const slug = params.slug as string;
  const playId = params.playId as string;
  const router = useRouter();
  const queryClient = useQueryClient();

  // ------------------------------------------------------------------
  // Load play state — backend is the single source of truth
  // ------------------------------------------------------------------
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
  // Step mutation — merge response into cache so UI updates instantly
  // ------------------------------------------------------------------
  const stepMutation = useMutation({
    mutationFn: (choiceIndex?: number) =>
      stepPlay(playId, choiceIndex !== undefined ? { choice_index: choiceIndex } : {}),
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["play", playId],
        (old: PlayViewResponse | undefined) => ({ ...old, ...data }),
      );
    },
  });

  // ------------------------------------------------------------------
  // Back mutation — merge response into cache
  // ------------------------------------------------------------------
  const backMutation = useMutation({
    mutationFn: () => backPlay(playId),
    onSuccess: (data) => {
      queryClient.setQueryData(
        ["play", playId],
        (old: PlayViewResponse | undefined) => ({ ...old, ...data }),
      );
    },
  });

  const isMutating = stepMutation.isPending || backMutation.isPending;

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
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-bold text-gray-800">Something went wrong</h1>
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

  const { scene, progress } = play;

  // ------------------------------------------------------------------
  // Continue handler — steps forward or navigates to reflection on end
  // ------------------------------------------------------------------
  const handleContinue = () => {
    if (scene.type === "end") {
      router.push(`/${slug}/complete/${playId}`);
    } else {
      stepMutation.mutate(undefined);
    }
  };

  // ------------------------------------------------------------------
  // Active play
  // ------------------------------------------------------------------
  return (
    <main className="min-h-screen bg-gray-50 p-4 md:p-8">
      <div className="mx-auto max-w-2xl">

        {/* Mutation error banner */}
        {(stepMutation.error || backMutation.error) && (
          <div className="mb-4 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {((stepMutation.error ?? backMutation.error) as Error).message}
          </div>
        )}

        {/* Scene */}
        <SceneRenderer
          scene={scene}
          isLoading={isMutating}
          onChoose={(i) => stepMutation.mutate(i)}
          onContinue={handleContinue}
        />

        {/* Your Journey */}
        {progress.choices_made.length > 0 && (
          <aside className="mt-6 rounded-xl bg-white p-5 shadow-sm">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-gray-400">
              Your Journey
            </h2>
            <ol className="mt-3 space-y-1">
              {progress.choices_made.map((choice, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <span className="mt-0.5 shrink-0 text-blue-400">✓</span>
                  {choice}
                </li>
              ))}
            </ol>
          </aside>
        )}

        {/* Navigation */}
        <nav className="mt-6 flex gap-3">
          <button
            onClick={() => backMutation.mutate()}
            disabled={progress.step_count === 0 || backMutation.isPending}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            ← Go Back
          </button>

          <button
            onClick={() => router.push(`/${slug}`)}
            className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm font-medium text-gray-500 transition hover:bg-gray-50"
          >
            Restart
          </button>
        </nav>

      </div>
    </main>
  );
}
