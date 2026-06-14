"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { getSupabaseClient } from "@/lib/auth/supabase";

export default function TeacherLoginPage() {
  const router = useRouter();
  const supabase = getSupabaseClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"sign-in" | "sign-up">("sign-in");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (!supabase) {
      setError("Supabase environment variables are not configured.");
      return;
    }

    setBusy(true);
    const auth =
      mode === "sign-in"
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password });
    setBusy(false);

    if (auth.error) {
      setError(auth.error.message);
      return;
    }

    if (mode === "sign-up" && !auth.data.session) {
      setMessage("Check your email to confirm your account, then sign in.");
      return;
    }

    router.replace("/teacher");
  }

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-10 text-gray-950">
      <div className="mx-auto w-full max-w-md">
        <header className="mb-6">
          <h1 className="text-3xl font-bold">Teacher sign in</h1>
          <p className="mt-2 text-sm text-gray-600">
            Create classes, assign scenarios, and review student work.
          </p>
        </header>

        <form
          onSubmit={submit}
          className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm"
        >
          <label className="block text-sm font-semibold text-gray-700" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            required
          />

          <label
            className="mt-4 block text-sm font-semibold text-gray-700"
            htmlFor="password"
          >
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            required
          />

          {error && (
            <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </p>
          )}
          {message && (
            <p className="mt-4 rounded-md bg-green-50 px-3 py-2 text-sm text-green-700">
              {message}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-5 w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy
              ? "Working"
              : mode === "sign-in"
                ? "Sign in"
                : "Create account"}
          </button>

          <button
            type="button"
            onClick={() => {
              setMode(mode === "sign-in" ? "sign-up" : "sign-in");
              setError(null);
              setMessage(null);
            }}
            className="mt-3 w-full rounded-md border border-gray-300 px-4 py-2 text-sm font-semibold text-gray-700 transition hover:bg-gray-50"
          >
            {mode === "sign-in"
              ? "Create a teacher account"
              : "I already have an account"}
          </button>
        </form>
      </div>
    </main>
  );
}
