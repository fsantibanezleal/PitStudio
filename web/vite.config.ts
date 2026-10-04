import { reactRouter } from "@react-router/dev/vite";
import { defineConfig } from "vite";
import { accessDigest, buildInfo } from "./build-info.ts";

export default defineConfig({
  // Must match the router basename (react-router.config.ts); every asset URL derives from it.
  base: process.env.BASE_PATH ?? "/",
  plugins: [reactRouter()],
  resolve: { tsconfigPaths: true },
  define: {
    __BUILD_INFO__: JSON.stringify(buildInfo()),
    // Only the SHA-256 of the demo passphrase reaches the bundle. No ACCESS_PASSPHRASE → the gate is off.
    __ACCESS_DIGEST__: JSON.stringify(accessDigest(process.env.ACCESS_PASSPHRASE)),
  },
});
