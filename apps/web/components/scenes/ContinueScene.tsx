"use client";

import type { SceneDTO } from "@/lib/api/types";

interface ContinueSceneProps {
  scene: SceneDTO;
  onContinue: () => void;
  isLoading: boolean;
}

export default function ContinueScene({
  scene,
  onContinue,
  isLoading,
}: ContinueSceneProps) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm">
      <h1 className="text-xl font-bold text-gray-900">{scene.title}</h1>

      {scene.image_url && (
        <img
          src={scene.image_url}
          alt={scene.title}
          className="mt-4 w-full rounded-xl object-cover"
        />
      )}

      {scene.description && (
        <p className="mt-4 text-gray-700">{scene.description}</p>
      )}

      {scene.narration && (
        <p className="mt-3 italic text-gray-500">{scene.narration}</p>
      )}

      <button
        onClick={onContinue}
        disabled={isLoading}
        className="mt-6 w-full rounded-lg bg-blue-600 px-6 py-3 text-base font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? "Loading…" : "Continue"}
      </button>
    </div>
  );
}
