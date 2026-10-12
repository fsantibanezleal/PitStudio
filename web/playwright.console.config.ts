import { defineConfig, devices } from "@playwright/test";

// Browser tests of the console UI (web/console/) against a real console on a fixture store: the web server is
// tests/support/console_fixture_server.py (needs `pnpm build:console` first). The public site's tests use playwright.config.ts.
const port = Number(process.env.CONSOLE_E2E_PORT ?? 4180);
const python = process.env.CONSOLE_E2E_PYTHON ?? "uv run --extra api python";

export default defineConfig({
  testDir: "e2e/console",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${port}/ui/`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `${python} ../tests/support/console_fixture_server.py`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 180_000,
    env: { CONSOLE_E2E_PORT: String(port) },
  },
});
