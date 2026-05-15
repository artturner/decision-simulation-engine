"use client";

import type { SceneDTO } from "@/lib/api/types";
import ChoiceScene from "@/components/scenes/ChoiceScene";
import ContinueScene from "@/components/scenes/ContinueScene";
import EndScene from "@/components/scenes/EndScene";

export interface SceneRendererProps {
  scene: SceneDTO;
  onChoose: (choiceIndex: number) => void;
  onContinue: () => void;
  isLoading: boolean;
}

export default function SceneRenderer({
  scene,
  onChoose,
  onContinue,
  isLoading,
}: SceneRendererProps) {
  switch (scene.type) {
    case "choice":
      return (
        <ChoiceScene scene={scene} onChoose={onChoose} isLoading={isLoading} />
      );
    case "auto_advance":
    case "conditional":
      return (
        <ContinueScene
          scene={scene}
          onContinue={onContinue}
          isLoading={isLoading}
        />
      );
    case "end":
      return <EndScene scene={scene} onContinue={onContinue} />;
    default:
      return null;
  }
}
