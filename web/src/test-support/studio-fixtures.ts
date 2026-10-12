// Shared, locked test support for the spec 019 (studio web) tests. Not a test file.
//
// Everything here is hand-built from the committed data contracts, never the output of the code under test:
//   - the tool registry entry shape            : specs/001-contracts/contracts/tools.schema.json (DC-001-03), data-model 001 section 4
//   - the 20 tool ids and their bands            : spec 019 section 7.1 and the valid example of the tool map
//                                                  (specs/019-web-studio/contracts/examples/toolmap.valid.json)
//   - the run card (published run manifest)      : the valid example of DC-001-01 (specs/001-contracts/contracts/examples/manifest.valid.json)
//   - the published telemetry                    : the valid example of DC-002-03 (specs/002-runner/contracts/examples/events.valid-published-telemetry.json)
//   - the studio index                           : the valid example of DC-019-03 (specs/019-web-studio/contracts/examples/studio-index.valid.json)
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { makeArtefact } from "./fixtures";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const readJson = (rel: string): unknown => JSON.parse(readFileSync(resolve(REPO, rel), "utf8"));

export const LICENCE_CLASSES = [
  "public-domain",
  "open-no-attribution",
  "own",
  "attribution",
  "share-alike",
  "display-only",
  "reference-only",
] as const;
export type LicenceClass = (typeof LICENCE_CLASSES)[number];
export const LANES = ["live", "replay", "local-only"] as const;
export const RINGS = ["Adopt", "Trial", "Assess", "Hold"] as const;
export const BAND_IDS = [
  "scene",
  "physics",
  "sensors-synthetic-data",
  "training",
  "acceleration",
  "encoding",
  "web",
] as const;
export type StatusId = "not-yet-run" | "done" | "evaluated-not-adopted";

/** The 17 studio tools and the three evaluated-not-adopted entries (data-model 001 section 4.3), each with its band of the map. */
export const STUDIO_TOOLS: ReadonlyArray<{ id: string; band: (typeof BAND_IDS)[number]; adopted: boolean }> =
  [
    { id: "openusd", band: "scene", adopted: true },
    { id: "kit-usd-composer-explorer", band: "scene", adopted: true },
    { id: "warp", band: "physics", adopted: true },
    { id: "newton", band: "physics", adopted: true },
    { id: "mujoco-warp", band: "physics", adopted: true },
    { id: "physx-ovphysx", band: "physics", adopted: true },
    { id: "ovrtx", band: "sensors-synthetic-data", adopted: true },
    { id: "isaac-sim-replicator", band: "sensors-synthetic-data", adopted: true },
    { id: "pytorch", band: "training", adopted: true },
    { id: "isaac-lab", band: "training", adopted: true },
    { id: "cosmos-reason-2", band: "training", adopted: true },
    { id: "onnx-runtime", band: "acceleration", adopted: true },
    { id: "tensorrt", band: "acceleration", adopted: true },
    { id: "nsight-nvml", band: "acceleration", adopted: true },
    { id: "nvenc-ffmpeg", band: "encoding", adopted: true },
    { id: "threejs-r3f-3d-tiles", band: "web", adopted: true },
    { id: "rapier-webgpu-pyodide", band: "web", adopted: true },
    { id: "cuopt", band: "acceleration", adopted: false },
    { id: "physicsnemo", band: "physics", adopted: false },
    { id: "cosmos-predict-transfer", band: "sensors-synthetic-data", adopted: false },
  ];
export const TOOL_IDS = STUDIO_TOOLS.map((t) => t.id);
export const ADOPTED_IDS = STUDIO_TOOLS.filter((t) => t.adopted).map((t) => t.id);
export const NOT_ADOPTED_IDS = STUDIO_TOOLS.filter((t) => !t.adopted).map((t) => t.id);

export interface ToolEntryFull {
  id: string;
  name: string;
  category: "studio-tool" | "component";
  envs: string[];
  version: Record<string, unknown>;
  spdx: string[];
  osi: boolean;
  licence_class: LicenceClass;
  ring: (typeof RINGS)[number];
  lane: (typeof LANES)[number];
  performance: "public" | "local-only";
  role: string;
  cases: string[];
  produces: string[];
  status: StatusId;
  reason?: string;
  docs_page?: string;
  alternatives_rejected?: Array<{ name: string; reason: string }>;
  notice?: string;
}

export function makeTool(id: string, over: Partial<ToolEntryFull> = {}): ToolEntryFull {
  const adopted = !NOT_ADOPTED_IDS.includes(id);
  const base: ToolEntryFull = {
    id,
    name: `Tool ${id}`,
    category: "studio-tool",
    envs: ["studio"],
    version: { from_lock: "studio/uv.lock", package: id },
    spdx: ["Apache-2.0"],
    osi: true,
    licence_class: "attribution",
    ring: "Adopt",
    lane: "replay",
    performance: "public",
    role: `Role of ${id} in mining.`,
    cases: [],
    produces: [],
    status: adopted ? "not-yet-run" : "evaluated-not-adopted",
    docs_page: adopted ? `docs/frameworks/${id}.md` : `docs/frameworks/not-adopted-${id}.md`,
  };
  if (!adopted) base.reason = `Evaluated and not adopted: the reason recorded for ${id}.`;
  return { ...base, ...over };
}

/** A registry of the 20 tools in which the lane, ring and licence class rotate so that every value is used. */
export function makeRegistry(over: Record<string, Partial<ToolEntryFull>> = {}): ToolEntryFull[] {
  return TOOL_IDS.map((id, i) =>
    makeTool(id, {
      lane: LANES[i % LANES.length] as ToolEntryFull["lane"],
      ring: RINGS[i % RINGS.length] as ToolEntryFull["ring"],
      licence_class: LICENCE_CLASSES[i % LICENCE_CLASSES.length] as LicenceClass,
      ...over[id],
    }),
  );
}

export interface ToolmapJson {
  bands: Array<{ id: string; tools: string[] }>;
  edges: Array<{ from: string; to: string; kind: string }>;
}

/** The tool map of the 20 tools: bands in the order of FR-019-02 and a few handoff edges. */
export function makeToolmap(edges?: ToolmapJson["edges"]): ToolmapJson {
  return {
    bands: BAND_IDS.map((band) => ({
      id: band,
      tools: STUDIO_TOOLS.filter((t) => t.band === band).map((t) => t.id),
    })),
    edges: edges ?? [
      { from: "openusd", to: "warp", kind: "usd" },
      { from: "openusd", to: "isaac-sim-replicator", kind: "usd" },
      { from: "isaac-sim-replicator", to: "pytorch", kind: "table" },
      { from: "pytorch", to: "onnx-runtime", kind: "onnx" },
    ],
  };
}

export function loadToolmapExample(): ToolmapJson {
  return readJson("specs/019-web-studio/contracts/examples/toolmap.valid.json") as ToolmapJson;
}

// ---------------------------------------------------------------------------------------------------------------
// Studio index (DC-019-03)
// ---------------------------------------------------------------------------------------------------------------
export interface StudioIndexJson {
  schema_version: string;
  git_sha: string;
  tools: Array<{
    id: string;
    position: { band: string; order: number; group: "map" | "not-adopted"; x_px: number; y_px: number };
    version: { value: string; release_date: string | null; from: string; lock?: string };
    probe: { status: "pass" | "fail" | "skip" | "not-probed"; [k: string]: unknown };
    artefacts: string[];
  }>;
  edges: Array<{
    from: string;
    to: string;
    kind: string;
    state: "observed" | "planned";
    evidence?: { run_id: string; from_artefact: string; to_artefact: string };
  }>;
  honesty: unknown;
}

export function loadStudioIndexExample(): StudioIndexJson {
  return readJson("specs/019-web-studio/contracts/examples/studio-index.valid.json") as StudioIndexJson;
}

/** An index entry for `id` with a probe status, in the band and order of the tool map. */
export function indexTool(
  id: string,
  over: Partial<StudioIndexJson["tools"][number]> = {},
): StudioIndexJson["tools"][number] {
  const meta = STUDIO_TOOLS.find((t) => t.id === id);
  const bandIndex = Math.max(0, BAND_IDS.indexOf((meta?.band ?? "scene") as (typeof BAND_IDS)[number]));
  const order = STUDIO_TOOLS.filter((t) => t.band === meta?.band && t.adopted === meta?.adopted).findIndex(
    (t) => t.id === id,
  );
  return {
    id,
    position: {
      band: meta?.band ?? "scene",
      order: Math.max(order, 0),
      group: meta?.adopted === false ? "not-adopted" : "map",
      x_px: 40 + 200 * bandIndex,
      y_px: 80 + 80 * Math.max(order, 0) + (meta?.adopted === false ? 320 : 0),
    },
    version: { value: "1.2.3", release_date: "2026-08-01", from: "lock", lock: "studio/uv.lock" },
    probe: { status: "not-probed" },
    artefacts: [],
    ...over,
  };
}

export function makeIndex(over: Partial<StudioIndexJson> = {}): StudioIndexJson {
  return {
    schema_version: "1.0",
    git_sha: "0123456789abcdef0123456789abcdef01234567",
    tools: TOOL_IDS.map((id) => indexTool(id)),
    edges: makeToolmap().edges.map((e) => ({ ...e, state: "planned" as const })),
    honesty: loadStudioIndexExample().honesty,
    ...over,
  };
}

// ---------------------------------------------------------------------------------------------------------------
// Run cards (the published run manifest, DC-001-01) and published telemetry (DC-002-03)
// ---------------------------------------------------------------------------------------------------------------
export interface RunCardJson {
  kind: "run";
  run_id: string;
  created: string;
  recipe: { id: string; path: string; sha256: string };
  git_sha: string;
  gpu: {
    backend: string;
    name: string;
    driver: string;
    vram_total_bytes: number;
    power_limit_enforced_w: number | null;
  } | null;
  published: boolean;
  stages: Array<
    Record<string, unknown> & { key: { id: string; variant?: string }; tool: string; performance: string }
  >;
  artefacts: Array<Record<string, unknown>>;
  notes?: string[];
  [k: string]: unknown;
}

export function loadRunCardExample(): RunCardJson {
  return readJson("specs/001-contracts/contracts/examples/manifest.valid.json") as RunCardJson;
}

/** A deep copy of the valid run card with `over` merged at the top level. */
export function makeRunCard(over: Partial<RunCardJson> = {}): RunCardJson {
  return { ...structuredClone(loadRunCardExample()), ...over };
}

export interface StageJson extends Record<string, unknown> {
  key: { id: string; variant?: string };
  tool: string;
  performance: string;
}

/** A succeeded public stage of a run card with the telemetry summary of the valid example (stage `st56_encode`). */
export function makeStage(id: string, tool: string, over: Record<string, unknown> = {}): StageJson {
  const base = structuredClone(loadRunCardExample().stages[0]) as StageJson;
  return { ...base, key: { id }, tool, ...over } as StageJson;
}

export interface TelemetryJson {
  run_id: string;
  stages: Array<{
    key: { id: string; variant?: string };
    performance: string;
    bucket_s: number;
    points: Array<Record<string, number | null>>;
  }>;
}

export function loadTelemetryExample(): TelemetryJson {
  return readJson(
    "specs/002-runner/contracts/examples/events.valid-published-telemetry.json",
  ) as TelemetryJson;
}

/** Artefacts of a studio tool in the web manifest, for the join by `producer.tool`. */
export function toolArtefact(id: string, tool: string, over: Record<string, unknown> = {}) {
  return makeArtefact({ id, producer: { tool, stage: { id: "st50_physics" } }, ...over } as never);
}
