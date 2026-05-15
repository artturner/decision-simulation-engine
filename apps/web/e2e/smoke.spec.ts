/**
 * Smoke tests — full-stack E2E against the running Docker Compose stack.
 *
 * Prerequisites
 * -------------
 *   cd infra && docker compose up          # start all services
 *   cd apps/web && npx playwright test     # run these tests
 *
 * Environment variables (all optional)
 * -------------------------------------
 *   BASE_URL      – frontend base URL  (default: http://localhost:3000)
 *   API_BASE_URL  – backend base URL   (default: http://localhost:8000)
 *   ADMIN_API_KEY – admin secret       (default: changeme)
 *
 * Seeding strategy
 * ----------------
 * beforeAll POSTs the test scenario to the admin API with status "published".
 * On 409 (slug already taken from a prior run) the test continues — the
 * existing published scenario is used.  No cleanup is needed between runs.
 */

import { test, expect } from "@playwright/test";
import scenarioJson from "./fixtures/test-scenario.json";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SLUG = "e2e-test-scenario";
const API_BASE = process.env.API_BASE_URL ?? "http://localhost:8000";
const ADMIN_KEY = process.env.ADMIN_API_KEY ?? "changeme";

// ---------------------------------------------------------------------------
// Seed the test scenario once per test run
// ---------------------------------------------------------------------------

test.beforeAll(async ({ request }) => {
  const res = await request.post(
    `${API_BASE}/api/v1/admin/scenarios/import`,
    {
      headers: {
        "X-Admin-Key": ADMIN_KEY,
        "Content-Type": "application/json",
      },
      data: {
        slug: SLUG,
        title: "E2E Test Scenario",
        description: "Automated testing scenario — do not delete.",
        status: "published",
        scenario_json: scenarioJson,
      },
    },
  );

  // 201 = freshly imported; 409 = already seeded from a previous run → both fine
  if (!res.ok() && res.status() !== 409) {
    throw new Error(
      `Failed to seed test scenario: HTTP ${res.status()} — ${await res.text()}`,
    );
  }
});

// ---------------------------------------------------------------------------
// Test 1: Critical path  start → choice → auto_advance → end → reflection
// ---------------------------------------------------------------------------

test("critical path: start → high road → middle → end → reflection → success", async ({
  page,
}) => {
  // ── Scenario landing page ────────────────────────────────────────────────
  await page.goto(`/${SLUG}`);

  await expect(
    page.getByRole("heading", { name: "E2E Test Scenario" }),
  ).toBeVisible();
  await expect(
    page.getByText("Automated testing scenario"),
  ).toBeVisible();

  // ── Start the scenario ───────────────────────────────────────────────────
  await page.getByRole("button", { name: "Start Scenario" }).click();
  await page.waitForURL(/\/play\//);

  // ── Choice scene — "The Starting Point" ──────────────────────────────────
  await expect(
    page.getByRole("heading", { name: "The Starting Point" }),
  ).toBeVisible();

  // Both choices are rendered with letter prefixes
  await expect(
    page.getByRole("button", { name: /A\. Take the high road/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /B\. Take the low road/ }),
  ).toBeVisible();

  // Go Back is disabled at step 0
  await expect(
    page.getByRole("button", { name: "← Go Back" }),
  ).toBeDisabled();

  // ── Choose "Take the high road" → auto_advance scene ─────────────────────
  await page.getByRole("button", { name: /A\. Take the high road/ }).click();

  await expect(
    page.getByRole("heading", { name: "The Middle Path" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue" }),
  ).toBeVisible();

  // Go Back is now enabled
  await expect(
    page.getByRole("button", { name: "← Go Back" }),
  ).toBeEnabled();

  // ── Continue → end scene ─────────────────────────────────────────────────
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(
    page.getByRole("heading", { name: "Journey Complete" }),
  ).toBeVisible();
  await expect(page.getByText("Success")).toBeVisible();
  await expect(
    page.getByText("You have completed your journey."),
  ).toBeVisible();

  // ── Navigate to reflection ────────────────────────────────────────────────
  await page
    .getByRole("button", { name: "Continue to Reflection" })
    .click();
  await page.waitForURL(/\/complete\//);

  // ── Reflection page ───────────────────────────────────────────────────────
  await expect(
    page.getByRole("heading", { name: "Reflection" }),
  ).toBeVisible();

  // Journey summary shows the choice made
  await expect(page.getByText("Take the high road")).toBeVisible();

  // Form fields are present
  const nameField = page.getByLabel("Your Name");
  const reflectionField = page.getByLabel(/1\. What did you learn/);
  await expect(nameField).toBeVisible();
  await expect(reflectionField).toBeVisible();

  // ── Fill and submit ───────────────────────────────────────────────────────
  await nameField.fill("Doe, Jane");
  await reflectionField.fill("I learned to choose my path carefully.");

  await page.getByRole("button", { name: "Submit Reflection" }).click();

  // ── Success ───────────────────────────────────────────────────────────────
  await expect(
    page.getByText("Reflection submitted successfully!"),
  ).toBeVisible();

  // Form is disabled after successful submission
  await expect(
    page.getByRole("button", { name: "Submit Reflection" }),
  ).toBeDisabled();
  await expect(nameField).toBeDisabled();
  await expect(reflectionField).toBeDisabled();
});

// ---------------------------------------------------------------------------
// Test 2: Go Back navigation
// ---------------------------------------------------------------------------

test("Go Back: returns to previous scene and resets its state", async ({
  page,
}) => {
  // Fresh play session
  await page.goto(`/${SLUG}`);
  await page.getByRole("button", { name: "Start Scenario" }).click();
  await page.waitForURL(/\/play\//);

  // At the start — Go Back is disabled
  await expect(
    page.getByRole("heading", { name: "The Starting Point" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "← Go Back" }),
  ).toBeDisabled();

  // Make a choice
  await page.getByRole("button", { name: /A\. Take the high road/ }).click();
  await expect(
    page.getByRole("heading", { name: "The Middle Path" }),
  ).toBeVisible();

  // Go Back becomes enabled after the first step
  const backBtn = page.getByRole("button", { name: "← Go Back" });
  await expect(backBtn).toBeEnabled();

  // Click Go Back
  await backBtn.click();

  // Returned to the choice scene — Go Back is disabled again
  await expect(
    page.getByRole("heading", { name: "The Starting Point" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "← Go Back" }),
  ).toBeDisabled();

  // Can still make a different choice
  await expect(
    page.getByRole("button", { name: /B\. Take the low road/ }),
  ).toBeEnabled();
});

// ---------------------------------------------------------------------------
// Test 3: Reflection validation — missing fields block submission
// ---------------------------------------------------------------------------

test("reflection validation: empty fields block submission", async ({
  page,
}) => {
  // Reach end via the short path (low road → directly to end)
  await page.goto(`/${SLUG}`);
  await page.getByRole("button", { name: "Start Scenario" }).click();
  await page.waitForURL(/\/play\//);

  await page.getByRole("button", { name: /B\. Take the low road/ }).click();
  await page
    .getByRole("button", { name: "Continue to Reflection" })
    .click();
  await page.waitForURL(/\/complete\//);

  await expect(
    page.getByRole("heading", { name: "Reflection" }),
  ).toBeVisible();

  // Submit without filling anything
  await page.getByRole("button", { name: "Submit Reflection" }).click();

  // Both required-field errors appear
  await expect(page.getByText("Name is required.")).toBeVisible();
  await expect(page.getByText("This field is required.")).toBeVisible();

  // API was NOT called — form is still enabled
  await expect(
    page.getByRole("button", { name: "Submit Reflection" }),
  ).toBeEnabled();
});
