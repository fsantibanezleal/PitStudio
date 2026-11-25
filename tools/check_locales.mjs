// Locale and JSX checks of the web app (FR-020-45, FR-000-03), run from the `check` script of web/package.json.
//
//   node tools/check_locales.mjs [--locales <dir>] [--src <dir>]     (defaults: web/src/locales and web/src)
//
// 1. Key parity: every namespace file `<lang>/<ns>.json` of English and Spanish has the same leaf keys, the same
//    {{placeholder}} names, and no empty or non-string value.
// 2. No text literal in JSX: a component takes every visible string from the locale files. The check parses the sources
//    with @babel/parser (a dependency of web/, resolved from there) and reports JSX text and string expressions that
//    contain a letter or a digit; attributes, separators such as " · " and `t("key")` calls are fine.
//
// Plain ESM with no top-level await, so tests can load it with Node's require(esm). Exit 0 = clean, 1 = violations.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(import.meta.url);
const ROOT = resolve(dirname(SCRIPT), "..");
const LETTER_OR_DIGIT = /[\p{L}\p{N}]/u;
const PLACEHOLDER = /\{\{\s*([^\s,}]+)[^}]*\}\}/g;

function violation(kind, file, detail, extra = {}) {
  return { kind, file, ...extra, message: `${file}: ${kind}${detail ? ` ${detail}` : ""}` };
}

// ---------------------------------------------------------------------------------------------------------------
// Locale files
// ---------------------------------------------------------------------------------------------------------------
function isBranch(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Leaf values by key path. Own enumerable keys only; `__proto__` is an ordinary key; a Map keeps it harmless. */
function leaves(object, prefix = "", out = new Map()) {
  for (const key of Object.keys(object)) {
    const path = prefix ? `${prefix}.${key}` : key;
    const value = Object.getOwnPropertyDescriptor(object, key)?.value;
    if (isBranch(value)) leaves(value, path, out);
    else out.set(path, value);
  }
  return out;
}

function placeholders(text) {
  return new Set([...text.matchAll(PLACEHOLDER)].map((m) => m[1]));
}

function sameSet(a, b) {
  return a.size === b.size && [...a].every((x) => b.has(x));
}

export function compareLocaleObjects(en, es, file) {
  const out = [];
  const a = leaves(en);
  const b = leaves(es);
  for (const key of a.keys()) {
    if (!b.has(key)) out.push(violation("missing-in-es", file, `"${key}"`, { key }));
  }
  for (const key of b.keys()) {
    if (!a.has(key)) out.push(violation("missing-in-en", file, `"${key}"`, { key }));
  }
  for (const [key, x] of a) {
    if (!b.has(key)) continue;
    const y = b.get(key);
    if (typeof x !== "string" || typeof y !== "string") {
      out.push(violation("not-a-string", file, `"${key}"`, { key }));
    } else if (x.trim() === "" || y.trim() === "") {
      out.push(violation("empty-value", file, `"${key}"`, { key }));
    } else if (!sameSet(placeholders(x), placeholders(y))) {
      out.push(violation("placeholder-mismatch", file, `"${key}"`, { key }));
    }
  }
  return out;
}

function namespaces(dir) {
  if (!existsSync(dir)) return new Map();
  return new Map(
    readdirSync(dir)
      .filter((name) => name.endsWith(".json"))
      .map((name) => [name.slice(0, -5), join(dir, name)]),
  );
}

export function checkLocaleDir(dir) {
  const out = [];
  const en = namespaces(join(dir, "en"));
  const es = namespaces(join(dir, "es"));
  for (const ns of new Set([...en.keys(), ...es.keys()])) {
    const enPath = en.get(ns);
    const esPath = es.get(ns);
    if (!esPath) {
      out.push(violation("namespace-missing-in-es", `${ns}.json`, `(only ${enPath} exists)`));
      continue;
    }
    if (!enPath) {
      out.push(violation("namespace-missing-in-en", `${ns}.json`, `(only ${esPath} exists)`));
      continue;
    }
    let ok = true;
    const parsed = [enPath, esPath].map((path) => {
      try {
        return JSON.parse(readFileSync(path, "utf8"));
      } catch (error) {
        ok = false;
        out.push(violation("invalid-json", `${ns}.json`, `(${path}: ${error.message})`));
        return null;
      }
    });
    if (ok && isBranch(parsed[0]) && isBranch(parsed[1])) {
      out.push(...compareLocaleObjects(parsed[0], parsed[1], `${ns}.json`));
    }
  }
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// JSX text literals
// ---------------------------------------------------------------------------------------------------------------
let babel = null;
function parser() {
  if (!babel) {
    try {
      babel = createRequire(join(ROOT, "web", "package.json"))("@babel/parser");
    } catch (error) {
      throw new Error(`check_locales: @babel/parser is missing (run "pnpm install" in web/): ${error.message}`);
    }
  }
  return babel;
}

function parse(source) {
  return parser().parse(source, {
    sourceType: "module",
    plugins: ["jsx", "typescript"],
    errorRecovery: true,
  });
}

/** Line of the first letter or digit of a JSX text node (the node itself starts at the preceding tag). */
function textLine(node) {
  const text = node.value;
  const at = text.search(LETTER_OR_DIGIT);
  const before = at < 0 ? "" : text.slice(0, at);
  return node.loc.start.line + (before.match(/\n/g)?.length ?? 0);
}

function literalOf(expression) {
  if (expression.type === "StringLiteral") return expression.value;
  if (expression.type === "TemplateLiteral") return expression.quasis.map((q) => q.value.cooked ?? "").join("");
  return null;
}

function snippet(text) {
  const one = text.replace(/\s+/g, " ").trim();
  return one.length > 40 ? `${one.slice(0, 37)}...` : one;
}

export function findJsxTextLiterals(source, file) {
  let ast;
  try {
    ast = parse(source);
  } catch {
    return [];
  }
  const out = [];
  const report = (line, text) =>
    out.push(
      violation("jsx-text-literal", file, `line ${line}: "${snippet(text)}" (use t("key") and a locale file)`, {
        line,
      }),
    );

  const visit = (node) => {
    if (Array.isArray(node)) {
      for (const item of node) visit(item);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    if (node.type === "JSXElement" || node.type === "JSXFragment") {
      for (const child of node.children) {
        if (child.type === "JSXText" && LETTER_OR_DIGIT.test(child.value)) {
          report(textLine(child), child.value);
        } else if (child.type === "JSXExpressionContainer") {
          const text = literalOf(child.expression);
          if (text !== null && LETTER_OR_DIGIT.test(text)) report(child.loc.start.line, text);
        }
      }
    }
    for (const key of Object.keys(node)) {
      if (key === "loc" || key === "extra" || key === "leadingComments" || key === "trailingComments") continue;
      visit(node[key]);
    }
  };
  visit(ast.program);
  return out.sort((x, y) => x.line - y.line);
}

function tsxFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "test-support" || entry.name === "node_modules") continue;
      out.push(...tsxFiles(path));
    } else if (entry.name.endsWith(".tsx") && !/\.(test|spec)\.tsx$/.test(entry.name)) {
      out.push(path);
    }
  }
  return out;
}

export function checkJsxSources(dir) {
  if (!existsSync(dir)) return [];
  return tsxFiles(dir)
    .sort()
    .flatMap((path) => findJsxTextLiterals(readFileSync(path, "utf8"), relative(process.cwd(), path) || path));
}

// ---------------------------------------------------------------------------------------------------------------
// Command line
// ---------------------------------------------------------------------------------------------------------------
function main(argv) {
  const args = { locales: join(ROOT, "web", "src", "locales"), src: join(ROOT, "web", "src") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--locales" && argv[i + 1]) args.locales = resolve(argv[++i]);
    else if (argv[i] === "--src" && argv[i + 1]) args.src = resolve(argv[++i]);
    else {
      console.error(`check_locales: unknown argument ${argv[i]}`);
      return 2;
    }
  }
  const found = [...checkLocaleDir(args.locales), ...checkJsxSources(args.src)];
  for (const v of found) console.log(v.message);
  return found.length > 0 ? 1 : 0;
}

if (process.argv[1] && resolve(process.argv[1]) === SCRIPT) {
  process.exitCode = main(process.argv.slice(2));
}
