// Generate TypeScript types from contracts/<stem>.schema.json into src/contracts/generated/<stem>.ts (data-model 7.2).
//
// Usage: node scripts/gen-types.mjs [stem ...]      (default: every promoted schema)
// A schema that refers to another contract (`manifest.schema.json#/$defs/...`) is compiled in a scratch folder that holds
// every schema of contracts/ and of the spec drafts, so references resolve whether or not the other contract is promoted yet.
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { compile } from "json-schema-to-typescript";

const root = resolve(import.meta.dirname, "..", "..");
const out = resolve(import.meta.dirname, "..", "src", "contracts", "generated");
const sources = [
  join(root, "contracts"),
  ...["001-contracts", "002-runner", "003-console"].map((s) => join(root, "specs", s, "contracts")),
];

const scratch = mkdtempSync(join(tmpdir(), "pst-gen-"));
try {
  for (const dir of sources.toReversed()) {
    if (!existsSync(dir)) continue;
    for (const f of readdirSync(dir).filter((n) => n.endsWith(".schema.json")))
      cpSync(join(dir, f), join(scratch, f));
  }
  const available = readdirSync(join(root, "contracts"))
    .filter((n) => n.endsWith(".schema.json"))
    .map((n) => n.replace(/\.schema\.json$/, ""));
  const stems = process.argv.length > 2 ? process.argv.slice(2) : available;
  mkdirSync(out, { recursive: true });
  for (const stem of stems) {
    const file = `${stem}.schema.json`;
    const schema = JSON.parse((await import("node:fs")).readFileSync(join(scratch, file), "utf8"));
    const ts = await compile(schema, stem, {
      bannerComment: `/* Generated from contracts/${file} by web/scripts/gen-types.mjs. Do not edit. */`,
      additionalProperties: false,
      strictIndexSignatures: true,
      unreachableDefinitions: true,
      declareExternallyReferenced: true,
      format: false,
      cwd: scratch,
    });
    writeFileSync(join(out, `${stem}.ts`), ts, "utf8");
    console.log(`wrote src/contracts/generated/${stem}.ts`);
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
