// Shared, locked test support for the P6 web-structure tests (specs 018 and 020). Not a test file.
//
// Oracles in here are hand transcriptions of committed documents, never output of the code under test:
//   - CASE_IDS / GROUPS                : FR-018-02 (12 cases in 5 groups, in this order).
//   - COVERAGE_ORACLE / TOOL_ORACLE    : docs/cases/coverage-matrix.md and docs/cases/tool-matrix.md (the 17 studio tools).
//   - UNIT_SYMBOLS                     : display symbols used by docs/cases/README.md (catalogue table).
//   - loadCaseRegistry()               : the valid example of the case registry contract DC-018-01
//                                        (specs/018-web-cases/contracts/examples/cases.valid.json), schema-validated by spec 018.
//   - makeArtefact / makeRun / makeWebIndex : records shaped by data-model 001 section 2.5 / 2.1 / 2.8 (spec 001).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"] as const;
export type CaseId = (typeof CASE_IDS)[number];

/** FR-018-02: five labelled groups, in this order. */
export const GROUPS: ReadonlyArray<readonly [letter: string, ids: readonly CaseId[]]> = [
  ["A", ["A1", "A2", "A3"]],
  ["B", ["B1", "B2"]],
  ["C", ["C1", "C2", "C3"]],
  ["D", ["D1", "D2"]],
  ["E", ["E1", "E2"]],
];

/** Display tab names of the case page (FR-018-11), in order, with the `tab=` query values of FR-018-12. */
export const CASE_TABS: ReadonlyArray<readonly [label: string, param: string]> = [
  ["Scene", "scene"],
  ["Simulate (live)", "simulate"],
  ["Studio replay", "replay"],
  ["Charts", "charts"],
  ["Context", "context"],
];

// ---------------------------------------------------------------------------------------------------------------
// Case registry (DC-018-01)
// ---------------------------------------------------------------------------------------------------------------
export interface Text2 {
  en: string;
  es: string;
}
export interface KpiJson {
  id: string;
  name: Text2;
  unit: string;
  orientation: string;
  headline: boolean;
  target_value?: number;
}
export interface SyntheticJson {
  label: Text2;
  validation: "validated-against-real" | "descriptive-only" | "unvalidated";
  reference_source?: string;
}
export interface CaseJson {
  category: string;
  title: Text2;
  question: Text2;
  kpis: KpiJson[];
  sources: string[];
  synthetic_data: SyntheticJson[];
  methods: string[];
  tools: Record<string, "named" | "supporting">;
  engines: string[];
  layers: string[];
  clock_fps?: number;
  recipe: string;
  validity: Text2;
}
export interface CaseRegistryJson {
  schema_version: string;
  categories: Record<string, { title: Text2 }>;
  cases: Record<string, CaseJson>;
}

// web/src/test-support -> repository root is three levels up (a path string, not a URL object: jsdom replaces `URL`).
const REGISTRY_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/018-web-cases/contracts/examples/cases.valid.json",
);

export function loadCaseRegistry(): CaseRegistryJson {
  return JSON.parse(readFileSync(REGISTRY_PATH, "utf8")) as CaseRegistryJson;
}

/** A deep copy whose `cases` and `categories` keys are in reverse insertion order (order must not depend on it). */
export function withReversedKeys(registry: CaseRegistryJson): CaseRegistryJson {
  const copy = structuredClone(registry);
  const rev = <T>(o: Record<string, T>) => Object.fromEntries(Object.entries(o).reverse());
  return { ...copy, categories: rev(copy.categories), cases: rev(copy.cases) };
}

export function headlineKpis(registry: CaseRegistryJson, id: string): KpiJson[] {
  return (registry.cases[id]?.kpis ?? []).filter((k) => k.headline);
}

/** ASCII unit id (DC-018-01 `kpi_unit`) -> display symbol, as the catalogue of docs/cases/README.md writes it.
 *  Dimensionless "1" and "1/(1000 h)" are left out on purpose (the docs write them as prose). */
export const UNIT_SYMBOLS: Record<string, string> = {
  "%": "%",
  pp: "pp",
  s: "s",
  min: "min",
  h: "h",
  m: "m",
  mm: "mm",
  km: "km",
  km2: "km²",
  m3: "m³",
  "m3/shift": "m³/shift",
  "t/h": "t/h",
  "kWh/t": "kWh/t",
  "kg/t": "kg/t",
  "L/t": "L/t",
  "L/(t.km)": "L/(t·km)",
  USD: "USD",
  "USD/t": "USD/t",
  "kg/VKT": "kg/VKT",
  "ug/m3": "µg/m³",
  "mm/s": "mm/s",
  "passes/truck": "passes/truck",
};

// ---------------------------------------------------------------------------------------------------------------
// Matrices (docs oracles)
// ---------------------------------------------------------------------------------------------------------------
/** docs/cases/coverage-matrix.md: method -> the cases that carry a mark (34 marks in total). */
export const COVERAGE_ORACLE: Record<string, string[]> = {
  M1: ["A1"],
  M2: ["A1", "A2", "B1", "C3"],
  M3: ["A1"],
  M4: ["A1"],
  M5: ["A1"],
  M6: ["A2", "E1"],
  M7: ["A3", "D1"],
  M8: ["A3"],
  M9: ["A3"],
  M10: ["B2"],
  M11: ["D1"],
  M12: ["D1", "D2"],
  M13: ["C1"],
  M14: ["C1"],
  M15: ["C2"],
  M16: ["C3"],
  M17: ["D2"],
  M18: ["E1"],
  M19: ["E2"],
  M20: ["B1"],
  M21: ["A2", "A3"],
  M22: ["B1", "B2"],
  M23: ["B1", "B2", "C1", "E2"],
};
export const COVERAGE_MARKS = 34;

/** docs/cases/tool-matrix.md, the 17 studio tools (registry ids of data-model 001 section 4.3): named = ●, supporting = ○. */
export const TOOL_ORACLE: Record<string, { named: string[]; supporting: string[] }> = {
  openusd: { named: [], supporting: ["B1", "B2", "C2", "C3", "D1", "E1", "E2"] },
  warp: { named: ["A3", "C2", "C3", "D1"], supporting: [] },
  newton: { named: ["A2", "A3"], supporting: [] },
  "mujoco-warp": { named: ["A3"], supporting: [] },
  "physx-ovphysx": { named: [], supporting: ["B1"] },
  ovrtx: { named: ["B1", "B2", "C3", "E2"], supporting: [] },
  "isaac-sim-replicator": { named: ["B1", "B2", "D1"], supporting: [] },
  "isaac-lab": { named: ["A2", "A3"], supporting: [] },
  "kit-usd-composer-explorer": { named: ["C2", "E1"], supporting: [] },
  "cosmos-reason-2": { named: ["B1", "B2"], supporting: [] },
  pytorch: { named: ["A1", "C1", "D2"], supporting: ["A2", "A3", "B2", "C2", "D1"] },
  "onnx-runtime": { named: [], supporting: ["A1", "A2", "A3", "B2", "C1", "C2", "D1", "D2"] },
  tensorrt: { named: ["A1", "B2", "D1"], supporting: [] },
  "nvenc-ffmpeg": { named: [], supporting: ["A2", "A3", "B1", "C2", "D1", "E2"] },
  "nsight-nvml": {
    named: [],
    supporting: ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"],
  },
  "threejs-r3f-3d-tiles": {
    named: [],
    supporting: ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"],
  },
  "rapier-webgpu-pyodide": {
    named: [],
    supporting: ["A1", "A2", "A3", "B1", "C1", "C2", "C3", "D1", "D2", "E1"],
  },
};

export interface ToolEntryJson {
  id: string;
  name: string;
  category: "studio-tool" | "component";
  status: "not-yet-run" | "done" | "evaluated-not-adopted";
}

/** Tool registry entries (data-model 001 section 4.3): 17 studio tools + 3 evaluated-not-adopted + components. */
export const TOOL_ENTRIES: ToolEntryJson[] = [
  ...Object.keys(TOOL_ORACLE).map(
    (id): ToolEntryJson => ({ id, name: `Tool ${id}`, category: "studio-tool", status: "not-yet-run" }),
  ),
  ...["cuopt", "physicsnemo", "cosmos-predict-transfer"].map(
    (id): ToolEntryJson => ({
      id,
      name: `Tool ${id}`,
      category: "studio-tool",
      status: "evaluated-not-adopted",
    }),
  ),
  ...["pitstudio", "minephys", "minehaulsim", "oreblocks", "colmap", "brush"].map(
    (id): ToolEntryJson => ({ id, name: `Component ${id}`, category: "component", status: "not-yet-run" }),
  ),
];

// ---------------------------------------------------------------------------------------------------------------
// Data source registry entries (data-model 001 section 5.1; only the fields the pages read)
// ---------------------------------------------------------------------------------------------------------------
export interface SourceJson {
  id: string;
  kind: "real" | "synthetic";
  title: string;
  spdx: string;
  landing_url: string;
  card: string;
}

export function makeSource(over: Partial<SourceJson> & { id: string }): SourceJson {
  return {
    kind: "real",
    title: `Title of ${over.id}`,
    spdx: "CC-BY-4.0",
    landing_url: `https://example.org/${over.id}`,
    card: `data/cards/${over.id}.md`,
    ...over,
  };
}

/** Sources the case registry references (ids as in the registry example), with licences from the publishers. */
export const SOURCES: SourceJson[] = [
  makeSource({
    id: "usgs-3dep-bingham",
    spdx: "LicenseRef-USGov-PD",
    title: "USGS 3DEP 1 m DEM, Bingham Canyon",
  }),
  makeSource({ id: "dewit-slope-failure", spdx: "CC-BY-4.0", title: "Slope failure monitoring series" }),
  makeSource({ id: "egms-hambach", spdx: "CC-BY-4.0", title: "EGMS ground motion, Hambach" }),
  makeSource({ id: "makehuman-exports", kind: "synthetic", spdx: "CC0-1.0", title: "MakeHuman exports" }),
  makeSource({ id: "mendeley-78ht3pjsr4", spdx: "CC-BY-4.0", title: "Labelled fragment images" }),
  makeSource({ id: "era5", spdx: "LicenseRef-Copernicus-CLMS", title: "ERA5 reanalysis" }),
  makeSource({ id: "ghcnh", spdx: "LicenseRef-USGov-PD", title: "GHCN hourly" }),
  makeSource({ id: "minelib-marvin", spdx: "CC-BY-SA-4.0", title: "MineLib marvin" }),
];

// ---------------------------------------------------------------------------------------------------------------
// Web manifest records (data-model 001 section 2.5 / 2.1 / 2.8)
// ---------------------------------------------------------------------------------------------------------------
export interface ArtefactJson {
  id: string;
  run_id: string;
  git_sha: string;
  path: string;
  bytes: number;
  sha256: string;
  kind: string;
  producer: { tool: string; stage: { id: string; variant?: string } };
  inputs: Array<{ id: string; sha256: string; kind: "source" | "artefact" | "knowledge" }>;
  cases?: string[];
  lane: "live" | "replay" | "static";
  lane_measurements?: {
    web_drivable: boolean;
    max_asset_bytes: number;
    interaction_ms: number | null;
    run_ms_t2: number | null;
    trace_bytes: number | null;
    measured: { tier: "T2"; date: string; browser: string };
  };
  licence_class: string;
  spdx: string;
  attribution?: string;
  asset_host: "git" | "release";
  budget_class: string;
}

export const GIT_SHA = "0123456789abcdef0123456789abcdef01234567";
export const SHA256_A = "a".repeat(64);
export const RUN_ID = "20261011T083000Z-a1";

export function makeArtefact(over: Partial<ArtefactJson> = {}): ArtefactJson {
  const lane = over.lane ?? "replay";
  const base: ArtefactJson = {
    id: "a1-queue-chart",
    run_id: RUN_ID,
    git_sha: GIT_SHA,
    path: "artefacts/a1-queue-chart.json",
    bytes: 1234,
    sha256: SHA256_A,
    kind: "shard",
    producer: { tool: "warp", stage: { id: "st50_physics" } },
    inputs: [{ id: "usgs-3dep-bingham", sha256: SHA256_A, kind: "source" }],
    cases: ["A1"],
    lane,
    licence_class: "public-domain",
    spdx: "LicenseRef-USGov-PD",
    asset_host: "git",
    budget_class: "shards-clouds",
  };
  if (lane !== "static") {
    base.lane_measurements = {
      web_drivable: lane === "live",
      max_asset_bytes: 1234,
      interaction_ms: lane === "live" ? 4 : null,
      run_ms_t2: lane === "live" ? 120 : null,
      trace_bytes: null,
      measured: { tier: "T2", date: "2026-10-11", browser: "chromium" },
    };
  }
  return { ...base, ...over };
}

export interface RunSummaryJson {
  run_id: string;
  gpu: { backend: "nvml"; name: string; driver: string } | null;
  created: string;
}

export function makeRun(over: Partial<RunSummaryJson> = {}): RunSummaryJson {
  return {
    run_id: RUN_ID,
    gpu: { backend: "nvml", name: "NVIDIA RTX 5000 Ada Generation Laptop GPU", driver: "595.95" },
    created: "2026-10-11T08:30:00Z",
    ...over,
  };
}

/** `web/public/assets/manifest.json` (kind web-index). */
export function makeWebIndex(artefacts: ArtefactJson[]) {
  return {
    kind: "web-index",
    schema_version: "1.0",
    generated: "2026-10-11",
    git_sha: GIT_SHA,
    runs: [] as Array<{ run_id: string; manifest: string; sha256: string }>,
    artefacts,
  };
}
