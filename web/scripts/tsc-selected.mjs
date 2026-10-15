// Type-checks the selected tests: the web test files of tasks without a green commit (specs/pending-red.txt) import
// modules that do not exist yet, so they are excluded here exactly as vitest and playwright exclude them.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const list = new URL("../../specs/pending-red.txt", import.meta.url);
const pending = existsSync(list)
  ? readFileSync(list, "utf8")
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.startsWith("web/"))
      .map((l) => l.slice("web/".length))
  : [];
const base = JSON.parse(readFileSync(new URL("../tsconfig.json", import.meta.url), "utf8"));
const config = new URL("../tsconfig.selected.json", import.meta.url);
writeFileSync(
  config,
  `${JSON.stringify({ extends: "./tsconfig.json", exclude: [...base.exclude, ...pending] }, null, 2)}\n`,
);
console.log(`pending-red (tsc): ${pending.length} web test file(s) not type-checked (specs/pending-red.txt)`);
const run = spawnSync(
  process.execPath,
  [
    new URL("../node_modules/typescript/bin/tsc", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
    "-p",
    "tsconfig.selected.json",
  ],
  { stdio: "inherit", cwd: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1") },
);
process.exit(run.status ?? 1);
