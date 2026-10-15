// FR-018-66, FR-018-67, FR-000-15: the CI mislabel check. An artefact or engine labelled live whose measurements give
// replay, or a live subject without a measurement, fails the web build and is named. The gate mirrors
// web/src/lane/derive.ts (thresholds: lane_gate in specs/000-foundation/thresholds.yaml).
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const ok = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0;

function gate(m) {
  if (m === null || typeof m !== "object") return "replay";
  const asset = ok(m.max_asset_bytes) && m.max_asset_bytes <= 25_000_000;
  const time = (ok(m.interaction_ms) && m.interaction_ms <= 16) || (ok(m.run_ms_t2) && m.run_ms_t2 <= 1000);
  const trace = m.trace_bytes === null || (ok(m.trace_bytes) && m.trace_bytes <= 10_000_000);
  return m.web_drivable === true && asset && time && trace ? "live" : "replay";
}

export function checkLanes({ artefacts = [], liveEngines = [], engines = [], measurements } = {}) {
  const violations = [];
  const add = (id, rule, message) => violations.push({ id, rule, message });
  const entries = Array.isArray(measurements?.entries) ? measurements.entries : [];
  const byEngine = new Map();
  const byArtefact = new Map();
  const seen = new Set();
  for (const e of entries) {
    const kind = e && typeof e.engine === "string" ? "engine" : "artefact";
    const id = kind === "engine" ? e.engine : e?.artefact;
    const key = `${kind}:${id}`;
    if (seen.has(key)) {
      if (!violations.some((v) => v.rule === "duplicate-entry" && v.id === id))
        add(id, "duplicate-entry", `${id}: listed more than once in the lane measurements`);
      continue;
    }
    seen.add(key);
    (kind === "engine" ? byEngine : byArtefact).set(id, e.measurements);
  }
  const known = new Set(artefacts.map((a) => a.id));
  for (const id of byArtefact.keys())
    if (!known.has(id)) add(id, "unknown-artefact", `${id}: measured, but not in the web manifest`);
  for (const id of engines)
    if (!byEngine.has(id)) add(id, "engine-not-measured", `${id}: engine without a lane measurement`);
  const live = [
    ...liveEngines.map((id) => ({ id, map: byEngine })),
    ...artefacts.filter((a) => a.lane === "live").map((a) => ({ id: a.id, map: byArtefact })),
  ];
  for (const { id, map, what } of live) {
    if (!map.has(id)) {
      add(id, "unmeasured", `${id}: labelled live but has no measurement`);
    } else if (gate(map.get(id)) !== "live") {
      add(id, "mislabel", `${id}: labelled live but its measurements give replay`);
    }
  }
  return { ok: violations.length === 0, violations };
}

function readJson(file, what) {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    throw new Error(`${file}: cannot read the ${what}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${file}: the ${what} is not valid JSON`);
  }
}

export function main(argv) {
  const opt = {};
  for (let i = 0; i < argv.length; i += 2) {
    if (!argv[i]?.startsWith("--") || argv[i + 1] === undefined) {
      console.error(
        "usage: check-lanes.mjs --manifest <web manifest> --measurements <lane measurements> [--engines a,b] [--live-engines a,b]",
      );
      return 2;
    }
    opt[argv[i].slice(2)] = argv[i + 1];
  }
  if (!opt.manifest || !opt.measurements) {
    console.error(
      "usage: check-lanes.mjs --manifest <web manifest> --measurements <lane measurements> [--engines a,b] [--live-engines a,b]",
    );
    return 2;
  }
  try {
    const manifest = readJson(opt.manifest, "web manifest");
    const arts = Array.isArray(manifest) ? manifest : manifest?.artefacts;
    if (!Array.isArray(arts)) throw new Error(`${opt.manifest}: the web manifest has no artefacts array`);
    const measurements = readJson(opt.measurements, "measurement file");
    if (!Array.isArray(measurements?.entries) || measurements.entries.length === 0)
      throw new Error(`${opt.measurements}: the measurement file has no non-empty entries array`);
    const list = (s) => (s ? s.split(",").filter(Boolean) : []);
    const r = checkLanes({
      artefacts: arts,
      liveEngines: list(opt["live-engines"]),
      engines: list(opt.engines),
      measurements,
    });
    for (const v of r.violations) console.error(`${v.rule}: ${v.message}`);
    return r.ok ? 0 : 1;
  } catch (e) {
    console.error(e.message);
    return 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href)
  process.exitCode = main(process.argv.slice(2));
