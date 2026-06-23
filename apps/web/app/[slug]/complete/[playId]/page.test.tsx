import React from "react";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CompletePage from "./page";
import type { GradeResult, PlayViewResponse } from "@/lib/api/types";

// ---------------------------------------------------------------------------
// Navigation mock
// ---------------------------------------------------------------------------
const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useParams: () => ({ slug: "test-scenario", playId: "play-abc" }),
  useRouter: () => ({ push: mockPush }),
}));

// ---------------------------------------------------------------------------
// API client mock — spread actual so ApiClientError class is preserved
// ---------------------------------------------------------------------------
jest.mock("@/lib/api/client", () => ({
  ...jest.requireActual("@/lib/api/client"),
  getPlay: jest.fn(),
  submitReflection: jest.fn(),
  gradeReflection: jest.fn(),
  acceptReflection: jest.fn(),
}));

const mockApi = jest.requireMock("@/lib/api/client") as {
  getPlay: jest.MockedFunction<() => Promise<PlayViewResponse>>;
  submitReflection: jest.MockedFunction<
    (id: string, body: object) => Promise<{ ok: true }>
  >;
  gradeReflection: jest.MockedFunction<
    (id: string, body: object) => Promise<GradeResult>
  >;
  acceptReflection: jest.MockedFunction<(id: string) => Promise<GradeResult>>;
};

const gradeResult: GradeResult = {
  grade_total: 85,
  completion_points: 20,
  dimensions: {
    engagement: { level: "full", points: 25, max_points: 25, evidence: "e" },
    reasoning: { level: "solid", points: 24, max_points: 30, evidence: "r" },
    insight: { level: "minimal", points: 16, max_points: 25, evidence: "i" },
  },
  feedback: "Solid reflection — try citing a specific moment.",
  needs_human_review: false,
  low_effort_flags: [],
  accepted: false,
  attempts_used: 1,
  attempts_remaining: 2,
  can_redo: true,
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------
const endScene = {
  scene_id: "end-1",
  type: "end" as const,
  title: "The End",
  narration: "",
  description: "",
  image_url: null,
  choices: null,
  outcome: "Good outcome",
  outcome_message: "Well done.",
};

const baseProgress = {
  step_count: 3,
  choices_made: ["Chose empathy", "Chose transparency"],
};

const completedPlay: PlayViewResponse = {
  play_id: "play-abc",
  learner_label: null,
  scene: endScene,
  progress: baseProgress,
  done: true,
  outcome: "Good outcome",
  outcome_message: "Well done.",
  reflection_required: true,
  reflection_questions: ["What did you learn?", "What would you do differently?"],
  reflection_prompts: [
    "Think about the key moments.",
    "Consider alternative approaches.",
  ],
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
  mockPush.mockReset();
});

// ---------------------------------------------------------------------------
// 1. Play not done — reflection form must NOT render
// ---------------------------------------------------------------------------
describe("when play is not done", () => {
  const inProgressPlay: PlayViewResponse = {
    ...completedPlay,
    done: false,
    reflection_required: true,
  };

  test("shows 'Scenario not completed yet' message", async () => {
    mockApi.getPlay.mockResolvedValue(inProgressPlay);
    renderWithClient(<CompletePage />);
    expect(
      await screen.findByText("Scenario not completed yet"),
    ).toBeInTheDocument();
  });

  test("does not render the reflection form", async () => {
    mockApi.getPlay.mockResolvedValue(inProgressPlay);
    renderWithClient(<CompletePage />);
    await screen.findByText("Scenario not completed yet");
    expect(
      screen.queryByRole("button", { name: /Submit Reflection/i }),
    ).not.toBeInTheDocument();
  });

  test("shows link back to play page", async () => {
    mockApi.getPlay.mockResolvedValue(inProgressPlay);
    renderWithClient(<CompletePage />);
    const btn = await screen.findByRole("button", { name: "Return to scenario" });
    fireEvent.click(btn);
    expect(mockPush).toHaveBeenCalledWith(
      "/test-scenario/play/play-abc",
    );
  });
});

// ---------------------------------------------------------------------------
// 2. AI grade → coach → accept flow
// ---------------------------------------------------------------------------
describe("AI grading flow", () => {
  beforeEach(() => {
    mockApi.getPlay.mockResolvedValue(completedPlay);
    mockApi.gradeReflection.mockResolvedValue(gradeResult);
    mockApi.acceptReflection.mockResolvedValue({
      ...gradeResult,
      accepted: true,
      can_redo: false,
    });
  });

  async function fillAndSubmit() {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.change(screen.getByLabelText("Your Name"), {
      target: { value: "Doe, Jane" },
    });
    fireEvent.change(screen.getByLabelText(/1\. What did you learn/), {
      target: { value: "I learned empathy." },
    });
    fireEvent.change(screen.getByLabelText(/2\. What would you do differently/), {
      target: { value: "I would listen more." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
  }

  test("calls gradeReflection with correct payload", async () => {
    await fillAndSubmit();
    await waitFor(() => expect(mockApi.gradeReflection).toHaveBeenCalledTimes(1));
    expect(mockApi.gradeReflection).toHaveBeenCalledWith("play-abc", {
      student_name: "Doe, Jane",
      responses: {
        reflection_1: "I learned empathy.",
        reflection_2: "I would listen more.",
      },
    });
  });

  test("shows score and coaching feedback after grading", async () => {
    await fillAndSubmit();
    expect(await screen.findByText("85 / 100")).toBeInTheDocument();
    expect(
      screen.getByText(/Solid reflection — try citing a specific moment/i),
    ).toBeInTheDocument();
  });

  test("revise returns to the form for a re-grade", async () => {
    await fillAndSubmit();
    await screen.findByText("85 / 100");
    fireEvent.click(screen.getByRole("button", { name: /Revise & resubmit/i }));
    // Form is back; answers retained
    expect(await screen.findByLabelText("Your Name")).toHaveValue("Doe, Jane");
  });

  test("accept locks in the score", async () => {
    await fillAndSubmit();
    await screen.findByText("85 / 100");
    fireEvent.click(screen.getByRole("button", { name: "Accept score" }));
    await waitFor(() => expect(mockApi.acceptReflection).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText(/Your score has been recorded/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 3. Fallback when AI grading is unavailable (503)
// ---------------------------------------------------------------------------
describe("grading unavailable fallback", () => {
  beforeEach(() => {
    mockApi.getPlay.mockResolvedValue(completedPlay);
    const { ApiClientError } = jest.requireMock("@/lib/api/client") as {
      ApiClientError: new (status: number, message: string) => Error & {
        status: number;
      };
    };
    mockApi.gradeReflection.mockRejectedValue(
      new ApiClientError(503, "AI grading is not available."),
    );
    mockApi.submitReflection.mockResolvedValue({ ok: true });
  });

  async function fillAndSubmit() {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.change(screen.getByLabelText("Your Name"), {
      target: { value: "Doe, Jane" },
    });
    fireEvent.change(screen.getByLabelText(/1\. What did you learn/), {
      target: { value: "I learned empathy." },
    });
    fireEvent.change(screen.getByLabelText(/2\. What would you do differently/), {
      target: { value: "I would listen more." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
  }

  test("falls back to plain submission and shows success", async () => {
    await fillAndSubmit();
    await waitFor(() => expect(mockApi.submitReflection).toHaveBeenCalledTimes(1));
    expect(
      await screen.findByText(/Reflection submitted successfully/i),
    ).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 4. 409 — reflection already accepted (locked)
// ---------------------------------------------------------------------------
describe("409 locked reflection", () => {
  beforeEach(() => {
    mockApi.getPlay.mockResolvedValue(completedPlay);
    const { ApiClientError } = jest.requireMock("@/lib/api/client") as {
      ApiClientError: new (status: number, message: string) => Error & {
        status: number;
      };
    };
    mockApi.gradeReflection.mockRejectedValue(
      new ApiClientError(409, "This reflection has already been accepted."),
    );
  });

  async function fillAndSubmit() {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.change(screen.getByLabelText("Your Name"), {
      target: { value: "Doe, Jane" },
    });
    fireEvent.change(screen.getByLabelText(/1\. What did you learn/), {
      target: { value: "Learned a lot." },
    });
    fireEvent.change(screen.getByLabelText(/2\. What would you do differently/), {
      target: { value: "More patience." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
  }

  test("shows 'Already submitted' message", async () => {
    await fillAndSubmit();
    expect(await screen.findByText(/Already submitted/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 4. Validation — missing fields
// ---------------------------------------------------------------------------
describe("validation errors", () => {
  beforeEach(() => {
    mockApi.getPlay.mockResolvedValue(completedPlay);
  });

  test("shows error when student_name is empty and submit attempted", async () => {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
    expect(await screen.findByText("Name is required.")).toBeInTheDocument();
  });

  test("shows error for each empty reflection field", async () => {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
    const errors = await screen.findAllByText("This field is required.");
    expect(errors).toHaveLength(2);
  });

  test("does NOT call gradeReflection when validation fails", async () => {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
    await screen.findByText("Name is required.");
    expect(mockApi.gradeReflection).not.toHaveBeenCalled();
    expect(mockApi.submitReflection).not.toHaveBeenCalled();
  });

  test("clears errors when fields are filled and re-submitted", async () => {
    renderWithClient(<CompletePage />);
    await screen.findByLabelText("Your Name");
    // Trigger errors
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
    await screen.findByText("Name is required.");
    // Fill required fields
    fireEvent.change(screen.getByLabelText("Your Name"), {
      target: { value: "Doe, Jane" },
    });
    fireEvent.change(screen.getByLabelText(/1\. What did you learn/), {
      target: { value: "Something." },
    });
    fireEvent.change(screen.getByLabelText(/2\. What would you do differently/), {
      target: { value: "More." },
    });
    mockApi.gradeReflection.mockResolvedValue(gradeResult);
    fireEvent.click(screen.getByRole("button", { name: "Submit Reflection" }));
    await screen.findByText("85 / 100");
    expect(screen.queryByText("Name is required.")).not.toBeInTheDocument();
  });
});
