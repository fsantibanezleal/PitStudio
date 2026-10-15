import { fileURLToPath } from "node:url";
import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
import { accessDigest, buildInfo } from "./build-info.ts";

export default defineConfig({
  // Must match the router basename (react-router.config.ts); every asset URL derives from it.
  base: process.env.BASE_PATH ?? "/",
  plugins: [reactRouter()],
  resolve: {
    tsconfigPaths: true,
    // The shared shell's executive view never typesets an equation; keep katex (about 75 KB gzip and its fonts) out of
    // the start page, which is the Introduction (NFR-000-01). See src/introduction/katex-stand-in.ts.
    alias: [
      {
        find: "katex/dist/katex.min.css",
        replacement: fileURLToPath(new URL("./src/introduction/katex-stand-in.css", import.meta.url)),
      },
      {
        find: /^katex$/,
        replacement: fileURLToPath(new URL("./src/introduction/katex-stand-in.ts", import.meta.url)),
      },
    ],
  },
  define: {
    __BUILD_INFO__: JSON.stringify(buildInfo()),
    // Only the SHA-256 of the demo passphrase reaches the bundle. No ACCESS_PASSPHRASE → the gate is off.
    __ACCESS_DIGEST__: JSON.stringify(accessDigest(process.env.ACCESS_PASSPHRASE)),
  },
});
