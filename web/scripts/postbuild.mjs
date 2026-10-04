// After `react-router build`, shape build/client into the GitHub Pages artifact and enforce the initial-JS budget.
//
// With a basename (BASE_PATH=/<repo>/), React Router 8.4 prerenders routes under build/client/<repo>/ and writes
// the SPA fallback to build/client/index.html. Pages serves the artifact root AT /<repo>/, so the prerendered tree
// moves up one level and the fallback becomes 404.html (unknown URLs hydrate the client router there).
// Without a basename the fallback is build/client/__spa-fallback.html.
import { cpSync, existsSync, readFileSync, renameSync, rmSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const OUT = "build/client";
const BUDGET_GZ = 200 * 1024; // NFR-000-01: ≤ 200 KB gzip for the scripts the start page loads
const base = process.env.BASE_PATH ?? "/";
const nested = join(OUT, base.replace(/^\/|\/$/g, ""));

if (base !== "/" && existsSync(nested)) {
  renameSync(join(OUT, "index.html"), join(OUT, "404.html"));
  cpSync(nested, OUT, { recursive: true });
  rmSync(nested, { recursive: true });
} else if (existsSync(join(OUT, "__spa-fallback.html"))) {
  renameSync(join(OUT, "__spa-fallback.html"), join(OUT, "404.html"));
} else {
  throw new Error("postbuild: no SPA fallback found — did the React Router output layout change?");
}
const index = join(OUT, "index.html");
if (!existsSync(index)) throw new Error("postbuild: the start page was not prerendered");

const html = readFileSync(index, "utf8");
const urls = new Set(
  [...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)].map((m) => m[1]).filter((u) => u.startsWith(base)),
);
let total = 0;
for (const url of urls) total += gzipSync(readFileSync(join(OUT, url.slice(base.length)))).length;

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
console.log(
  `postbuild: Pages layout ready; start page loads ${urls.size} scripts, ${kb(total)} gzip (budget ${kb(BUDGET_GZ)})`,
);
if (total > BUDGET_GZ) {
  console.error("postbuild: initial JS budget exceeded");
  process.exit(1);
}
