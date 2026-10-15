import { resolve } from "node:path";
import { defineConfig } from "vite";

// The console UI: a separate entry (web/console/), served by the console at /ui/ from web/build/console/. It is never part of
// the Pages artifact (web/build/client/); tools/check_pages_artifact.py enforces that. `pnpm build:console` builds it.
export default defineConfig({
  root: resolve(import.meta.dirname, "console"),
  base: "/ui/",
  publicDir: resolve(import.meta.dirname, "console", "public"),
  resolve: { tsconfigPaths: true },
  build: {
    outDir: resolve(import.meta.dirname, "build", "console"),
    emptyOutDir: true,
    assetsInlineLimit: 0, // the console's CSP (default-src 'self') forbids data: URIs
  },
});
