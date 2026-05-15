"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { ApiClientError, getScenario, startPlay } from "@/lib/api/client";

export default function ScenarioPage() {
  const params = useParams();
  const slug = params.slug as string;
  const router = useRouter();

  // ------------------------------------------------------------------
  // Fetch scenario metadata
  // ------------------------------------------------------------------
  const {
    data: scenario,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["scenario", slug],
    queryFn: () => getScenario(slug),
    enabled: Boolean(slug),
  });

  // ------------------------------------------------------------------
  // Start play mutation
  // ------------------------------------------------------------------
  const startMutation = useMutation({
    mutationFn: () =>
      startPlay({ scenario_version_id: scenario!.scenario_version_id }),
    onSuccess: (data) => {
      router.push(`/${slug}/play/${data.play_id}`);
    },
  });

  // ------------------------------------------------------------------
  // Render states
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-gray-500">Loading scenario…</p>
      </main>
    );
  }

  if (error) {
    const is404 =
      error instanceof ApiClientError && error.status === 404;

    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <h1 className="text-2xl font-bold text-gray-800">
          {is404 ? "Scenario not found" : "Something went wrong"}
        </h1>
        <p className="text-gray-500">
          {is404
            ? `No published scenario found for "${slug}".`
            : (error as Error).message}
        </p>
      </main>
    );
  }

  if (!scenario) return null;

  const { metadata } = scenario;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="w-full max-w-lg rounded-2xl bg-white p-8 shadow-md">
        {/* Cover image */}
        {metadata.cover_image_url && (
          <img
            src={metadata.cover_image_url}
            alt={metadata.title || slug}
            className="mb-6 w-full rounded-xl object-cover"
          />
        )}

        {/* Page icon */}
        {metadata.page_icon && (
          <div className="mb-4 text-5xl" aria-hidden="true">
            {metadata.page_icon}
          </div>
        )}

        {/* Title */}
        <h1 className="text-2xl font-bold text-gray-900">
          {metadata.title || slug}
        </h1>

        {/* Description */}
        {metadata.description && (
          <p className="mt-3 text-gray-600">{metadata.description}</p>
        )}

        {/* Author / version meta */}
        {(metadata.author || metadata.version) && (
          <p className="mt-2 text-sm text-gray-400">
            {[metadata.author, metadata.version && `v${metadata.version}`]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}

        {/* Error from start mutation */}
        {startMutation.error && (
          <p className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
            {(startMutation.error as Error).message}
          </p>
        )}

        {/* Start button */}
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="mt-6 w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {startMutation.isPending ? "Starting…" : "Start Scenario"}
        </button>
      </div>
    </main>
  );
}
