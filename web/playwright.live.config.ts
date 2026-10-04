import { defineConfig, devices } from "@playwright/test";

// Smoke test of the deployed site (run by the Pages workflow after deploy). LIVE_URL ends with "/".
const liveUrl = process.env.LIVE_URL ?? "https://fsantibanezleal.github.io/PitStudio/";

export default defineConfig({
  testDir: "e2e/live",
  retries: 2,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",
  use: { baseURL: liveUrl, trace: "retain-on-failure" },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
