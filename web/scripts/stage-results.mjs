// Stage published results bundles for a build (T-020-034 contract, RESULTS_DIR).
//
//   RESULTS_DIR=e2e/fixtures/results node scripts/stage-results.mjs
//
// Copies every `*.json` of RESULTS_DIR into `public/results/` as `e2e-<name>.json` (git-ignored), so the production build
// reads them like committed bundles (`src/results/bundles.ts`). Stale `e2e-*.json` files of an earlier staging are removed
// first, with or without the variable, so a release build never ships fixtures. Real bundles are committed under
// `public/results/` by their own names and are never touched here.
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(WEB, "public", "results");

if (existsSync(OUT)) {
  for (const name of readdirSync(OUT)) if (/^e2e-.*\.json$/.test(name)) rmSync(join(OUT, name));
}

const dir = process.env.RESULTS_DIR;
if (dir) {
  const from = resolve(WEB, dir);
  if (!existsSync(from)) {
    console.error(`stage-results: RESULTS_DIR ${from} does not exist`);
    process.exit(1);
  }
  mkdirSync(OUT, { recursive: true });
  const files = readdirSync(from).filter((f) => f.endsWith(".json"));
  for (const f of files) copyFileSync(join(from, f), join(OUT, `e2e-${f}`));
  console.log(`stage-results: staged ${files.length} bundle(s) from ${dir}`);
}
