// Byte budgets of the built Pages artifact (NFR-020-01, NFR-020-03, NFR-020-04).
//
//   node scripts/budgets.mjs --root build/client
//
// ROOT is a built client tree: prerendered pages `<route>/index.html` (and `index.html`), scripts and assets next to them,
// and `assets/manifest.json` (the web manifest, `artefacts[{ path, bytes, budget_class }]`, `path` relative to ROOT/assets/).
// One line "<rule>: <subject>: <detail>" per violation; exit 0 when there is none, 1 with violations, 2 on a usage error or
// an unreadable root or manifest (a message on stderr, no stack trace).
//
// Rules
//   initial-js    the gzip size of every `.js` file a page references by a `src` or `href` of its HTML is at most 200,000 bytes
//                 (inclusive), page by page, every prerendered route, dynamic templates included; a script shared by two
//                 pages counts for each; references to other origins and non-script links are not counted.
//   class-budget  the size on disk of the files of a budget class is at most its cap (MB = 10^6, inclusive). A file listed
//                 in the manifest belongs to its `budget_class`; a file the manifest does not list, and every file outside
//                 `assets/` (scripts, styles, pages, fonts), counts as own code.
//   total-budget  the whole artifact is at most 500,000,000 bytes.
//   katex-js      no script holds KaTeX JavaScript (equations are rendered at build time): a script whose text contains
//                 "KaTeX parse error".
//   katex-css     a page links a KaTeX stylesheet or font exactly when its HTML contains `class="katex`.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { gzipSync } from "node:zlib";

export const INITIAL_JS_BUDGET = 200_000;
export const CLASS_CAPS = {
  videos: 150_000_000,
  "tiles-glb": 95_000_000,
  "shards-clouds": 60_000_000,
  splats: 25_000_000,
  onnx: 80_000_000,
  runtimes: 55_000_000,
  "own-code": 10_000_000,
  "studio-showcase": 25_000_000,
};
export const TOTAL_CAP = 500_000_000;

class UsageError extends Error {}

function walk(dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else out.push({ path: p, bytes: st.size });
  }
  return out;
}

const posix = (root, p) => relative(root, p).split(sep).join("/");

/** The file a page URL names under ROOT, trying the path with and without the leading base segments of a Pages URL. */
function resolveUrl(root, url) {
  if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith("//")) return null;
  const clean = url.split(/[?#]/)[0].replace(/^\/+/, "");
  const parts = clean.split("/");
  for (let i = 0; i < parts.length; i++) {
    const candidate = resolve(root, ...parts.slice(i));
    if (candidate.startsWith(root + sep) && existsSync(candidate) && statSync(candidate).isFile())
      return candidate;
  }
  return null;
}

function check(root) {
  const findings = [];
  const files = walk(root);
  const pages = files.filter(
    (f) => f.path.endsWith(`${sep}index.html`) || f.path === join(root, "index.html"),
  );

  // initial-js and katex-css, page by page
  const gz = new Map();
  const gzipOf = (p) => {
    if (!gz.has(p)) gz.set(p, gzipSync(readFileSync(p)).length);
    return gz.get(p);
  };
  for (const page of pages) {
    const route = posix(root, dirname(page.path)) || "/";
    const html = readFileSync(page.path, "utf8");
    const scripts = new Set();
    for (const m of html.matchAll(/\b(?:src|href)\s*=\s*["']([^"']+\.js(?:[?#][^"']*)?)["']/gi)) {
      const file = resolveUrl(root, m[1]);
      if (file) scripts.add(file);
    }
    let total = 0;
    for (const s of scripts) total += gzipOf(s);
    if (total > INITIAL_JS_BUDGET)
      findings.push(
        `initial-js: ${route}: ${total} bytes gzip of ${scripts.size} scripts, at most ${INITIAL_JS_BUDGET}`,
      );

    const needsCss = html.includes('class="katex');
    const linksKatex = [...html.matchAll(/<link\b[^>]*>/gi)].some((m) =>
      /href\s*=\s*["'][^"']*katex/i.test(m[0]),
    );
    if (needsCss && !linksKatex)
      findings.push(`katex-css: ${route}: the page has equations but links no KaTeX stylesheet`);
    if (!needsCss && linksKatex)
      findings.push(`katex-css: ${route}: the page has no equations but links KaTeX files`);
  }

  // katex-js over every script of the tree
  for (const f of files.filter((x) => x.path.endsWith(".js") || x.path.endsWith(".mjs"))) {
    if (readFileSync(f.path, "utf8").includes("KaTeX parse error"))
      findings.push(
        `katex-js: ${posix(root, f.path)}: the script bundles KaTeX; equations are rendered at build`,
      );
  }

  // class budgets
  const manifestFile = join(root, "assets", "manifest.json");
  const classOf = new Map();
  if (existsSync(manifestFile)) {
    let manifest;
    try {
      manifest = JSON.parse(readFileSync(manifestFile, "utf8"));
    } catch (e) {
      throw new UsageError(`assets/manifest.json is not valid JSON: ${e.message}`);
    }
    const assets = join(root, "assets");
    for (const a of Array.isArray(manifest?.artefacts) ? manifest.artefacts : []) {
      const p = resolve(assets, String(a.path));
      if (!p.startsWith(assets + sep)) throw new UsageError(`manifest path leaves assets/: ${a.path}`);
      if (!Object.hasOwn(CLASS_CAPS, a.budget_class))
        throw new UsageError(`manifest entry ${a.path} has an unknown budget_class: ${a.budget_class}`);
      classOf.set(p, a.budget_class);
    }
  }
  const sums = Object.fromEntries(Object.keys(CLASS_CAPS).map((k) => [k, 0]));
  let total = 0;
  for (const f of files) {
    sums[classOf.get(f.path) ?? "own-code"] += f.bytes;
    total += f.bytes;
  }
  for (const [klass, cap] of Object.entries(CLASS_CAPS))
    if (sums[klass] > cap) findings.push(`class-budget: ${klass}: ${sums[klass]} bytes, at most ${cap}`);
  if (total > TOTAL_CAP) findings.push(`total-budget: artifact: ${total} bytes, at most ${TOTAL_CAP}`);
  return findings;
}

function main(argv) {
  let root;
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--root" && argv[i + 1] !== undefined) root = argv[++i];
    else throw new UsageError(`unknown or incomplete argument: ${argv[i]}`);
  }
  if (root === undefined) throw new UsageError("usage: node scripts/budgets.mjs --root <built client tree>");
  const abs = resolve(root);
  if (!existsSync(abs) || !statSync(abs).isDirectory()) throw new UsageError(`${root} is not a directory`);
  const findings = check(abs);
  for (const line of findings) console.log(line);
  return findings.length === 0 ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (e) {
    if (!(e instanceof UsageError)) throw e;
    console.error(`budgets: ${e.message}`);
    process.exitCode = 2;
  }
}
