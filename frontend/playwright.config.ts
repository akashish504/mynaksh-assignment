import { defineConfig, devices } from "@playwright/test";

// Browser tests for every user path. They drive the real frontend against the
// real local backend (docker-compose.dev.yml), including real model calls.
//
//   docker compose -f docker-compose.dev.yml up -d --build   (from the repo root)
//   npm run test:e2e                                          (from frontend/)
export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  // A chat turn waits for a real model, so tests get a generous limit.
  timeout: 120_000,
  expect: { timeout: 15_000 },
  // Replies come from a real model: one retry absorbs an occasional slow or odd answer.
  retries: 1,
  workers: 3,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Starts the Vite dev server unless one is already running.
  webServer: {
    command: "npm run dev -- --port 5173 --strictPort",
    url: "http://localhost:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
