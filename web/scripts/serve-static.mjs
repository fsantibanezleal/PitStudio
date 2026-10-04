// Serves build/client the way GitHub Pages does, under BASE_PATH: files as-is, `dir/` → `dir/index.html`,
// `dir` → 301 to `dir/`, `name` → `name.html`, anything else → 404.html with status 404.
// Used by the E2E tests; no dependencies.
import { existsSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize, resolve, sep } from "node:path";

const ROOT = resolve("build/client");
const BASE = process.env.BASE_PATH ?? "/";
const PORT = Number(process.env.PORT ?? 4173);
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
  ".wasm": "application/wasm",
  ".mp4": "video/mp4",
  ".webm": "video/webm",
};

const isFile = (p) => existsSync(p) && statSync(p).isFile();

function send(res, status, file) {
  res.writeHead(status, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" });
  res.end(readFileSync(file));
}

createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost");
  const notFound = () => send(res, 404, join(ROOT, "404.html"));
  if (!url.pathname.startsWith(BASE) && `${url.pathname}/` !== BASE) return notFound();
  let rel;
  try {
    rel = decodeURIComponent(url.pathname.slice(BASE.length));
  } catch {
    return notFound();
  }
  const target = normalize(join(ROOT, rel));
  if (target !== ROOT && !target.startsWith(ROOT + sep)) return notFound();
  if (isFile(target)) return send(res, 200, target);
  if (existsSync(target) && statSync(target).isDirectory()) {
    if (!url.pathname.endsWith("/")) {
      res.writeHead(301, { location: `${url.pathname}/${url.search}` });
      return res.end();
    }
    if (isFile(join(target, "index.html"))) return send(res, 200, join(target, "index.html"));
  }
  if (isFile(`${target}.html`)) return send(res, 200, `${target}.html`);
  return notFound();
}).listen(PORT, () => console.log(`serving ${ROOT} at http://localhost:${PORT}${BASE}`));
