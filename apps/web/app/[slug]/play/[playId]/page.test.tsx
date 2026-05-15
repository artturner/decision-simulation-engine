import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import PlayPage from "./page";
import type { PlayViewResponse } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Navigation mock
// ---------------------------------------------------------------------------
jest.mock("next/navigation", () => ({
  useParams: () => ({ slug: "test-scenario", playId: "play-123" }),
  useRouter: () => ({ push: jest.fn() }),
}));

// ---------------------------------------------------------------------------
// API client mock
// ---------------------------------------------------------------------------
jest.mock("@/lib/api/client", () => ({
  getPlay: jest.fn(),
  stepPlay: jest.fn(),
  backPlay: jest.fn(),
}));

const mockApi = jest.requireMock("@/lib/api/client") as {
  getPlay: jest.MockedFunction<() => Promise<PlayViewResponse>>;
  stepPlay: jest.MockedFunction<(id: string, body: object) => Promise<PlayViewResponse>>;
  backPlay: jest.MockedFunction<(id: string) => Promise<PlayViewResponse>>;
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const choiceScene = {
  scene_id: "scene-1",
  type: "choice" as const,
  title: "Test Scene",
  narration: "",
  description: "",
  image_url: null,
  choices: [{ text: "Option A" }, { text: "Option B" }],
  outcome: null,
  outcome_message: null,
};

const basePlay: PlayViewResponse = {
  play_id: "play-123",
  scene: choiceScene,
  progress: { step_count: 0, choices_made: [] },
  done: false,
  outcome: null,
  outcome_message: null,
  reflection_required: false,
  reflection_questions: [],
  reflection_prompts: [],
};

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------
function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test("shows loading state while fetching play", () => {
  // getPlay never resolves → component stays in loading
  mockApi.getPlay.mockReturnValue(new Promise(() => {}));
  renderWithClient(<PlayPage />);
  expect(screen.getByText("Loading…")).toBeInTheDocument();
});

test("Go Back is disabled when step_count is 0", async () => {
  mockApi.getPlay.mockResolvedValue(basePlay);
  renderWithClient(<PlayPage />);
  const backButton = await screen.findByText("← Go Back");
  expect(backButton).toBeDisabled();
});

test("clicking a choice button calls stepPlay with the correct choice_index", async () => {
  mockApi.getPlay.mockResolvedValue(basePlay);
  mockApi.stepPlay.mockResolvedValue({
    ...basePlay,
    progress: { step_count: 1, choices_made: ["Option B"] },
  });

  renderWithClient(<PlayPage />);
  fireEvent.click(await screen.findByText("Option B"));

  await waitFor(() =>
    expect(mockApi.stepPlay).toHaveBeenCalledWith("play-123", { choice_index: 1 }),
  );
});

test("cache update after step re-renders the new scene", async () => {
  const nextScene = { ...choiceScene, scene_id: "scene-2", title: "Next Scene" };
  mockApi.getPlay.mockResolvedValue(basePlay);
  mockApi.stepPlay.mockResolvedValue({
    ...basePlay,
    scene: nextScene,
    progress: { step_count: 1, choices_made: ["Option A"] },
  });

  renderWithClient(<PlayPage />);
  fireEvent.click(await screen.findByText("Option A"));

  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Next Scene" })).toBeInTheDocument(),
  );
});
