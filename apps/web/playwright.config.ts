import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright configuration for smoke-testing the full stack.
 *
 * Requires a running stack: cd infra && docker compose up
 *
 * Override URLs via environment variables:
 *   BASE_URL          – frontend   (default: http://localhost:3000)
 *   API_BASE_URL      – backend    (default: http://localhost:8000)
 *   ADMIN_API_KEY     – admin key  (default: changeme)
 */
export default defineConfig({
  testDir: "./e2e",

  // Run tests serially — they share DB state via the seeded scenario
  fullyParallel: false,
  workers: 1,

  // One retry in CI to handle transient startup delays
  retries: process.env.CI ? 1 : 0,

  reporter: [["list"], ["html", { open: "never" }]],

  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    // Capture trace + screenshot on test failure for easy debugging
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
