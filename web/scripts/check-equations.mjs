// Parses every `$$` display block of the theory pages (EN and ES) with KaTeX and fails the build on an equation that does
// not parse (FR-020-03).
//
//   node scripts/check-equations.mjs [--root DIR]      (default: the repository root)
//
// Prints "<file>:<line>: <message>" for each block that KaTeX rejects (`throwOnError: true`), the file relative to DIR and the
// line of the opening `$$`. Exit 0 = every equation parses, 1 = at least one does not, 2 = usage error or unreadable root.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import katex from "katex";

const HERE = dirname(fileURLToPath(import.meta.url));

class UsageError extends Error {}

/** The `$$` display blocks of an MDX text, outside code fences: { line, tex }, `line` 1-based at the opening `$$`. */
export function displayBlocks(text) {
  const blocks = [];
  let fence = false;
  let open = null;
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (open === null && /^\s*(```|~~~)/.test(line)) {
      fence = !fence;
      continue;
    }
    if (fence) continue;
    if (open === null) {
      if (line.trim() === "$$") open = { line: i + 1, body: [] };
    } else if (/^\s*\$\$\s*(\{#[^}]*\})?\s*$/.test(line)) {
      blocks.push({ line: open.line, tex: open.body.join("\n") });
      open = null;
    } else open.body.push(line);
  }
  return blocks;
}

/** The findings ("file:line: message") of one MDX file. */
export function checkFile(path, label) {
  const out = [];
  for (const { line, tex } of displayBlocks(readFileSync(path, "utf8"))) {
    try {
      katex.renderToString(tex, { throwOnError: true, displayMode: true, strict: "ignore" });
    } catch (e) {
      out.push(`${label}:${line}: ${String(e.message).split("\n")[0]}`);
    }
  }
  return out;
}

function main(argv) {
  let root = resolve(HERE, "..", "..");
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--root" && argv[i + 1] !== undefined) root = resolve(argv[++i]);
    else throw new UsageError(`unknown or incomplete argument: ${argv[i]}`);
  }
  if (!existsSync(root) || !statSync(root).isDirectory()) throw new UsageError(`${root} is not a directory`);
  const findings = [];
  for (const lang of ["en", "es"]) {
    const dir = join(root, "web", "src", "content", "theory", lang);
    if (!existsSync(dir)) continue;
    for (const name of readdirSync(dir).filter((f) => f.endsWith(".mdx")).sort()) {
      const file = join(dir, name);
      findings.push(...checkFile(file, relative(root, file).split("\\").join("/")));
    }
  }
  for (const line of findings) console.log(line);
  return findings.length === 0 ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (e) {
    if (!(e instanceof UsageError)) throw e;
    console.error(`check-equations: ${e.message}`);
    process.exitCode = 2;
  }
}
