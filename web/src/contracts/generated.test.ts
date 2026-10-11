// @vitest-environment node
//
// T-001-002 · the generated TypeScript types: FR-001-41, FR-001-42, FR-001-44, FR-001-46, NFR-001-02, NFR-001-04.
//
// Oracles: `tsc` (the reference compiler, TypeScript 7) over a program built here from the valid conformance-corpus
// fixtures (every example must type-check against its generated type; seeded `@ts-expect-error` lines must fail to
// type-check, so the directive is satisfied); a byte comparison of two fresh generations with each other and with the
// committed files (determinism, drift); a hand-written scanner for "only type declarations", itself checked on seeded
// runtime and type-only snippets.
//
// Expected API: `node scripts/gen-types.mjs [--check] [--contracts DIR] [--out DIR]` (`pnpm gen:types`) writes one
// type-only module per `contracts/<stem>.schema.json` into `src/contracts/generated/<stem>.ts` plus `index.ts`
// (`export type { ... }`), each starting with the banner `/* Generated from contracts/<file> by
// web/scripts/gen-types.mjs. Do not edit. */`. `--check` exits 0 when the folder equals a fresh generation and 1
// otherwise (listing every differing, orphan and missing file by name, writing nothing); an invalid schema, an
// unsupported construct (`prefixItems`, `$dynamicRef`, a remote `$ref`) or an unknown option exits non-zero, names the
// schema file and writes nothing. Type names: `Run`, `WebIndex` (manifest), `Recipe`, `JobRequest` (recipe),
// `PitStudioToolRegistry`, `PitStudioSourceRegistry`, `PitStudioCapabilityReport`.

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  cpSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const WEB = resolve(HERE, "../..");
const ROOT = resolve(WEB, "..");
const GENERATED = join(HERE, "generated");
const FIXTURES = join(ROOT, "tests", "contract", "fixtures");
const CONTRACTS = join(ROOT, "contracts");
const STEMS = ["manifest", "recipe", "tools", "sources", "capabilities"] as const;
const WORK = mkdtempSync(join(process.env.PITSTUDIO_TMP ?? tmpdir(), "gen-types-test-"));
const SLOW = 180_000;
const DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema";

afterAll(() => {
  rmSync(WORK, { recursive: true, force: true });
});

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

type Entry = {
  file: string;
  schema: string;
  target: string;
  kind: string;
  valid: boolean;
  tags: string[];
};

function sha(path: string): string {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function snapshot(folder: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!existsSync(folder)) return out;
  for (const name of readdirSync(folder, { recursive: true, encoding: "utf8" }).sort()) {
    const full = join(folder, name);
    if (statSync(full).isFile()) out[name.replaceAll("\\", "/")] = sha(full);
  }
  return out;
}

function generator(...args: string[]) {
  const script = join(WEB, "scripts", "gen-types.mjs");
  expect(existsSync(script), "web/scripts/gen-types.mjs must exist (task T-001-002)").toBe(true);
  const run = spawnSync(process.execPath, [script, ...args], { cwd: WEB, encoding: "utf8", timeout: SLOW });
  return { code: run.status, text: `${run.stdout}\n${run.stderr}` };
}

function freshInto(name: string): string {
  const out = join(WORK, name);
  const run = generator("--out", out);
  expect(run.code, run.text).toBe(0);
  return out;
}

function contractsCopy(name: string): string {
  const dir = join(WORK, name);
  mkdirSync(dir, { recursive: true });
  for (const stem of STEMS) cpSync(join(CONTRACTS, `${stem}.schema.json`), join(dir, `${stem}.schema.json`));
  return dir;
}

function stripCommentsAndStrings(source: string): string {
  let text = "";
  let i = 0;
  while (i < source.length) {
    const c = source.charAt(i);
    const next = source.charAt(i + 1);
    if (c === "/" && next === "*") {
      const end = source.indexOf("*/", i + 2);
      i = end < 0 ? source.length : end + 2;
    } else if (c === "/" && next === "/") {
      const end = source.indexOf("\n", i);
      i = end < 0 ? source.length : end;
    } else if (c === '"' || c === "'" || c === "`") {
      let j = i + 1;
      while (j < source.length && source.charAt(j) !== c) j += source.charAt(j) === "\\" ? 2 : 1;
      text += '""';
      i = j + 1;
    } else {
      text += c;
      i += 1;
    }
  }
  return text;
}

const STATEMENT_KEYWORDS = [
  "const",
  "let",
  "var",
  "function",
  "class",
  "enum",
  "namespace",
  "module",
  "declare",
  "default",
];

/** Top-level tokens that make a module more than type declarations: runtime statements, value imports and exports. */
function runtimeStatements(source: string): string[] {
  const tokens = stripCommentsAndStrings(source).match(/[A-Za-z_$][\w$]*|[{}[\]()]|[^\s\w]/g) ?? [];
  const offenders: string[] = [];
  let depth = 0;
  tokens.forEach((token, i) => {
    const next = tokens[i + 1] ?? "";
    if (token === "{" || token === "[" || token === "(") depth += 1;
    else if (token === "}" || token === "]" || token === ")") depth -= 1;
    else if (depth === 0) {
      if (token === "export" && next !== "interface" && next !== "type") offenders.push(`export ${next}`);
      else if (token === "import" && next !== "type") offenders.push(`import ${next}`);
      else if (STATEMENT_KEYWORDS.includes(token)) offenders.push(token);
    }
  });
  return offenders;
}

describe("the type-only scanner (self-check on seeded snippets)", () => {
  it("FR-001-44 · flags runtime statements", () => {
    for (const code of [
      "export const x = 1;",
      "export function f() {}",
      "export class C {}",
      "export enum E { A }",
      'import x from "y";',
      "export default {};",
      "let a = 1;",
      "export { a };",
    ]) {
      expect(runtimeStatements(code), code).not.toEqual([]);
    }
  });

  it("FR-001-44 · accepts interfaces, aliases and type-only imports and exports", () => {
    for (const code of [
      "export interface A { class: string; const?: 1 | null }",
      'export type B = { enum: "a" | "b" }[] | null;',
      'import type { A } from "./a";',
      'export type { A } from "./a";',
      "/* banner */\n// comment\nexport type C = string;\n",
    ]) {
      expect(runtimeStatements(code), code).toEqual([]);
    }
  });
});

describe("the generated modules", () => {
  it("DC-001-07 · every contract has a generated TypeScript module under web/src/contracts/generated", () => {
    const contracts = readdirSync(CONTRACTS)
      .filter((name) => name.endsWith(".schema.json"))
      .map((name) => name.replace(".schema.json", ""))
      .sort();
    expect(contracts).toEqual([...STEMS].sort());
    for (const stem of contracts) expect(existsSync(join(GENERATED, `${stem}.ts`)), `${stem}.ts`).toBe(true);
  });

  it("FR-001-41 · one type-only module per contract plus an index, each with the banner comment", () => {
    for (const stem of STEMS) {
      const file = join(GENERATED, `${stem}.ts`);
      expect(existsSync(file), `${stem}.ts`).toBe(true);
      const first = readFileSync(file, "utf8").split("\n", 1)[0];
      expect(first).toBe(
        `/* Generated from contracts/${stem}.schema.json by web/scripts/gen-types.mjs. Do not edit. */`,
      );
    }
    const index = readFileSync(join(GENERATED, "index.ts"), "utf8");
    expect(index).toContain("export type {");
    for (const stem of STEMS) expect(index).toMatch(new RegExp(`from ["']\\./${stem}["']`));
    expect(readdirSync(GENERATED).sort()).toEqual([...STEMS.map((s) => `${s}.ts`), "index.ts"].sort());
  });

  it("FR-001-44 · the modules contain only type declarations and comments", () => {
    for (const name of [...STEMS, "index"]) {
      const text = readFileSync(join(GENERATED, `${name}.ts`), "utf8");
      expect(text.length).toBeGreaterThan(100);
      expect(runtimeStatements(text), name).toEqual([]);
    }
  });

  it("NFR-001-02 · no runtime import of the generated types and none of their names in the built JavaScript", () => {
    const names = new Set<string>();
    for (const stem of STEMS) {
      const text = readFileSync(join(GENERATED, `${stem}.ts`), "utf8");
      for (const m of text.matchAll(/export (?:interface|type) ([A-Za-z0-9_]+)/g)) {
        const id = m[1] ?? "";
        if (id.length >= 8 && /^[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+$/.test(id)) names.add(id);
      }
    }
    expect(names.size).toBeGreaterThan(20);
    const sources: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir, { withFileTypes: true })) {
        const full = join(dir, entry.name);
        if (entry.isDirectory()) {
          if (full !== GENERATED && entry.name !== "node_modules") walk(full);
        } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\./.test(entry.name)) sources.push(full);
      }
    };
    walk(join(WEB, "src"));
    for (const file of sources) {
      for (const line of readFileSync(file, "utf8").split("\n")) {
        if (/contracts\/generated/.test(line) && /^\s*(import|export)\b/.test(line)) {
          expect(line, relative(WEB, file)).toMatch(/^\s*(import|export) type\b/);
        }
      }
    }
    const build = join(WEB, "build", "client");
    if (existsSync(build)) {
      const scan = (dir: string) => {
        for (const entry of readdirSync(dir, { withFileTypes: true })) {
          const full = join(dir, entry.name);
          if (entry.isDirectory()) scan(full);
          else if (entry.name.endsWith(".js")) {
            const code = readFileSync(full, "utf8");
            for (const id of names) expect(code.includes(id), `${id} in ${relative(WEB, full)}`).toBe(false);
          }
        }
      };
      scan(build);
    }
  });
});

describe("the generator", () => {
  it(
    "FR-001-41 · two generations are byte-identical and equal the committed modules (NFR-001-04)",
    () => {
      const a = freshInto("a");
      const b = freshInto("b");
      expect(snapshot(a)).toEqual(snapshot(b));
      expect(snapshot(a)).toEqual(snapshot(GENERATED));
      expect(Object.keys(snapshot(a)).sort()).toEqual([...STEMS.map((s) => `${s}.ts`), "index.ts"].sort());
      for (const file of Object.keys(snapshot(a))) {
        const text = readFileSync(join(a, file), "utf8");
        expect(text).not.toContain("\r");
        expect(text).not.toContain(ROOT.replaceAll("\\", "/"));
      }
    },
    SLOW,
  );

  it(
    "FR-001-42 · --check passes on a fresh folder and names every drifting, orphan and missing file",
    () => {
      const out = freshInto("drift");
      const ok = generator("--check", "--out", out);
      expect(ok.code, ok.text).toBe(0);
      const before = snapshot(out);
      const file = join(out, "tools.ts");
      const text = readFileSync(file, "utf8");
      writeFileSync(file, `${text.slice(0, 200)}${text.charAt(200) === "x" ? "y" : "x"}${text.slice(201)}`);
      writeFileSync(join(out, "ghost.ts"), "// orphan\n");
      rmSync(join(out, "recipe.ts"));
      const drift = generator("--check", "--out", out);
      expect(drift.code, drift.text).toBe(1);
      for (const name of ["tools.ts", "ghost.ts", "recipe.ts"]) expect(drift.text).toContain(name);
      const after = snapshot(out);
      expect(after["tools.ts"]).not.toBe(before["tools.ts"]); // --check repaired nothing
      expect(Object.keys(after)).not.toContain("recipe.ts");
      const missing = generator("--check", "--out", join(WORK, "does-not-exist"));
      expect(missing.code).toBe(1);
    },
    SLOW,
  );

  const BAD: Record<string, string> = {
    prefix: JSON.stringify({ $schema: DRAFT_2020_12, type: "array", prefixItems: [{ type: "string" }] }),
    dynamic: JSON.stringify({
      $schema: DRAFT_2020_12,
      $dynamicAnchor: "node",
      type: "object",
      properties: { child: { $dynamicRef: "#node" } },
    }),
    remote: JSON.stringify({
      $schema: DRAFT_2020_12,
      type: "object",
      properties: { x: { $ref: "https://example.com/other.schema.json#/$defs/x" } },
    }),
    malformed: '{"type": "object"',
    metainvalid: JSON.stringify({ $schema: DRAFT_2020_12, type: "nonsense" }),
  };

  for (const [label, content] of Object.entries(BAD)) {
    it(
      `FR-001-46 · ${label}: fails naming the schema and leaves the output folder untouched`,
      () => {
        const out = freshInto(`committed-${label}`);
        const before = snapshot(out);
        const contracts = contractsCopy(`contracts-${label}`);
        writeFileSync(join(contracts, "bad.schema.json"), content);
        const run = generator("--contracts", contracts, "--out", out);
        expect(run.code).not.toBe(0);
        expect(run.text).toContain("bad.schema.json");
        expect(snapshot(out)).toEqual(before);
      },
      SLOW,
    );
  }

  it(
    "FR-001-46 · an unknown option is a usage error and writes nothing",
    () => {
      const out = freshInto("committed-usage");
      const before = snapshot(out);
      const run = generator("--frobnicate", "--out", out);
      expect(run.code).not.toBe(0);
      expect(run.code).not.toBe(1);
      expect(snapshot(out)).toEqual(before);
    },
    SLOW,
  );
});

describe("type checking against the conformance corpus", () => {
  const TYPES: Record<string, [string, string]> = {
    run: ["manifest", "Run"],
    "web-index": ["manifest", "WebIndex"],
    recipe: ["recipe", "Recipe"],
    "job-request": ["recipe", "JobRequest"],
    tools: ["tools", "PitStudioToolRegistry"],
    sources: ["sources", "PitStudioSourceRegistry"],
    capabilities: ["capabilities", "PitStudioCapabilityReport"],
  };

  function validExamples(): { kind: string; file: string; doc: Json }[] {
    const index = JSON.parse(readFileSync(join(FIXTURES, "index.json"), "utf8")) as { fixtures: Entry[] };
    return index.fixtures
      .filter((e) => e.valid && e.file.endsWith(".json"))
      .map((e) => ({
        kind: e.kind,
        file: e.file,
        doc: JSON.parse(readFileSync(join(FIXTURES, e.file), "utf8")) as Json,
      }));
  }

  function withChange(doc: Json, path: (string | number)[], value: Json): Json {
    const copy = JSON.parse(JSON.stringify(doc)) as Json;
    const last = path.at(-1);
    if (last === undefined) throw new Error("empty path");
    let node = copy as unknown as Record<string | number, Json>;
    for (const key of path.slice(0, -1)) node = node[key] as unknown as Record<string | number, Json>;
    node[last] = value;
    return copy;
  }

  function typecheck(source: string, name: string): { code: number | null; text: string } {
    const dir = join(WORK, name);
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "check.ts"), source);
    writeFileSync(
      join(dir, "tsconfig.json"),
      JSON.stringify({
        compilerOptions: {
          target: "ES2023",
          module: "ES2022",
          moduleResolution: "bundler",
          strict: true,
          noEmit: true,
          skipLibCheck: true,
          types: [],
          paths: { "@gen/*": [`${GENERATED.replaceAll("\\", "/")}/*`] },
        },
        files: ["check.ts"],
      }),
    );
    const manifest = createRequire(import.meta.url).resolve("typescript/package.json");
    const tsc = join(dirname(manifest), "bin", "tsc");
    const run = spawnSync(process.execPath, [tsc, "-p", join(dir, "tsconfig.json")], {
      encoding: "utf8",
      timeout: SLOW,
    });
    return { code: run.status, text: `${run.stdout}${run.stderr}` };
  }

  it(
    "FR-001-44 · every valid corpus example type-checks against its generated type",
    () => {
      const examples = validExamples();
      expect(examples.length).toBeGreaterThanOrEqual(9);
      const imports = new Set<string>();
      const lines: string[] = [];
      examples.forEach(({ kind, doc }, i) => {
        const [module, type] = TYPES[kind] ?? ["", ""];
        imports.add(`import type { ${type} } from "@gen/${module}";`);
        lines.push(`export const valid${i}: ${type} = ${JSON.stringify(doc)};`);
      });
      const result = typecheck(`${[...imports].join("\n")}\n${lines.join("\n")}\n`, "valid");
      expect(result.text).toBe("");
      expect(result.code).toBe(0);
    },
    SLOW,
  );

  it(
    "FR-001-44 · an unknown property or an out-of-enum value fails type-checking (the expected errors are raised)",
    () => {
      const pick = (kind: string, file: string): Json => {
        const found = validExamples().find((e) => e.kind === kind && e.file.endsWith(file));
        expect(found, `${kind} ${file}`).toBeDefined();
        return found?.doc ?? null;
      };
      const run = pick("run", "manifest.valid.json");
      const web = pick("web-index", "manifest.valid-web-index.json");
      const recipe = pick("recipe", "recipe.valid.json");
      const job = pick("job-request", "recipe.valid-job-request.json");
      const tools = pick("tools", "tools.valid.json");
      const sources = pick("sources", "sources.valid.json");
      const caps = pick("capabilities", "capabilities.valid.json");
      const cases: [string, Json][] = [
        ["Run", withChange(run, ["hostname"], "build-box")],
        ["Run", withChange(run, ["artefacts", 0, "budget_class"], "bogus")],
        ["Run", withChange(run, ["seed"], "20261007")],
        ["Run", withChange(run, ["stages", 0, "status"], "exploded")],
        ["WebIndex", withChange(web, ["generated"], 20261007)],
        ["WebIndex", withChange(web, ["artefacts", 0, "kind"], "hologram")],
        ["Recipe", withChange(recipe, ["profile"], "laptop")],
        ["Recipe", withChange(recipe, ["stages", 0, "env"], "docker")],
        ["JobRequest", withChange(job, ["entry"], "pkg.mod")],
        ["PitStudioToolRegistry", withChange(tools, ["tools", 0, "ring"], "Pilot")],
        ["PitStudioSourceRegistry", withChange(sources, ["sources", 0, "access"], "ftp")],
        ["PitStudioCapabilityReport", withChange(caps, ["probes", "warp_newton", "status"], "ok")],
      ];
      const moduleOf: Record<string, string> = {
        Run: "manifest",
        WebIndex: "manifest",
        Recipe: "recipe",
        JobRequest: "recipe",
        PitStudioToolRegistry: "tools",
        PitStudioSourceRegistry: "sources",
        PitStudioCapabilityReport: "capabilities",
      };
      const imports = [
        ...new Set(cases.map(([type]) => `import type { ${type} } from "@gen/${moduleOf[type]}";`)),
      ];
      const declarations = cases.map(
        ([type, doc], i) => `export const bad${i}: ${type} = ${JSON.stringify(doc)};`,
      );
      const withDirectives = declarations.map((d, i) => `// @ts-expect-error seeded violation ${i}\n${d}`);
      // each directive is satisfied only if the line below it has a type error (an unused one is TS2578)
      const satisfied = typecheck(`${imports.join("\n")}\n${withDirectives.join("\n")}\n`, "invalid");
      expect(satisfied.text).toBe("");
      expect(satisfied.code).toBe(0);
      // and without the directives every seeded example is reported
      const plain = typecheck(`${imports.join("\n")}\n${declarations.join("\n")}\n`, "invalid-plain");
      expect(plain.code).not.toBe(0);
      expect((plain.text.match(/error TS/g) ?? []).length).toBeGreaterThanOrEqual(cases.length);
    },
    SLOW,
  );
});
