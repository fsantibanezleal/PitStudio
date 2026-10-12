// Generate one type-only TypeScript module per contract schema, or check that the committed ones are current.
//
//   node scripts/gen-types.mjs [--check] [--contracts DIR] [--out DIR]      (pnpm gen:types [--check])
//
// Defaults: `contracts/` of the repository and `web/src/contracts/generated/`. Writes `<stem>.ts` per
// `<stem>.schema.json` plus `index.ts` with `export type { ... }` only (no runtime statement, NFR-001-02), with
// json-schema-to-typescript and the pinned options of data-model 7.2. Everything is generated in memory first: a failed
// run changes no file. Exit: 0 ok (or no drift), 1 drift (--check), 2 usage error, 3 a schema cannot be generated.
//
// The invalid-schema check here is structural (keyword value types); the complete 2020-12 meta-schema check is the
// job of tools/gen_types.py, which runs first in CI.

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const WEB = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const REPO = resolve(WEB, "..");
const DEFAULT_CONTRACTS = join(REPO, "contracts");
const DEFAULT_OUT = join(WEB, "src", "contracts", "generated");
const SCHEMA_SUFFIX = ".schema.json";

const UNSUPPORTED = ["prefixItems", "$dynamicRef", "$dynamicAnchor", "$recursiveRef"];
const TYPES = new Set(["string", "number", "integer", "boolean", "object", "array", "null"]);
const NUMBER_KEYWORDS = [
  "minimum",
  "maximum",
  "exclusiveMinimum",
  "exclusiveMaximum",
  "multipleOf",
  "minLength",
  "maxLength",
  "minItems",
  "maxItems",
  "minProperties",
  "maxProperties",
];
const STRING_KEYWORDS = ["pattern", "title", "description", "$id", "$schema", "$ref", "$comment", "format"];
const SUBSCHEMA = [
  "items",
  "additionalProperties",
  "unevaluatedProperties",
  "unevaluatedItems",
  "propertyNames",
  "contains",
  "not",
  "if",
  "then",
  "else",
];
const SCHEMA_LIST = ["allOf", "anyOf", "oneOf", "prefixItems"];
const SCHEMA_MAP = ["properties", "patternProperties", "$defs", "definitions", "dependentSchemas"];

class GenerationError extends Error {}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Structural vet of one schema node; throws a message naming the pointer of the first defect. */
function vetNode(node, pointer, ownBase) {
  if (typeof node === "boolean") return;
  if (!isObject(node)) throw new Error(`${pointer || "/"}: a schema must be an object or a boolean`);
  for (const key of UNSUPPORTED) {
    if (key in node) throw new Error(`unsupported construct ${key} at ${pointer || "/"}`);
  }
  if (typeof node.$ref === "string" && node.$ref.includes("://") && !node.$ref.startsWith(ownBase)) {
    throw new Error(`remote $ref ${node.$ref.slice(0, 80)} at ${pointer || "/"}`);
  }
  if ("type" in node) {
    const kinds = Array.isArray(node.type) ? node.type : [node.type];
    if (kinds.length === 0 || kinds.some((kind) => !TYPES.has(kind))) {
      throw new Error(`not a valid 2020-12 schema: bad type at ${pointer || "/"}`);
    }
  }
  for (const key of NUMBER_KEYWORDS) {
    if (key in node && (typeof node[key] !== "number" || Number.isNaN(node[key]))) {
      throw new Error(`not a valid 2020-12 schema: ${key} is not a number at ${pointer || "/"}`);
    }
  }
  for (const key of STRING_KEYWORDS) {
    if (key in node && typeof node[key] !== "string") {
      throw new Error(`not a valid 2020-12 schema: ${key} is not a string at ${pointer || "/"}`);
    }
  }
  if (
    "required" in node &&
    !(Array.isArray(node.required) && node.required.every((r) => typeof r === "string"))
  ) {
    throw new Error(`not a valid 2020-12 schema: required at ${pointer || "/"}`);
  }
  if ("enum" in node && !Array.isArray(node.enum)) {
    throw new Error(`not a valid 2020-12 schema: enum is not an array at ${pointer || "/"}`);
  }
  for (const key of SUBSCHEMA) if (key in node) vetNode(node[key], `${pointer}/${key}`, ownBase);
  for (const key of SCHEMA_LIST) {
    if (!(key in node)) continue;
    if (!Array.isArray(node[key]))
      throw new Error(`not a valid 2020-12 schema: ${key} is not an array at ${pointer || "/"}`);
    for (const [i, child] of node[key].entries()) vetNode(child, `${pointer}/${key}/${i}`, ownBase);
  }
  for (const key of SCHEMA_MAP) {
    if (!(key in node)) continue;
    if (!isObject(node[key]))
      throw new Error(`not a valid 2020-12 schema: ${key} is not an object at ${pointer || "/"}`);
    for (const [name, child] of Object.entries(node[key]))
      vetNode(child, `${pointer}/${key}/${name}`, ownBase);
  }
}

function loadSchema(file) {
  const name = basename(file);
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    throw new GenerationError(`${name}: cannot be read`);
  }
  if (text.charCodeAt(0) === 0xfeff) throw new GenerationError(`${name}: a byte-order mark is not allowed`);
  let schema;
  try {
    schema = JSON.parse(text);
  } catch {
    throw new GenerationError(`${name}: not valid JSON`);
  }
  try {
    const ownBase =
      typeof schema?.$id === "string" ? schema.$id.slice(0, schema.$id.lastIndexOf("/") + 1) : "\0";
    vetNode(schema, "", ownBase);
  } catch (error) {
    throw new GenerationError(`${name}: ${error.message}`);
  }
  return schema;
}

/** Names exported by a generated module (`export type Name` / `export interface Name`). */
function exportedNames(text) {
  return [...text.matchAll(/^export (?:interface|type) ([A-Za-z0-9_]+)/gm)].map((m) => m[1]);
}

async function generate(contractsDir) {
  const files = readdirSync(contractsDir)
    .filter((name) => name.endsWith(SCHEMA_SUFFIX))
    .sort();
  const schemas = files.map((name) => [name, loadSchema(join(contractsDir, name))]);
  const out = new Map();
  const seen = new Set();
  const indexLines = [
    "/* Generated by web/scripts/gen-types.mjs from the schemas in contracts/. Do not edit. */",
    "// A name that two schemas share is re-exported from the first schema only; import the others from their module.",
    "",
  ];
  for (const [name, schema] of schemas) {
    const stem = name.slice(0, -SCHEMA_SUFFIX.length);
    let text;
    try {
      text = await compile(schema, stem, {
        bannerComment: `/* Generated from contracts/${name} by web/scripts/gen-types.mjs. Do not edit. */`,
        additionalProperties: false,
        strictIndexSignatures: true,
        unreachableDefinitions: true,
        declareExternallyReferenced: true,
        format: false,
        cwd: contractsDir.endsWith("/") ? contractsDir : `${contractsDir}/`,
      });
    } catch (error) {
      throw new GenerationError(`${name}: ${String(error.message).split("\n")[0].slice(0, 200)}`);
    }
    text = `${text.replaceAll("\r\n", "\n").trimEnd()}\n`;
    out.set(`${stem}.ts`, text);
    const names = exportedNames(text).filter((n) => !seen.has(n));
    for (const n of names) seen.add(n);
    indexLines.push(`export type { ${names.join(", ")} } from "./${stem}";`);
  }
  out.set("index.ts", `${indexLines.join("\n")}\n`);
  return out;
}

function existing(dir) {
  const map = new Map();
  if (!existsSync(dir)) return map;
  for (const name of readdirSync(dir).sort()) {
    if (name.endsWith(".ts")) map.set(name, readFileSync(join(dir, name), "utf8").replaceAll("\r\n", "\n"));
  }
  return map;
}

function parseArgs(argv) {
  const args = { check: false, contracts: DEFAULT_CONTRACTS, out: DEFAULT_OUT };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--check") args.check = true;
    else if (arg === "--contracts" || arg === "--out") {
      const value = argv[i + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${arg} needs a value`);
      args[arg.slice(2)] = resolve(value);
      i += 1;
    } else throw new Error(`unknown option ${arg}`);
  }
  return args;
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    console.error(
      `usage error: ${error.message}\nusage: node scripts/gen-types.mjs [--check] [--contracts DIR] [--out DIR]`,
    );
    return 2;
  }
  if (!existsSync(args.contracts)) {
    console.error("usage error: --contracts is not a directory");
    return 2;
  }
  let expected;
  try {
    expected = await generate(args.contracts);
  } catch (error) {
    if (!(error instanceof GenerationError)) throw error;
    console.error(`generation failed: ${error.message}`);
    return 3;
  }
  const current = existing(args.out);
  const problems = [
    ...[...expected.keys()].filter((name) => !current.has(name)).map((name) => `missing: ${name}`),
    ...[...expected.keys()]
      .filter((name) => current.has(name) && current.get(name) !== expected.get(name))
      .map((name) => `differs: ${name}`),
    ...[...current.keys()].filter((name) => !expected.has(name)).map((name) => `orphan: ${name}`),
  ];
  if (args.check) {
    if (problems.length > 0) {
      console.log(
        `generated types are stale (run: pnpm gen:types):\n${problems.map((p) => `  ${p}`).join("\n")}`,
      );
      return 1;
    }
    console.log("generated types are current");
    return 0;
  }
  mkdirSync(args.out, { recursive: true });
  for (const [name, text] of expected)
    if (current.get(name) !== text) writeFileSync(join(args.out, name), text);
  for (const name of current.keys()) if (!expected.has(name)) rmSync(join(args.out, name));
  console.log(
    `generated ${expected.size} modules in ${basename(args.out)}${problems.length ? ` (${problems.length} changed)` : ""}`,
  );
  return 0;
}

process.exitCode = await main();
