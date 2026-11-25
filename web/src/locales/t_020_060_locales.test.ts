// T-020-060 [red] · FR-020-45, FR-000-03: locale key parity (EN/ES) and no JSX text literals outside the locale files.
//
// Expected module (plain ESM, no top-level await, no dependencies beyond Node and the repository's own dev tools; the test loads it with
// Node's require(esm), so it must not need a bundler):  tools/check_locales.mjs  (repository root)
//   export function compareLocaleObjects(en: object, es: object, file: string): Violation[]
//     Walks both objects (nested objects = key paths joined with "."; own enumerable keys only, "__proto__" is an ordinary key) and reports
//       { kind: "missing-in-es", key }            a leaf key of EN that ES lacks
//       { kind: "missing-in-en", key }            a leaf key of ES that EN lacks
//       { kind: "placeholder-mismatch", key }     the sets of {{placeholder}} names of the two strings differ
//       { kind: "empty-value", key }              an empty or whitespace-only string, in either language
//       { kind: "not-a-string", key }             a leaf that is not a string (number, boolean, null, array)
//     Every violation also carries { file, message } and `message` names both the key and the file.
//   export function checkLocaleDir(dir: string): Violation[]
//     `dir` holds one folder per language (`en`, `es`) of namespace files `<ns>.json`. Reports { kind: "namespace-missing-in-es" | "namespace-missing-in-en",
//     file } for a namespace present in one language only, { kind: "invalid-json", file } for a file that does not parse, and the
//     compareLocaleObjects violations of every namespace present in both. A clean directory gives [].
//   export function findJsxTextLiterals(source: string, file: string): Violation[]
//     A JSX text literal is (a) JSX text between tags or fragment tags that contains a Unicode letter or digit, or (b) a `{"..."}` / `{`...`}`
//     string expression directly inside an element whose text contains a letter or digit. Whitespace, punctuation-only separators such as " · ",
//     `{" "}`, JSX comments, attribute values and `{t("key")}` calls are allowed. Reports { kind: "jsx-text-literal", file, line, message } with the
//     1-based line of the literal; `message` names the file and the line.
//   export function checkJsxSources(dir: string): Violation[]
//     Applies findJsxTextLiterals to every `.tsx` file under `dir`, skipping `*.test.tsx`, `*.spec.tsx` and the `test-support` folder.
//   CLI:  node tools/check_locales.mjs [--locales <dir>] [--src <dir>]    (defaults: web/src/locales and web/src)
//     prints one line per violation (naming the key or the file) and exits 1 when there is any, else prints nothing to stderr and exits 0.
//   Wiring: web/package.json runs it from its `check` script (CI), and web/biome.json enables the lint rule style.noJsxLiterals at level "error".
// Oracles: planted defects written in this file (a missing key, a placeholder mismatch, a planted JSX literal); no output of the checker is used
//          to derive an expectation.
import { spawnSync } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

// This file is web/src/locales/: SRC = web/src, WEB = web, ROOT = repository root (path strings; jsdom replaces `URL`).
const HERE = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(HERE, "..");
const WEB = resolve(HERE, "../..");
const ROOT = resolve(HERE, "../../..");
const SCRIPT = join(ROOT, "tools", "check_locales.mjs");

interface Violation {
  kind: string;
  file: string;
  key?: string;
  line?: number;
  message: string;
}
interface Checker {
  compareLocaleObjects(en: object, es: object, file: string): Violation[];
  checkLocaleDir(dir: string): Violation[];
  findJsxTextLiterals(source: string, file: string): Violation[];
  checkJsxSources(dir: string): Violation[];
}

// The tool is a plain ESM file without top-level await, loaded with Node's require(esm) (Vite's module runner mis-resolves
// absolute file URLs on Windows).
const nodeRequire = createRequire(join(HERE, "noop.cjs"));

async function checker(): Promise<Checker> {
  return nodeRequire(SCRIPT) as Checker;
}

const summary = (vs: Violation[]) => vs.map((v) => `${v.kind}:${v.key ?? ""}`).sort();

let dir = "";
beforeEach(() => {
  dir = mkdtempSync(join(tmpdir(), "p6-locales-"));
});
afterEach(() => {
  rmSync(dir, { recursive: true, force: true });
});

function writeLocale(lang: string, ns: string, content: unknown) {
  mkdirSync(join(dir, lang), { recursive: true });
  writeFileSync(
    join(dir, lang, `${ns}.json`),
    typeof content === "string" ? content : JSON.stringify(content),
  );
}

describe("key parity of two locale objects (FR-020-45)", () => {
  it("FR-020-45 · identical key sets give no violation", async () => {
    const { compareLocaleObjects } = await checker();
    const o = { a: { b: "x", c: "y {{n}}" }, d: "z" };
    const p = { a: { b: "equis", c: "ye {{n}}" }, d: "zeta" };
    expect(compareLocaleObjects(o, p, "app.json")).toEqual([]);
  });

  it("FR-020-45 · a key missing in ES, a key missing in EN and a placeholder mismatch are reported by key path and file", async () => {
    const { compareLocaleObjects } = await checker();
    const en = { a: { b: "x", c: "y" }, d: "z {{n}}" };
    const es = { a: { b: "equis" }, d: "zeta", e: "extra" };
    const vs = compareLocaleObjects(en, es, "app.json");
    expect(summary(vs)).toEqual(["missing-in-en:e", "missing-in-es:a.c", "placeholder-mismatch:d"].sort());
    for (const v of vs) {
      expect(v.file).toBe("app.json");
      expect(v.message).toContain("app.json");
      expect(v.message).toContain(v.key as string);
    }
  });

  it("FR-020-45 · a whole subtree missing in ES is reported leaf by leaf", async () => {
    const { compareLocaleObjects } = await checker();
    const vs = compareLocaleObjects({ pages: { a: { title: "T", lead: "L" } } }, { pages: {} }, "app.json");
    expect(summary(vs)).toEqual(["missing-in-es:pages.a.lead", "missing-in-es:pages.a.title"]);
  });

  it("FR-020-45 · placeholders compare as sets of names, with spaces and format options ignored", async () => {
    const { compareLocaleObjects } = await checker();
    expect(
      compareLocaleObjects(
        { k: "{{ count }} items for {{name}}" },
        { k: "{{name}} tiene {{count}}" },
        "f.json",
      ),
    ).toEqual([]);
    expect(
      summary(compareLocaleObjects({ k: "{{count}} items" }, { k: "{{total}} elementos" }, "f.json")),
    ).toEqual(["placeholder-mismatch:k"]);
  });

  it("FR-020-45 · empty and non-string values are violations in either language", async () => {
    const { compareLocaleObjects } = await checker();
    const vs = compareLocaleObjects(
      { a: "x", b: "y", c: "z", d: "w" },
      { a: "", b: "   ", c: 5, d: null },
      "f.json",
    );
    expect(summary(vs)).toEqual(["empty-value:a", "empty-value:b", "not-a-string:c", "not-a-string:d"]);
    const en = compareLocaleObjects({ a: "" }, { a: "x" }, "f.json");
    expect(summary(en)).toEqual(["empty-value:a"]);
  });

  it("FR-020-45 · hostile keys: __proto__, unicode and dotted-looking names compare as ordinary keys and pollute nothing", async () => {
    const { compareLocaleObjects } = await checker();
    const es = JSON.parse('{"__proto__": {"polluted": "yes"}, "año": "x", "k": "v"}');
    const en = JSON.parse('{"año": "x", "k": "v"}');
    const vs = compareLocaleObjects(en, es, "f.json");
    expect(summary(vs)).toEqual(["missing-in-en:__proto__.polluted"]);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
    expect(compareLocaleObjects({ ñandú: "a" }, { ñandú: "b" }, "f.json")).toEqual([]);
  });
});

describe("locale directory (FR-020-45)", () => {
  it("FR-020-45 · a clean directory gives no violation", async () => {
    const { checkLocaleDir } = await checker();
    writeLocale("en", "app", { a: "x" });
    writeLocale("es", "app", { a: "equis" });
    writeLocale("en", "shell", { b: { c: "y" } });
    writeLocale("es", "shell", { b: { c: "ye" } });
    expect(checkLocaleDir(dir)).toEqual([]);
  });

  it("FR-020-45 · a planted missing key and a namespace present in one language only are reported", async () => {
    const { checkLocaleDir } = await checker();
    writeLocale("en", "app", { a: "x", b: "y" });
    writeLocale("es", "app", { a: "equis" });
    writeLocale("en", "extra", { z: "z" });
    writeLocale("es", "solo-es", { z: "z" });
    const vs = checkLocaleDir(dir);
    expect(vs.some((v) => v.kind === "missing-in-es" && v.key === "b" && v.file.includes("app"))).toBe(true);
    expect(vs.some((v) => v.kind === "namespace-missing-in-es" && v.file.includes("extra"))).toBe(true);
    expect(vs.some((v) => v.kind === "namespace-missing-in-en" && v.file.includes("solo-es"))).toBe(true);
  });

  it("FR-020-45 · a file that is not JSON is reported by name and does not stop the other checks", async () => {
    const { checkLocaleDir } = await checker();
    writeLocale("en", "app", "{ not json");
    writeLocale("es", "app", { a: "x" });
    writeLocale("en", "shell", { a: "x" });
    writeLocale("es", "shell", {});
    const vs = checkLocaleDir(dir);
    expect(vs.some((v) => v.kind === "invalid-json" && v.file.includes("app"))).toBe(true);
    expect(vs.some((v) => v.kind === "missing-in-es" && v.key === "a" && v.file.includes("shell"))).toBe(
      true,
    );
  });

  it("FR-020-45 · the shipped EN and ES locale files have the same keys and placeholders", async () => {
    const { checkLocaleDir } = await checker();
    expect(checkLocaleDir(join(WEB, "src", "locales"))).toEqual([]);
  });
});

describe("JSX text literals (FR-020-45)", () => {
  it("FR-020-45 · accepts text that comes from the locale files, attributes, whitespace and punctuation separators", async () => {
    const { findJsxTextLiterals } = await checker();
    const clean = [
      "export function A({ n }: { n: number }) {",
      "  const { t } = useTranslation();",
      "  return (",
      '    <p className="x" aria-label="Close">',
      '      <strong>{n}</strong> · {t("a.b")} ·{" "}',
      '      {/* a comment */}<span>{t("c")}</span>',
      "    </p>",
      "  );",
      "}",
    ].join("\n");
    expect(findJsxTextLiterals(clean, "A.tsx")).toEqual([]);
  });

  it("FR-020-45 · reports a planted literal with the file and its line", async () => {
    const { findJsxTextLiterals } = await checker();
    const dirty = [
      "export function A() {",
      "  return (",
      "    <section>",
      "      <h1>Hello world</h1>",
      "    </section>",
      "  );",
      "}",
    ].join("\n");
    const vs = findJsxTextLiterals(dirty, "Planted.tsx");
    expect(vs).toHaveLength(1);
    expect(vs[0]?.kind).toBe("jsx-text-literal");
    expect(vs[0]?.file).toBe("Planted.tsx");
    expect(vs[0]?.line).toBe(4);
    expect(vs[0]?.message).toContain("Planted.tsx");
    expect(vs[0]?.message).toContain("4");
  });

  it("FR-020-45 · reports every literal: text in a fragment, a digit-only literal, a string expression and a template string", async () => {
    const { findJsxTextLiterals } = await checker();
    const src = [
      "export const A = () => <>Fragment text</>;",
      "export const B = () => <p>42</p>;",
      'export const C = () => <p>{"Spelled in an expression"}</p>;',
      "export const D = () => <p>{`Template literal`}</p>;",
      "export const E = () => (",
      "  <div>",
      "    Multi line text",
      "  </div>",
      ");",
    ].join("\n");
    const vs = findJsxTextLiterals(src, "Many.tsx");
    expect(vs.map((v) => v.kind)).toEqual(Array(5).fill("jsx-text-literal"));
    const lines = vs.map((v) => v.line as number).sort((a, b) => a - b);
    expect(lines.slice(0, 4)).toEqual([1, 2, 3, 4]);
  });

  it("FR-020-45 · does not report a string literal in an attribute, an import or a call", async () => {
    const { findJsxTextLiterals } = await checker();
    const src = [
      'import { x } from "somewhere";',
      "export const A = () => (",
      '  <img src="a.png" alt="A description" title={"Tooltip"} data-x={f("literal")} />',
      ");",
    ].join("\n");
    expect(findJsxTextLiterals(src, "A.tsx")).toEqual([]);
  });

  it("FR-020-45 · tolerates source that is not valid TSX without throwing", async () => {
    const { findJsxTextLiterals } = await checker();
    expect(() => findJsxTextLiterals("export const = <p>unterminated", "Bad.tsx")).not.toThrow();
    expect(() => findJsxTextLiterals("", "Empty.tsx")).not.toThrow();
    expect(findJsxTextLiterals("", "Empty.tsx")).toEqual([]);
  });

  it("FR-020-45 · checks every .tsx of a directory except tests and test support", async () => {
    const { checkJsxSources } = await checker();
    mkdirSync(join(dir, "routes"), { recursive: true });
    mkdirSync(join(dir, "test-support"), { recursive: true });
    writeFileSync(join(dir, "routes", "Bad.tsx"), "export const A = () => <p>Hello</p>;\n");
    writeFileSync(join(dir, "routes", "Good.tsx"), 'export const A = () => <p>{t("k")}</p>;\n');
    writeFileSync(join(dir, "routes", "Bad.test.tsx"), "export const A = () => <p>Hello</p>;\n");
    writeFileSync(join(dir, "test-support", "render.tsx"), "export const A = () => <p>Hello</p>;\n");
    const vs = checkJsxSources(dir);
    expect(vs).toHaveLength(1);
    expect(vs[0]?.file).toContain("Bad.tsx");
    expect(vs[0]?.file).not.toContain("Bad.test.tsx");
  });

  it("FR-020-45 · the shipped components contain no JSX text literal", async () => {
    const { checkJsxSources } = await checker();
    expect(checkJsxSources(SRC)).toEqual([]);
  });
});

describe("command line and CI wiring (FR-020-45)", () => {
  function run(args: string[]) {
    return spawnSync(process.execPath, [SCRIPT, ...args], { encoding: "utf8" });
  }

  it("FR-020-45 · the command exits 1 and names the key or file for a planted defect, and 0 for a clean tree", () => {
    writeLocale("en", "app", { a: "x", missingKeyB: "y" });
    writeLocale("es", "app", { a: "equis" });
    mkdirSync(join(dir, "src"), { recursive: true });
    writeFileSync(join(dir, "src", "Planted.tsx"), "export const A = () => <p>Hello</p>;\n");
    const bad = run(["--locales", dir, "--src", join(dir, "src")]);
    expect(bad.status).toBe(1);
    const out = `${bad.stdout}${bad.stderr}`;
    expect(out).toContain("missingKeyB");
    expect(out).toContain("app.json");
    expect(out).toContain("Planted.tsx");

    writeLocale("es", "app", { a: "equis", missingKeyB: "ye" });
    writeFileSync(join(dir, "src", "Planted.tsx"), 'export const A = () => <p>{t("a")}</p>;\n');
    const good = run(["--locales", dir, "--src", join(dir, "src")]);
    expect(good.status).toBe(0);
  });

  it("FR-020-45 · the default run on the repository passes", () => {
    const res = run([]);
    expect(res.status, `${res.stdout}${res.stderr}`).toBe(0);
  });

  it("FR-020-45 · web/package.json runs the checker from its check script", () => {
    const pkg = JSON.parse(readFileSync(join(WEB, "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    const all = Object.values(pkg.scripts).join("\n");
    expect(all).toContain("check_locales");
    expect(pkg.scripts.check).toBeDefined();
    const check = pkg.scripts.check as string;
    const delegated = check.match(/(?:pnpm(?: run)?|npm run)\s+([\w:-]+)/g) ?? [];
    const viaScript = delegated.some((cmd) => {
      const name = cmd.split(/\s+/).pop() as string;
      return (pkg.scripts[name] ?? "").includes("check_locales");
    });
    expect(check.includes("check_locales") || viaScript).toBe(true);
  });

  it("FR-020-45 · biome enables the rule style.noJsxLiterals at level error", () => {
    const biome = JSON.parse(readFileSync(join(WEB, "biome.json"), "utf8")) as {
      linter?: { rules?: { style?: { noJsxLiterals?: unknown } } };
    };
    const rule = biome.linter?.rules?.style?.noJsxLiterals;
    const level = typeof rule === "string" ? rule : (rule as { level?: string } | undefined)?.level;
    expect(level).toBe("error");
  });
});
