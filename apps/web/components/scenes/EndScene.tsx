"use client";

import type { SceneDTO } from "@/lib/api/types";

interface EndSceneProps {
  scene: SceneDTO;
  onContinue: () => void;
}

export default function EndScene({ scene, onContinue }: EndSceneProps) {
  const hasOutcome = Boolean(scene.outcome || scene.outcome_message);

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm text-center">
      <h1 className="text-2xl font-bold text-gray-900">{scene.title}</h1>

      {scene.image_url && (
        <img
          src={scene.image_url}
          alt={scene.title}
          className="mt-4 w-full rounded-xl object-cover"
        />
      )}

      {scene.outcome && (
        <p className="mt-3 text-sm font-semibold uppercase tracking-wide text-blue-600">
          {scene.outcome}
        </p>
      )}

      {scene.outcome_message && (
        <p className="mt-4 text-gray-700">{scene.outcome_message}</p>
      )}

      {!hasOutcome && (
        <p className="mt-4 text-gray-600">
          You have completed this scenario.
        </p>
      )}

      <button
        onClick={onContinue}
        className="mt-8 w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700"
      >
        Continue to Reflection
      </button>
    </div>
  );
}
