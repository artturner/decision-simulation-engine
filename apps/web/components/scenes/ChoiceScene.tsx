"use client";

import type { SceneDTO } from "@/lib/api/types";

const LABELS = ["A", "B", "C", "D", "E", "F"];

interface ChoiceSceneProps {
  scene: SceneDTO;
  onChoose: (index: number) => void;
  isLoading: boolean;
}

export default function ChoiceScene({ scene, onChoose, isLoading }: ChoiceSceneProps) {
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

      <ul className="mt-6 space-y-3" role="list">
        {scene.choices?.map((choice, i) => (
          <li key={i}>
            <button
              onClick={() => onChoose(i)}
              disabled={isLoading}
              aria-label={`${LABELS[i]}. ${choice.text}`}
              className="flex w-full items-start gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-left text-sm font-medium text-gray-800 transition hover:border-blue-400 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="shrink-0 font-bold text-blue-600">
                {LABELS[i]}.
              </span>
              {choice.text}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
