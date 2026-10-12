// Shared, locked E2E support for the published-run tests of spec 019 (ledger, run page, GPU page, budgets, accessibility). Not a test file.
//
// The run pages are PRERENDERED from the run cards found under `web/public/assets/runs/<run id>/` (FR-019-22), so the E2E build of these tests must contain published runs. The three fixture runs live in
// `web/e2e/fixtures/studio-runs/<run id>/{manifest,telemetry}.json` (schema-valid run cards of DC-001-01 and published telemetry of DC-002-03, written from the spec example corpus) and the build that the
// studio E2E tests run against is made with `STUDIO_RUNS_DIR=e2e/fixtures/studio-runs` (a directory whose sub-folders are copied to `public/assets/runs/` before the build; flagged in the red report as a
// contract the green commit and the CI job must provide). A third run id, `UNPUBLISHED_RUN`, is well-formed and absent from the artifact.
//
// A third published run, RUN_BIG, holds a run card of about 200 KB (199,866 bytes, just under the 200,000-byte cap of FR-019-38, 285 artefacts of case E2 produced by pytorch) for the render-time bound of FR-019-23.
//
// The FACTS below are hand transcriptions of those fixture files (the oracle of the tests, not read from the code under test).
export const RUN_A = "20261007T120000Z-a2-haulage";
export const RUN_B = "20261007T210000Z-c2-slope";
export const RUN_BIG = "20261006T120000Z-e2-bigcard";
export const UNPUBLISHED_RUN = "20261010T000000Z-local-draft";

export interface StageFact {
  id: string;
  variant?: string;
  tool: string;
  cache: "hit" | "miss";
  status: string;
  performance: "public" | "local-only";
  wall_s?: number;
  attempts: number;
  retries: number;
  exit_code: number | null;
  determinism: string;
}

export interface RunFact {
  id: string;
  created: string;
  date: string;
  gpu: string;
  driver: string;
  vram_gib: number;
  power_limit_w: number;
  cases: string[];
  artefact_tools: string[];
  artefacts: string[];
  stages: StageFact[];
  /** published telemetry points of the public stages: stage id -> number of points */
  telemetry_points: Record<string, number>;
}

export const RUNS: Record<string, RunFact> = {
  [RUN_A]: {
    id: RUN_A,
    created: "2026-10-07T12:00:00Z",
    date: "2026-10-07",
    gpu: "NVIDIA RTX 5000 Ada Generation Laptop GPU",
    driver: "582.78",
    vram_gib: 16,
    power_limit_w: 175,
    cases: ["A2"],
    artefact_tools: ["nvenc-ffmpeg"],
    artefacts: ["a2-haul-clip", "a2-encode-report"],
    stages: [
      {
        id: "st56_encode",
        tool: "nvenc-ffmpeg",
        cache: "miss",
        status: "succeeded",
        performance: "public",
        wall_s: 42.5,
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "statistical",
      },
      {
        id: "st53_sensors",
        tool: "ovrtx",
        cache: "hit",
        status: "succeeded",
        performance: "local-only",
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "none",
      },
      {
        id: "st45b_kit_validate",
        tool: "kit-usd-composer-explorer",
        cache: "miss",
        status: "not_run",
        performance: "local-only",
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "none",
      },
    ],
    telemetry_points: { st56_encode: 3 },
  },
  [RUN_B]: {
    id: RUN_B,
    created: "2026-10-07T21:00:00Z",
    date: "2026-10-07",
    gpu: "NVIDIA RTX 5000 Ada Generation Laptop GPU",
    driver: "582.78",
    vram_gib: 16,
    power_limit_w: 175,
    cases: ["C2"],
    artefact_tools: ["isaac-sim-replicator", "openusd", "warp"],
    artefacts: ["c2-scene", "c2-flood-field", "c2-render"],
    stages: [
      {
        id: "st40_compose",
        tool: "openusd",
        cache: "hit",
        status: "succeeded",
        performance: "public",
        wall_s: 3.25,
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "bitwise",
      },
      {
        id: "st50_physics",
        tool: "warp",
        cache: "miss",
        status: "succeeded",
        performance: "public",
        wall_s: 120.5,
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "statistical",
      },
      {
        id: "st55_sdg",
        tool: "isaac-sim-replicator",
        cache: "miss",
        status: "succeeded",
        performance: "local-only",
        attempts: 1,
        retries: 0,
        exit_code: 0,
        determinism: "none",
      },
      {
        id: "s62_accel",
        variant: "fp8",
        tool: "tensorrt",
        cache: "miss",
        status: "failed",
        performance: "public",
        wall_s: 41.5,
        attempts: 1,
        retries: 0,
        exit_code: 3,
        determinism: "none",
      },
    ],
    telemetry_points: { st50_physics: 3 },
  },
};

RUNS[RUN_BIG] = {
  id: RUN_BIG,
  created: "2026-10-06T12:00:00Z",
  date: "2026-10-06",
  gpu: "NVIDIA RTX 5000 Ada Generation Laptop GPU",
  driver: "582.78",
  vram_gib: 16,
  power_limit_w: 175,
  cases: ["E2"],
  artefact_tools: ["pytorch"],
  artefacts: Array.from({ length: 285 }, (_, i) => `e2-eval-${String(i + 1).padStart(4, "0")}`),
  stages: [
    {
      id: "s50_evaluate",
      tool: "pytorch",
      cache: "miss",
      status: "succeeded",
      performance: "public",
      wall_s: 12.5,
      attempts: 1,
      retries: 0,
      exit_code: 0,
      determinism: "bitwise",
    },
  ],
  telemetry_points: { s50_evaluate: 1 },
};
/** The run ids in the order of the ledger: newest first. */
export const LEDGER_ORDER = [RUN_B, RUN_A, RUN_BIG];
