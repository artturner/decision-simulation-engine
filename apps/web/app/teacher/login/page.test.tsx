import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherLoginPage from "./page";
import { getSupabaseClient } from "@/lib/auth/supabase";

const replace = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

jest.mock("@/lib/auth/supabase", () => ({
  getSupabaseClient: jest.fn(),
}));

describe("TeacherLoginPage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders an environment error when Supabase is not configured", async () => {
    (getSupabaseClient as jest.Mock).mockReturnValue(null);
    const user = userEvent.setup();

    render(<TeacherLoginPage />);

    await user.type(screen.getByLabelText("Email"), "teacher@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      screen.getByText("Supabase environment variables are not configured."),
    ).toBeVisible();
  });

  it("signs in with Supabase and redirects to the teacher dashboard", async () => {
    const signInWithPassword = jest.fn().mockResolvedValue({
      data: { session: { access_token: "token" } },
      error: null,
    });
    (getSupabaseClient as jest.Mock).mockReturnValue({
      auth: { signInWithPassword },
    });
    const user = userEvent.setup();

    render(<TeacherLoginPage />);

    await user.type(screen.getByLabelText("Email"), "teacher@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(signInWithPassword).toHaveBeenCalledWith({
      email: "teacher@example.com",
      password: "password123",
    });
    expect(replace).toHaveBeenCalledWith("/teacher");
  });
});
