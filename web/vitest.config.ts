import { defineConfig } from "vitest/config";

// Unit tests run without the React Router plugin; build-time constants get fixed test values.
export default defineConfig({
  resolve: { tsconfigPaths: true },
  define: {
    __BUILD_INFO__: JSON.stringify({ version: "0.00.000", gitSha: "test000", buildDate: "2026-01-01" }),
    __ACCESS_DIGEST__: JSON.stringify(""),
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    restoreMocks: true,
  },
});
