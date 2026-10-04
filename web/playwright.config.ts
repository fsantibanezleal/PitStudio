import { defineConfig, devices } from "@playwright/test";

// E2E against the production build served like GitHub Pages (scripts/serve-static.mjs) under BASE_PATH.
// Build first with the same env: `BASE_PATH=/PitStudio/ ACCESS_PASSPHRASE=<phrase> pnpm build`.
const base = process.env.BASE_PATH ?? "/";
const port = Number(process.env.PORT ?? 4173);

export default defineConfig({
  testDir: "e2e",
  testIgnore: "live/**",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${port}${base}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "node scripts/serve-static.mjs",
    url: `http://localhost:${port}${base}`,
    reuseExistingServer: !process.env.CI,
    env: { BASE_PATH: base, PORT: String(port) },
  },
});
