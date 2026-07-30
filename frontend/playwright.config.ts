import { defineConfig, devices } from "@playwright/test";

/**
 * Browser tests for the one surface the pytest suite cannot reach: the React
 * editor's own behaviour (dirty tracking, button states, the badge).
 *
 * The specs mock every /api/** call in the browser, so no key, no LLM, and no
 * database are involved - the API's behaviour is already covered by the backend
 * suite. The backend is still used as the static file server, because it is
 * what serves the export in production and needs no extra dependency; it runs
 * on a spare port so it never collides with a container on 8000.
 *
 * Requires the export to exist: run `npm run build` first.
 */
const PORT = 8123;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "line" : [["list"]],
  use: {
    // IPv4 loopback, not localhost: see docs/TEST-PHASE7.md for why.
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run --directory ../backend uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
