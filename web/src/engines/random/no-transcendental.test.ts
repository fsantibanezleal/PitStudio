// @vitest-environment node
//
// T-007-012 (3/3) · no transcendental function in the variate and DES modules: FR-007-06.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-06 (the TypeScript variate and DES modules contain no call to Math.exp, Math.log, Math.log1p, Math.log2, Math.log10, Math.expm1, Math.pow, Math.sin,
// Math.cos, Math.tan, Math.asin, Math.acos, Math.atan, Math.atan2, Math.sinh, Math.cosh, Math.tanh, Math.cbrt or Math.hypot, and no `**` with a non-integer exponent); plan.md ("TypeScript AST scan
// for the forbidden identifiers"; the repository's TypeScript 7 has no JavaScript compiler API, so the scan parses with @babel/parser, a devDependency).
//
// Oracle: the forbidden list of the spec written out below; the scanner is itself checked on seeded snippets (each forbidden construct is found, each allowed construct is not) before it is applied to
// the real files, so a scanner that finds nothing cannot pass.
//
// Expected files: every non-test `.ts` file under `web/src/engines/random/` (at least `philox.ts` and `variates.ts`) and under `web/src/engines/des/` (at least three files: the engine, the
// dispatchers and the traversal of the twin) is scanned; a violation is reported as `<file>:<line>: <construct>`.

import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "@babel/parser";
import { describe, expect, it } from "vitest";

const ENGINES = resolve(fileURLToPath(new URL(".", import.meta.url)), "..");
const FORBIDDEN = [
  "exp", "log", "log1p", "log2", "log10", "expm1", "pow", "sin", "cos", "tan", "asin", "acos", "atan", "atan2", "sinh", "cosh", "tanh", "cbrt", "hypot",
]; // biome-ignore format: one list

type Node = { type: string; loc?: { start: { line: number } }; [k: string]: unknown };

// an integer literal, possibly signed (`2 ** -53` is an integer exponent)
function isIntegerLiteral(n: Node & { value?: unknown; argument?: Node & { value?: unknown } }): boolean {
  if (n.type === "NumericLiteral") return Number.isInteger(n.value);
  if (n.type === "UnaryExpression" && n.argument)
    return n.argument.type === "NumericLiteral" && Number.isInteger(n.argument.value);
  return false;
}

function scan(code: string, file = "snippet.ts"): string[] {
  const ast = parse(code, { sourceType: "module", plugins: ["typescript"], errorRecovery: false });
  const found: string[] = [];
  const at = (n: Node, what: string) => found.push(`${file}:${n.loc?.start.line ?? 0}: ${what}`);
  const isMath = (n: unknown) =>
    !!n && (n as Node).type === "Identifier" && (n as Node & { name: string }).name === "Math";
  const walk = (n: unknown, parent: Node | null): void => {
    if (Array.isArray(n)) {
      for (const c of n) walk(c, parent);
      return;
    }
    if (!n || typeof n !== "object" || typeof (n as Node).type !== "string") return;
    const node = n as Node;
    if (node.type === "MemberExpression" || node.type === "OptionalMemberExpression") {
      const obj = node.object as Node;
      const prop = node.property as Node & { name?: string; value?: unknown };
      if (isMath(obj)) {
        const name = node.computed
          ? prop.type === "StringLiteral"
            ? String(prop.value)
            : "<computed>"
          : prop.name;
        if (name === "<computed>" || FORBIDDEN.includes(name as string)) at(node, `Math.${name}`);
      }
    } else if (
      isMath(node) &&
      !(
        parent &&
        (parent.type === "MemberExpression" || parent.type === "OptionalMemberExpression") &&
        parent.object === node
      )
    ) {
      at(node, "Math used as a value (alias or destructuring)");
    }
    if (node.type === "BinaryExpression" && node.operator === "**") {
      const r = node.right as Node & { value?: unknown };
      if (!isIntegerLiteral(r)) at(node, "** with a non-integer or non-literal exponent");
    }
    if (node.type === "AssignmentExpression" && node.operator === "**=") {
      const r = node.right as Node & { value?: unknown };
      if (!isIntegerLiteral(r)) at(node, "**= with a non-integer or non-literal exponent");
    }
    if (
      node.type === "Identifier" &&
      ["globalThis", "window", "self"].includes((node as Node & { name: string }).name) &&
      parent?.type === "MemberExpression" &&
      parent.object === node
    ) {
      const p = parent.property as Node & { name?: string };
      if (p.name === "Math") at(node, "globalThis.Math");
    }
    for (const [k, v] of Object.entries(node)) {
      if (
        k === "loc" ||
        k === "start" ||
        k === "end" ||
        k === "extra" ||
        k === "leadingComments" ||
        k === "trailingComments"
      )
        continue;
      walk(v, node);
    }
  };
  walk(ast.program, null);
  return found;
}

function sources(dir: string): string[] {
  try {
    return readdirSync(dir)
      .filter((f) => f.endsWith(".ts") && !f.endsWith(".test.ts") && !f.endsWith(".d.ts"))
      .sort()
      .map((f) => join(dir, f));
  } catch {
    return [];
  }
}

describe("the scanner itself", () => {
  it("FR-007-06 · finds every forbidden Math function, however it is spelled", () => {
    for (const f of FORBIDDEN) expect(scan(`const y = Math.${f}(x);`).length, f).toBe(1);
    expect(scan(`const y = Math["exp"](x);`).length).toBe(1);
    expect(scan(`const k = "exp"; const y = Math[k](x);`).length).toBe(1);
    expect(scan(`const { exp } = Math;`).length).toBe(1);
    expect(scan(`const m = Math; m.exp(1);`).length).toBe(1);
    expect(scan(`const y = globalThis.Math.log(x);`).length).toBeGreaterThanOrEqual(1);
    expect(scan(`const y = Math?.exp(x);`).length).toBeGreaterThanOrEqual(1);
  });

  it("FR-007-06 · finds ** with a non-integer or non-literal exponent and **= alike", () => {
    expect(scan("const y = x ** 0.5;").length).toBe(1);
    expect(scan("const y = x ** n;").length).toBe(1);
    expect(scan("const y = x ** -0.25;").length).toBe(1);
    expect(scan("let y = 2; y **= 1.5;").length).toBe(1);
    expect(scan("let y = 2; y **= k;").length).toBe(1);
  });

  it("FR-007-06 · accepts the allowed constructs", () => {
    expect(scan("const a = 2 ** 53; const b = 2 ** -53; const c = x ** 2; let d = 3; d **= 2;")).toEqual([]);
    expect(
      scan(
        "const y = Math.floor(x) + Math.min(a, b) + Math.max(a, b) + Math.abs(x) + Math.sqrt(x) + Math.imul(1, 2) + Math.fround(x) + Math.trunc(x);",
      ),
    ).toEqual([]);
    expect(scan("// Math.exp in a comment\nconst s = 'Math.log(x)';")).toEqual([]);
  });

  it("FR-007-06 · reports the line of each finding", () => {
    const f = scan("const a = 1;\nconst b = Math.exp(a);\n\nconst c = a ** 0.5;", "x.ts");
    expect(f).toEqual(["x.ts:2: Math.exp", "x.ts:4: ** with a non-integer or non-literal exponent"]);
  });
});

describe("the engine modules", () => {
  it("FR-007-06 · the random and DES modules exist", () => {
    const names = sources(join(ENGINES, "random")).map((p) => p.split(/[\\/]/).pop());
    expect(names).toEqual(expect.arrayContaining(["philox.ts", "variates.ts"]));
    expect(sources(join(ENGINES, "des")).length).toBeGreaterThanOrEqual(3);
  });

  it("FR-007-06 · no variate or DES module calls a transcendental function or raises to a non-integer power", () => {
    const files = [...sources(join(ENGINES, "random")), ...sources(join(ENGINES, "des"))];
    expect(files.length).toBeGreaterThanOrEqual(5);
    const violations = files.flatMap((f) => scan(readFileSync(f, "utf-8"), f.slice(ENGINES.length + 1)));
    expect(violations).toEqual([]);
  });
});
