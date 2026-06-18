import { downloadRollGradebookCsv } from "./teacher";

describe("teacher API client", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it("downloads roll gradebook CSV with the teacher bearer token", async () => {
    const blob = new Blob(["student_name,status\nAlice,completed\n"], {
      type: "text/csv",
    });
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(blob),
    });

    const result = await downloadRollGradebookCsv(
      "token-123",
      "roll-1",
      "scenario-1",
    );

    expect(global.fetch).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/teacher/rolls/roll-1/scenarios/scenario-1/gradebook.csv",
      {
        headers: {
          Authorization: "Bearer token-123",
        },
      },
    );
    expect(result).toBe(blob);
  });
});
