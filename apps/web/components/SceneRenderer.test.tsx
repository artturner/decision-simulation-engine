import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import SceneRenderer from "@/components/SceneRenderer";
import type { SceneDTO } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const base: Omit<SceneDTO, "type" | "choices"> = {
  scene_id: "s1",
  title: "My Scene",
  narration: "Some narration",
  description: "Some description",
  image_url: null,
  outcome: null,
  outcome_message: null,
};

const choiceScene: SceneDTO = {
  ...base,
  type: "choice",
  choices: [{ text: "Alpha" }, { text: "Beta" }, { text: "Gamma" }],
};

const autoScene: SceneDTO = { ...base, type: "auto_advance", choices: null };
const conditionalScene: SceneDTO = { ...base, type: "conditional", choices: null };
const endScene: SceneDTO = {
  ...base,
  type: "end",
  choices: null,
  outcome: "Great job",
  outcome_message: "You made the right calls.",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const noop = () => {};

function renderScene(
  scene: SceneDTO,
  overrides: {
    onChoose?: (i: number) => void;
    onContinue?: () => void;
    isLoading?: boolean;
  } = {},
) {
  return render(
    <SceneRenderer
      scene={scene}
      onChoose={overrides.onChoose ?? noop}
      onContinue={overrides.onContinue ?? noop}
      isLoading={overrides.isLoading ?? false}
    />,
  );
}

// ---------------------------------------------------------------------------
// SceneRenderer — type switching
// ---------------------------------------------------------------------------

describe("SceneRenderer type switching", () => {
  test("renders choice buttons for type=choice", () => {
    renderScene(choiceScene);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
    expect(screen.getByText("Gamma")).toBeInTheDocument();
  });

  test("renders Continue button for type=auto_advance", () => {
    renderScene(autoScene);
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  test("renders Continue button for type=conditional", () => {
    renderScene(conditionalScene);
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  test("renders 'Continue to Reflection' for type=end", () => {
    renderScene(endScene);
    expect(
      screen.getByRole("button", { name: "Continue to Reflection" }),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ChoiceScene
// ---------------------------------------------------------------------------

describe("ChoiceScene", () => {
  test("labels choices A., B., C.", () => {
    renderScene(choiceScene);
    // The button aria-labels include the letter prefix
    expect(screen.getByRole("button", { name: /A\. Alpha/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /B\. Beta/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /C\. Gamma/ })).toBeInTheDocument();
  });

  test("calls onChoose(0) when first choice is clicked", () => {
    const onChoose = jest.fn();
    renderScene(choiceScene, { onChoose });
    fireEvent.click(screen.getByRole("button", { name: /A\. Alpha/ }));
    expect(onChoose).toHaveBeenCalledWith(0);
  });

  test("calls onChoose(1) when second choice is clicked", () => {
    const onChoose = jest.fn();
    renderScene(choiceScene, { onChoose });
    fireEvent.click(screen.getByRole("button", { name: /B\. Beta/ }));
    expect(onChoose).toHaveBeenCalledWith(1);
  });

  test("calls onChoose(2) when third choice is clicked", () => {
    const onChoose = jest.fn();
    renderScene(choiceScene, { onChoose });
    fireEvent.click(screen.getByRole("button", { name: /C\. Gamma/ }));
    expect(onChoose).toHaveBeenCalledWith(2);
  });

  test("disables all choice buttons when isLoading=true", () => {
    renderScene(choiceScene, { isLoading: true });
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  test("enables choice buttons when isLoading=false", () => {
    renderScene(choiceScene, { isLoading: false });
    const buttons = screen.getAllByRole("button");
    buttons.forEach((btn) => expect(btn).not.toBeDisabled());
  });

  test("renders title", () => {
    renderScene(choiceScene);
    expect(screen.getByRole("heading", { name: "My Scene" })).toBeInTheDocument();
  });

  test("renders description and narration", () => {
    renderScene(choiceScene);
    expect(screen.getByText("Some description")).toBeInTheDocument();
    expect(screen.getByText("Some narration")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// ContinueScene
// ---------------------------------------------------------------------------

describe("ContinueScene (auto_advance)", () => {
  test("calls onContinue when Continue is clicked", () => {
    const onContinue = jest.fn();
    renderScene(autoScene, { onContinue });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  test("disables Continue button when isLoading=true", () => {
    renderScene(autoScene, { isLoading: true });
    expect(screen.getByRole("button", { name: /Loading/ })).toBeDisabled();
  });

  test("enables Continue button when isLoading=false", () => {
    renderScene(autoScene, { isLoading: false });
    expect(screen.getByRole("button", { name: "Continue" })).not.toBeDisabled();
  });
});

describe("ContinueScene (conditional)", () => {
  test("calls onContinue when Continue is clicked", () => {
    const onContinue = jest.fn();
    renderScene(conditionalScene, { onContinue });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// EndScene
// ---------------------------------------------------------------------------

describe("EndScene", () => {
  test("renders outcome and outcome_message", () => {
    renderScene(endScene);
    expect(screen.getByText("Great job")).toBeInTheDocument();
    expect(screen.getByText("You made the right calls.")).toBeInTheDocument();
  });

  test("shows generic message when no outcome set", () => {
    const bare: SceneDTO = {
      ...base,
      type: "end",
      choices: null,
      outcome: null,
      outcome_message: null,
    };
    renderScene(bare);
    expect(
      screen.getByText("You have completed this scenario."),
    ).toBeInTheDocument();
  });

  test("calls onContinue when 'Continue to Reflection' is clicked", () => {
    const onContinue = jest.fn();
    renderScene(endScene, { onContinue });
    fireEvent.click(screen.getByRole("button", { name: "Continue to Reflection" }));
    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
