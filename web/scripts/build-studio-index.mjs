// Build the studio index (DC-019-03, spec 019): the join of the tool registry, the tool map, the locks, the capability
// report, the web manifest and the published run cards, written as
//   web/public/studio/index.json            the studio index (checked against its byte cap, FR-019-47)
//   web/public/studio/runs.json             one slim card per published run (ledger, loop); the full cards stay under assets/runs/
//   web/src/studio/generated/studio-data.json   the 20 registry entries and the index, imported by the studio routes
//
//   node scripts/build-studio-index.mjs        (pnpm build:studio-index)
//
// Environment:
//   STUDIO_RUNS_DIR   a folder whose sub-folders are copied to public/assets/runs/ first (the E2E fixture runs); they are
//                     removed again at the next run of this script, so they never stay in the tree
//   STUDIO_RELEASE=1  a release build: a version that cannot be resolved fails the build (FR-019-10) and a run card
//                     marked `fixture: true` is left out (FR-019-48); a development build records the version as
//                     "unresolved" with a warning naming the tool, and keeps fixture runs, labelled
//   STUDIO_PYTHON     the Python interpreter that runs tools/resolve_versions.py and tools/check_showcase.py
//
// Exit: 0 written, 1 a build rule failed (the message names the file and the JSON pointer or the tool), 2 usage or unreadable input.
import { spawnSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parse as parseYaml } from "yaml";
import { deriveEdges, joinArtefacts, layoutTools } from "../src/studio/buildIndex.ts";
import { parseStudioIndex } from "../src/studio/loadIndex.ts";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(WEB, "..");
const PUBLIC = join(WEB, "public");
const RUNS = join(PUBLIC, "assets", "runs");
const STAGED = join(WEB, ".studio-staged.json");
const MANIFEST = join(PUBLIC, "assets", "manifest.json");
const RELEASE = process.env.STUDIO_RELEASE === "1";
const RUN_CARD_CAP = 200_000;
const TELEMETRY_CAP = 200_000;

const LANES = new Set(["live", "replay", "local-only"]);
const RINGS = new Set(["Adopt", "Trial", "Assess", "Hold"]);
const STATUSES = new Set(["not-yet-run", "done", "evaluated-not-adopted"]);
const LICENCES = new Set([
  "public-domain",
  "open-no-attribution",
  "own",
  "attribution",
  "share-alike",
  "display-only",
  "reference-only",
]);
const BANDS = ["scene", "physics", "sensors-synthetic-data", "training", "acceleration", "encoding", "web"];
const KINDS = new Set([
  "video",
  "image",
  "figure",
  "point-cloud",
  "mesh",
  "tiles",
  "splat",
  "onnx",
  "table",
  "trace",
  "shard",
  "field",
  "text",
  "model-card",
  "telemetry",
  "usd",
]);
const LOCKS = new Set([
  "uv.lock",
  "studio/uv.lock",
  "studio/isaac/uv.lock",
  "studio/rtx/uv.lock",
  "studio/isaaclab/uv.lock",
  "pipeline/uv.lock",
  "pipeline/accel/uv.lock",
  "web/pnpm-lock.yaml",
]);

class BuildError extends Error {}
const fail = (message) => {
  throw new BuildError(message);
};

function readText(path) {
  try {
    return readFileSync(path, "utf8");
  } catch (error) {
    console.error(`build-studio-index: cannot read ${path}: ${error.message}`);
    process.exit(2);
  }
}

function readJson(path, what) {
  try {
    return JSON.parse(readText(path));
  } catch (error) {
    if (error instanceof BuildError) throw error;
    return fail(`${what}: ${path} is not valid JSON (${error.message})`);
  }
}

function python() {
  const candidates = [
    process.env.STUDIO_PYTHON,
    join(REPO, ".venv", "Scripts", "python.exe"),
    join(REPO, ".venv", "bin", "python"),
    "python3",
    "python",
  ].filter(Boolean);
  for (const exe of candidates) {
    const probe = spawnSync(exe, ["-c", "import yaml"], { encoding: "utf8" });
    if (probe.status === 0) return exe;
  }
  return (
    console.error("build-studio-index: no Python with PyYAML found (set STUDIO_PYTHON)") ?? process.exit(2)
  );
}

// --- runs: stage the fixture runs, read the published run cards ---------------------------------------------------
function stageFixtures() {
  mkdirSync(RUNS, { recursive: true });
  if (existsSync(STAGED)) {
    const staged = JSON.parse(readFileSync(STAGED, "utf8"));
    for (const id of staged.runs) rmSync(join(RUNS, id), { recursive: true, force: true });
    if (staged.manifest) rmSync(MANIFEST, { force: true });
    rmSync(STAGED, { force: true });
  }
  const staged = { runs: [], manifest: false };
  // Nothing is published until `studio publish` writes the web manifest: the build then serves an empty one, which is
  // what the pages already read as "nothing published", so the honesty checks run on a real (empty) manifest.
  if (!existsSync(MANIFEST)) {
    writeFileSync(
      MANIFEST,
      `${JSON.stringify({ kind: "web-index", artefacts: [] })}
`,
    );
    staged.manifest = true;
  }
  const dir = process.env.STUDIO_RUNS_DIR;
  if (dir) {
    const source = resolve(WEB, dir);
    for (const d of readdirSync(source, { withFileTypes: true })) {
      if (!d.isDirectory()) continue;
      if (existsSync(join(RUNS, d.name)))
        fail(`STUDIO_RUNS_DIR: run ${d.name} is already published under public/assets/runs`);
      cpSync(join(source, d.name), join(RUNS, d.name), { recursive: true });
      staged.runs.push(d.name);
    }
  }
  writeFileSync(
    STAGED,
    `${JSON.stringify(staged)}
`,
  );
}

function readRuns() {
  const out = [];
  if (!existsSync(RUNS)) return out;
  for (const entry of readdirSync(RUNS, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const manifest = join(RUNS, entry.name, "manifest.json");
    if (!existsSync(manifest)) continue;
    const rel = `web/public/assets/runs/${entry.name}/manifest.json`;
    const size = statSync(manifest).size;
    if (size > RUN_CARD_CAP)
      fail(`${rel}: the run card has ${size} bytes, above the cap of ${RUN_CARD_CAP} (/)`);
    const card = readJson(manifest, rel);
    if (card?.kind !== "run" || card.run_id !== entry.name)
      fail(`${rel}: not a run card of this folder (/run_id)`);
    if (!Array.isArray(card.stages) || !Array.isArray(card.artefacts))
      fail(`${rel}: stages or artefacts missing (/stages)`);
    const telemetry = join(RUNS, entry.name, "telemetry.json");
    if (existsSync(telemetry)) {
      const tsize = statSync(telemetry).size;
      const trel = rel.replace("manifest.json", "telemetry.json");
      if (tsize > TELEMETRY_CAP)
        fail(`${trel}: the telemetry has ${tsize} bytes, above the cap of ${TELEMETRY_CAP} (/)`);
      const t = readJson(telemetry, trel);
      for (const [i, s] of (t.stages ?? []).entries()) {
        const names = new Set((s.points ?? []).flatMap((p) => Object.keys(p)));
        for (const p of s.points ?? [])
          for (const name of names)
            if (name in p && p[name] !== null && !Number.isFinite(p[name]))
              fail(`${trel}: a non-finite number at /stages/${i}/points (${name})`);
      }
    }
    if (card.published !== true) continue;
    if (RELEASE && card.fixture === true) continue;
    out.push(card);
  }
  return out.sort((a, b) => (a.run_id < b.run_id ? -1 : 1));
}

function slim(card) {
  const tools = new Set([...card.stages.map((s) => s.tool), ...card.artefacts.map((a) => a.producer?.tool)]);
  return {
    run_id: card.run_id,
    created: card.created,
    published: true,
    ...(card.stale === true ? { stale: true } : {}),
    ...(card.fixture === true ? { fixture: true } : {}),
    gpu: card.gpu ?? null,
    stages: card.stages.map((s) => ({
      key: s.key,
      tool: s.tool,
      performance: s.performance,
      status: s.status,
      determinism: s.determinism ? { class: s.determinism.class } : undefined,
    })),
    artefacts: card.artefacts.map((a) => ({ id: a.id, producer: a.producer, cases: a.cases ?? [] })),
    tools: [...tools].filter(Boolean).sort(),
  };
}

// --- registry and tool map -----------------------------------------------------------------------------------------
function readRegistry() {
  const doc = parseYaml(readText(join(REPO, "studio", "tools.yaml")));
  const all = doc?.tools;
  if (!Array.isArray(all)) fail("studio/tools.yaml: no tools list (/tools)");
  const seen = new Set();
  for (const [i, t] of all.entries()) {
    const at = `studio/tools.yaml: /tools/${i}`;
    if (seen.has(t.id)) fail(`${at}/id: duplicate id ${t.id}`);
    seen.add(t.id);
    if (!LANES.has(t.lane)) fail(`${at}/lane: unknown lane ${JSON.stringify(t.lane)} (${t.id})`);
    if (!RINGS.has(t.ring)) fail(`${at}/ring: unknown ring ${JSON.stringify(t.ring)} (${t.id})`);
    if (!STATUSES.has(t.status)) fail(`${at}/status: unknown status ${JSON.stringify(t.status)} (${t.id})`);
    if (!LICENCES.has(t.licence_class))
      fail(`${at}/licence_class: unknown licence class ${JSON.stringify(t.licence_class)} (${t.id})`);
  }
  return all.filter((t) => t.category === "studio-tool");
}

function readToolmap(tools) {
  const map = parseYaml(readText(join(REPO, "studio", "toolmap.yaml")));
  const ids = new Set(tools.map((t) => t.id));
  if (!Array.isArray(map?.bands) || !Array.isArray(map?.edges))
    fail("studio/toolmap.yaml: bands or edges missing (/)");
  if (JSON.stringify(map.bands.map((b) => b.id)) !== JSON.stringify(BANDS))
    fail(`studio/toolmap.yaml: the bands must be ${BANDS.join(", ")} in this order (/bands)`);
  const placed = new Set();
  for (const [b, band] of map.bands.entries())
    for (const id of band.tools) {
      if (!ids.has(id)) fail(`studio/toolmap.yaml: unknown tool ${id} (/bands/${b}/tools)`);
      if (placed.has(id)) fail(`studio/toolmap.yaml: ${id} is placed twice (/bands/${b}/tools)`);
      placed.add(id);
    }
  for (const id of ids) if (!placed.has(id)) fail(`studio/toolmap.yaml: ${id} is in no band (/bands)`);
  for (const [i, e] of map.edges.entries()) {
    if (e.from === e.to) fail(`studio/toolmap.yaml: ${e.from}: an edge from a tool to itself (/edges/${i})`);
    if (!ids.has(e.from) || !ids.has(e.to))
      fail(`studio/toolmap.yaml: edge to an unknown tool (/edges/${i})`);
    if (!KINDS.has(e.kind))
      fail(`studio/toolmap.yaml: unknown artefact kind ${JSON.stringify(e.kind)} (/edges/${i}/kind)`);
  }
  return map;
}

// --- versions, probes, honesty -------------------------------------------------------------------------------------
const RESOLVE = `
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "tools"))
import resolve_versions as r, yaml
root = Path(sys.argv[1])
tools = yaml.safe_load((root / "studio" / "tools.yaml").read_text(encoding="utf-8"))["tools"]
out = {}
for e in tools:
    try:
        v = r.resolve_entry(e, root)
        out[e["id"]] = {"version": v.version, "release_date": v.release_date}
    except r.VersionError as x:
        out[e["id"]] = {"error": str(x)}
print(json.dumps(out))
`;

function resolveVersions(py, tools) {
  const run = spawnSync(py, ["-c", RESOLVE, REPO], { encoding: "utf8" });
  if (run.status !== 0) {
    console.error(`build-studio-index: version resolution failed: ${run.stderr}`);
    process.exit(2);
  }
  const resolved = JSON.parse(run.stdout);
  const unresolved = [];
  const out = {};
  for (const t of tools) {
    const ref = t.version ?? {};
    const r = resolved[t.id] ?? { error: `${t.id}: no result` };
    const from =
      "from_lock" in ref
        ? "lock"
        : "from_binary" in ref
          ? "binary"
          : "from_git_tag" in ref
            ? "git-tag"
            : "own";
    if (r.error) {
      unresolved.push(r.error);
      out[t.id] = { value: "unresolved", release_date: null, from: from === "lock" ? "own" : from };
      continue;
    }
    const version = { value: r.version, release_date: r.release_date ?? null, from };
    if (from === "lock") {
      if (!LOCKS.has(ref.from_lock))
        fail(`studio/tools.yaml: ${t.id}: ${ref.from_lock} is not a known lock file`);
      version.lock = ref.from_lock;
    }
    out[t.id] = version;
  }
  if (unresolved.length > 0) {
    for (const line of unresolved)
      console.warn(`build-studio-index: ${RELEASE ? "error" : "warning"}: ${line}`);
    if (RELEASE)
      fail(`${unresolved.length} tool version(s) cannot be resolved (FR-019-10): ${unresolved.join("; ")}`);
  }
  return out;
}

/** The probe of the tool: the capability probe that names the tool's package or id, else "not probed". */
const PROBE_OF = {
  warp: "warp_newton",
  newton: "warp_newton",
  "mujoco-warp": "warp_newton",
  pytorch: "torch_ort",
  "onnx-runtime": "torch_ort",
  tensorrt: "tensorrt",
  "nvenc-ffmpeg": "nvenc",
  ovrtx: "ovrtx",
  "isaac-sim-replicator": "isaacsim",
  "isaac-lab": "isaaclab",
};

function probeOf(capabilities, id, performance) {
  const name = PROBE_OF[id];
  const probe = name ? capabilities.probes?.[name] : undefined;
  if (!probe || typeof probe !== "object") return { status: "not-probed" };
  const status = ["pass", "fail", "skip"].includes(probe.status) ? probe.status : "not-probed";
  if (status === "not-probed") return { status };
  const entry = {
    status,
    name,
    date: String(capabilities.generated ?? "").slice(0, 10),
    gpu: String(capabilities.gpu ?? "unknown"),
    driver: String(capabilities.driver ?? "0"),
  };
  if (status === "fail") entry.error = String(probe.error ?? "the probe failed").slice(0, 300);
  if (status === "pass" && probe.metrics && typeof probe.metrics === "object") {
    if (performance === "local-only") entry.metrics = "measured locally, not published (licence)";
    else {
      const metrics = Object.fromEntries(
        Object.entries(probe.metrics).filter(
          ([k, v]) => typeof v === "number" && Number.isFinite(v) && /^[a-z][a-z0-9_]{0,63}$/.test(k),
        ),
      );
      if (Object.keys(metrics).length > 0) entry.metrics = metrics;
    }
  }
  return entry;
}

const CHECKS = [
  "done-needs-artefact",
  "not-yet-run-has-artefact",
  "outputs-only",
  "our-scenes",
  "local-only-scrub",
  "file-guards",
];

function honestyChecks(py) {
  const run = spawnSync(py, [join(REPO, "tools", "check_showcase.py"), "--root", REPO], { encoding: "utf8" });
  if (run.status === 2) {
    console.error(`build-studio-index: check_showcase could not run: ${run.stdout}${run.stderr}`);
    process.exit(2);
  }
  const lines = run.stdout.split("\n").filter(Boolean);
  return CHECKS.map((id) => {
    const mine = lines.filter((l) => l.startsWith(`${id}:`));
    const violations = mine.map((line) => {
      const [, subject = "", ...rest] = line.split(": ");
      const message = (rest.join(": ") || line).slice(0, 300);
      const key =
        id === "done-needs-artefact" || id === "not-yet-run-has-artefact"
          ? "tool"
          : id === "outputs-only" || id === "our-scenes"
            ? "artefact"
            : "file";
      return { message, [key]: subject.trim() || "unknown" };
    });
    return { id, status: violations.length === 0 ? "pass" : "fail", violations };
  });
}

function gitSha() {
  const fromEnv = process.env.GITHUB_SHA;
  if (fromEnv && /^[0-9a-f]{40}$/.test(fromEnv)) return fromEnv;
  const run = spawnSync("git", ["rev-parse", "HEAD"], { cwd: REPO, encoding: "utf8" });
  const sha = run.stdout.trim();
  return /^[0-9a-f]{40}$/.test(sha) ? sha : "0".repeat(40);
}

function main() {
  stageFixtures();
  const runs = readRuns();
  const tools = readRegistry();
  const toolmap = readToolmap(tools);
  const py = python();
  const versions = resolveVersions(py, tools);
  const capabilities = readJson(join(REPO, "studio", "capabilities.json"), "studio/capabilities.json");

  const manifest = readJson(MANIFEST, "web/public/assets/manifest.json");
  // Fixture runs are not artefacts of their tool (FR-019-48): only the web manifest counts.
  const artefacts = Array.isArray(manifest.artefacts) ? manifest.artefacts : [];

  const layout = layoutTools(toolmap, tools);
  const joined = joinArtefacts(
    tools.map((t) => t.id),
    artefacts,
  );
  const indexTools = tools.map((t) => ({
    id: t.id,
    position: layout[t.id],
    version: versions[t.id],
    probe: probeOf(capabilities, t.id, t.performance),
    artefacts: joined[t.id] ?? [],
  }));
  const adopted = tools.filter((t) => t.status !== "evaluated-not-adopted");
  const missing = adopted.filter((t) => (joined[t.id] ?? []).length === 0).map((t) => t.id);
  const index = {
    schema_version: "1.0",
    git_sha: gitSha(),
    tools: indexTools,
    edges: deriveEdges(toolmap.edges, artefacts),
    honesty: {
      checks: honestyChecks(py),
      definition_of_done: {
        studio_tools: adopted.length,
        satisfied: adopted.length - missing.length,
        missing,
        met: missing.length === 0,
      },
    },
  };

  const text = `${JSON.stringify(index)}\n`;
  parseStudioIndex(text); // throws above the cap of FR-019-47
  mkdirSync(join(PUBLIC, "studio"), { recursive: true });
  writeFileSync(join(PUBLIC, "studio", "index.json"), text);
  writeFileSync(join(PUBLIC, "studio", "runs.json"), `${JSON.stringify(runs.map(slim))}\n`);
  const generated = join(WEB, "src", "studio", "generated");
  mkdirSync(generated, { recursive: true });
  const registry = tools.map((t) => ({
    id: t.id,
    name: t.name,
    category: t.category,
    envs: t.envs,
    spdx: t.spdx,
    licence_class: t.licence_class,
    ring: t.ring,
    lane: t.lane,
    performance: t.performance,
    role: t.role,
    cases: t.cases ?? [],
    status: t.status,
    ...(t.reason ? { reason: t.reason } : {}),
    ...(t.docs_page ? { docs_page: t.docs_page } : {}),
    ...(t.alternatives_rejected ? { alternatives_rejected: t.alternatives_rejected } : {}),
    ...(t.notice ? { notice: t.notice } : {}),
  }));
  writeFileSync(
    join(generated, "studio-data.json"),
    `${JSON.stringify({ tools: registry, index, run_ids: runs.map((r) => r.run_id) })}\n`,
  );
  console.log(
    `build-studio-index: ${tools.length} tools, ${index.edges.length} edges, ${runs.length} published run(s), ${text.length} bytes` +
      `${RELEASE ? " (release)" : ""}`,
  );
}

try {
  main();
} catch (error) {
  if (error instanceof BuildError || error?.name === "StudioIndexError") {
    console.error(`build-studio-index: ${error.message}`);
    process.exit(1);
  }
  throw error;
}
