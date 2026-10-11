// T-018-050 [red] · FR-018-47 (engine registry = the table of spec section 7.1) and FR-018-63 (parity-report gate; unit half, with
// FR-018-14 badge rule and FR-018-32 GPU-compute note). E2E half: web/e2e/t_018_050_parity_gate.spec.ts.
//
// Expected API (module `~/engines/registry`, file web/src/engines/registry.ts)
//   interface EngineEntry { id: string; cases: readonly string[]; runtime: string; parityClass: string; reference: string;
//                           sizeCap: string; timeoutMs: number; t0Fallback: string; gpuCompute: boolean }
//   ENGINE_REGISTRY: readonly EngineEntry[]        exactly the 25 rows of section 7.1, in table order
//   engineById(id: string): EngineEntry | undefined
//   PARITY_NOT_CONFIRMED = "parity not confirmed — showing precomputed results"
//   NEEDS_WEBGPU = "needs WebGPU to compute live"
//   parityGate(engineId: string, report: unknown): { live: boolean; notice: string | null }
//       `report` is the DC-018-05 document read at run time. live is true iff the report lists the engine, EVERY entry of that
//       engine has verdict "pass", and the report is well formed; otherwise live is false and notice = PARITY_NOT_CONFIRMED.
//       A missing, null, non-object or malformed report confirms nothing. Never throws.
//   engineMode(engineId: string, tier: "t1" | "t2" | "t0", report: unknown):
//       { mode: "live" | "replay"; badge: "LIVE" | "REPLAY"; notice: string | null }
//       t0 -> replay; a gpuCompute engine on t2 -> replay with NEEDS_WEBGPU; otherwise the parity gate decides
//       (live + LIVE, or replay + REPLAY with PARITY_NOT_CONFIRMED). The badge always follows what is shown (FR-018-14).
//
// Oracles: the table of spec 018 section 7.1 transcribed below by hand (columns compared after dropping Markdown backticks, case
// and repeated spaces); the case registry example (engines per case); the valid parity-report example of the spec
// (contracts/examples/parity-report.valid.json: blasting, geotech, mincut, des, gns pass; swe not_run; detector fail).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  ENGINE_REGISTRY,
  engineById,
  engineMode,
  NEEDS_WEBGPU,
  PARITY_NOT_CONFIRMED,
  parityGate,
} from "~/engines/registry";
import { ENGINE_IDS } from "~/test-support/engine-examples";
import { loadCaseRegistry } from "~/test-support/fixtures";

interface Row {
  id: string;
  cases: string[];
  runtime: string;
  parityClass: string;
  reference: string;
  sizeCap: string;
  timeoutMs: number;
  t0Fallback: string;
  gpuCompute: boolean;
}

// Spec 018 section 7.1, row by row.
const TABLE: Row[] = [
  {
    id: "des",
    cases: ["A1"],
    runtime: "TS worker (spec 007)",
    parityClass: "exact event trace (FR-007-10)",
    reference: "minehaulsim through the spec 007 adapter",
    sizeCap: "as FR-007-03 and FR-007-13 (live bundles ≤ 40 trucks; ≤ 2×10⁶ events)",
    timeoutMs: 10_000,
    t0Fallback: "baked traces",
    gpuCompute: false,
  },
  {
    id: "policies",
    cases: ["A1"],
    runtime: "ORT-web inside the DES worker (spec 007)",
    parityClass: "FR-007-32",
    reference: "ONNX Runtime CPU 1.30",
    sizeCap: "≤ 2 MB per policy",
    timeoutMs: 10_000,
    t0Fallback: "baked traces",
    gpuCompute: false,
  },
  {
    id: "haulage",
    cases: ["A1", "A2"],
    runtime: "TS worker (spec 007)",
    parityClass: "FR-007-15",
    reference: "minephys.haulage",
    sizeCap: "as FR-007-16",
    timeoutMs: 2_000,
    t0Fallback: "baked grid",
    gpuCompute: false,
  },
  {
    id: "lp",
    cases: ["A1"],
    runtime: "TS worker (spec 007)",
    parityClass: "FR-007-20",
    reference: "HiGHS (highspy)",
    sizeCap: "as FR-007-21",
    timeoutMs: 2_000,
    t0Fallback: "baked solution",
    gpuCompute: false,
  },
  {
    id: "routing",
    cases: ["A2", "E1"],
    runtime: "TS worker (spec 007)",
    parityClass: "FR-007-39",
    reference: "the spec 007 Python router; networkx Dijkstra as oracle",
    sizeCap: "as FR-007-36 (browser DEM ≤ 1024 × 1024 cells)",
    timeoutMs: 5_000,
    t0Fallback: "baked routes",
    gpuCompute: false,
  },
  {
    id: "il1-twin",
    cases: ["A2"],
    runtime: "TS worker + ORT-web (spec 014)",
    parityClass: "FR-014-42",
    reference: "Python twin of spec 014",
    sizeCap: "as spec 014 (≤ 2,000 steps)",
    timeoutMs: 10_000,
    t0Fallback: "baked rollouts",
    gpuCompute: false,
  },
  {
    id: "il2-twin",
    cases: ["A3"],
    runtime: "TS worker + ORT-web (spec 014)",
    parityClass: "FR-014-42",
    reference: "Python twin of spec 014",
    sizeCap: "as spec 014 (≤ 2,000 steps)",
    timeoutMs: 10_000,
    t0Fallback: "baked rollouts",
    gpuCompute: false,
  },
  {
    id: "granular",
    cases: ["A3"],
    runtime: "WGSL compute (T1 only)",
    parityClass: "chaotic / particle",
    reference: "Warp DEM / MPM on the CPU device (kernels); spec 005 goldens DC-005-06 (observables)",
    sizeCap: "≤ 2×10⁴ particles",
    timeoutMs: 30_000,
    t0Fallback: "replay shards, aggregates",
    gpuCompute: true,
  },
  {
    id: "gns",
    cases: ["A3"],
    runtime: "ORT-web",
    parityClass: "ML",
    reference: "ONNX Runtime CPU",
    sizeCap: "≤ 5,000 particles; model ≤ 25 MB",
    timeoutMs: 10_000,
    t0Fallback: "precomputed rollouts",
    gpuCompute: false,
  },
  {
    id: "traffic",
    cases: ["B1"],
    runtime: "Rapier WASM + TS agents",
    parityClass: "rigid body (snapshot hash); TTC closed form",
    reference: "Rapier 0.21 in Node; TTC hand calculation",
    sizeCap: "≤ 40 vehicles",
    timeoutMs: 10_000,
    t0Fallback: "baked video",
    gpuCompute: false,
  },
  {
    id: "dust-lidar",
    cases: ["B1", "C3"],
    runtime: "TS worker (spec 013)",
    parityClass: "P-013-15",
    reference: "the spec 013 Python post-model",
    sizeCap: "as spec 013 (frames ≤ 150,000 returns)",
    timeoutMs: 2_000,
    t0Fallback: "baked frames",
    gpuCompute: false,
  },
  {
    id: "detector",
    cases: ["B2"],
    runtime: "ORT-web (post-processor in the graph, no NMS)",
    parityClass: "ML",
    reference: "ONNX Runtime CPU on the spec 009 export",
    sizeCap: "shipped sample frames only, 640 × 640 input",
    timeoutMs: 5_000,
    t0Fallback: "precomputed detections",
    gpuCompute: false,
  },
  {
    id: "geotech",
    cases: ["C1"],
    runtime: "TS worker",
    parityClass: "analytical (+ statistical Monte Carlo)",
    reference: "minephys.geotech",
    sizeCap: "≤ 200 slices; ≤ 10⁵ Monte-Carlo samples",
    timeoutMs: 5_000,
    t0Fallback: "baked grid",
    gpuCompute: false,
  },
  {
    id: "forecasters",
    cases: ["C1"],
    runtime: "ORT-web",
    parityClass: "ML",
    reference: "ONNX Runtime CPU",
    sizeCap: "each ≤ 25 MB",
    timeoutMs: 10_000,
    t0Fallback: "precomputed forecasts",
    gpuCompute: false,
  },
  {
    id: "swe",
    cases: ["C2"],
    runtime: "WGSL compute (T1 only)",
    parityClass: "chaotic / field",
    reference:
      "Warp shallow-water solver on the CPU device (kernels); spec 005 goldens DC-005-06 (observables)",
    sizeCap: "≤ 256 × 256 cells",
    timeoutMs: 30_000,
    t0Fallback: "baked aggregates",
    gpuCompute: true,
  },
  {
    id: "fno",
    cases: ["C2"],
    runtime: "ORT-web",
    parityClass: "ML",
    reference: "ONNX Runtime CPU",
    sizeCap: "≤ 25 MB",
    timeoutMs: 10_000,
    t0Fallback: "precomputed fields",
    gpuCompute: false,
  },
  {
    id: "plume",
    cases: ["C3"],
    runtime: "TS worker",
    parityClass: "analytical",
    reference: "minephys.environment (AP-42 and Gaussian plume)",
    sizeCap: "receptor grid ≤ 256 × 256",
    timeoutMs: 2_000,
    t0Fallback: "baked grid",
    gpuCompute: false,
  },
  {
    id: "dust-particles",
    cases: ["C3"],
    runtime: "WGSL compute (T1 only)",
    parityClass: "particle",
    reference: "Warp particles on the CPU device (kernels); spec 005 goldens DC-005-06 (observables)",
    sizeCap: "≤ 2×10⁴ particles",
    timeoutMs: 30_000,
    t0Fallback: "replay shards",
    gpuCompute: true,
  },
  {
    id: "blasting",
    cases: ["D1"],
    runtime: "TS worker",
    parityClass: "analytical",
    reference: "minephys.blasting",
    sizeCap: "—",
    timeoutMs: 2_000,
    t0Fallback: "baked grid",
    gpuCompute: false,
  },
  {
    id: "watershed",
    cases: ["D1"],
    runtime: "TS worker",
    parityClass: "exact label map on fixture inputs",
    reference: "Python watershed baseline of spec 012",
    sizeCap: "≤ 1024 × 1024 px",
    timeoutMs: 5_000,
    t0Fallback: "precomputed PSDs",
    gpuCompute: false,
  },
  {
    id: "unet",
    cases: ["D1"],
    runtime: "ORT-web",
    parityClass: "ML",
    reference: "ONNX Runtime CPU",
    sizeCap: "≤ 25 MB",
    timeoutMs: 10_000,
    t0Fallback: "precomputed masks",
    gpuCompute: false,
  },
  {
    id: "comminution",
    cases: ["D2"],
    runtime: "TS worker",
    parityClass: "analytical",
    reference: "minephys.comminution",
    sizeCap: "—",
    timeoutMs: 2_000,
    t0Fallback: "baked grid",
    gpuCompute: false,
  },
  {
    id: "meta-model",
    cases: ["D2"],
    runtime: "ORT-web",
    parityClass: "ML",
    reference: "ONNX Runtime CPU",
    sizeCap: "≤ 1 MB",
    timeoutMs: 5_000,
    t0Fallback: "precomputed answers",
    gpuCompute: false,
  },
  {
    id: "mincut",
    cases: ["E1"],
    runtime: "TS worker",
    parityClass: "combinatorial",
    reference: "minephys.planning min-cut; networkx maximum flow as oracle",
    sizeCap: "≤ 10⁵ blocks",
    timeoutMs: 10_000,
    t0Fallback: "baked nested shells",
    gpuCompute: false,
  },
  {
    id: "volume",
    cases: ["E2"],
    runtime: "TS worker",
    parityClass: "analytical",
    reference: "numpy DEM differencing of spec 017",
    sizeCap: "polygon ≤ 10⁴ vertices; grid ≤ 2048 × 2048",
    timeoutMs: 5_000,
    t0Fallback: "baked volumes",
    gpuCompute: false,
  },
];

interface E {
  id: string;
  cases: readonly string[];
  gpuCompute: boolean;
}
const norm = (s: string) => s.replace(/`/g, "").replace(/\s+/g, " ").trim().toLowerCase();

describe("engine registry (FR-018-47)", () => {
  it("FR-018-47 · lists exactly the 25 engines of section 7.1, in table order, with unique ids", () => {
    expect(ENGINE_REGISTRY.map((e: E) => e.id)).toEqual(TABLE.map((r) => r.id));
    expect(new Set(ENGINE_REGISTRY.map((e: E) => e.id)).size).toBe(25);
    expect([...ENGINE_IDS]).toEqual(TABLE.map((r) => r.id));
  });

  for (const row of TABLE) {
    it(`FR-018-47 · ${row.id} carries its row of the table (cases, runtime, parity class, reference, size cap, timeout, T0 fallback)`, () => {
      const e = engineById(row.id);
      expect(e).toBeDefined();
      if (!e) return;
      expect([...e.cases]).toEqual(row.cases);
      expect(norm(e.runtime)).toBe(norm(row.runtime));
      expect(norm(e.parityClass)).toBe(norm(row.parityClass));
      expect(norm(e.reference)).toBe(norm(row.reference));
      expect(norm(e.sizeCap)).toBe(norm(row.sizeCap));
      expect(e.timeoutMs).toBe(row.timeoutMs);
      expect(norm(e.t0Fallback)).toBe(norm(row.t0Fallback));
      expect(e.gpuCompute).toBe(row.gpuCompute);
    });
  }

  it("FR-018-47 · only granular, swe and dust-particles need GPU compute", () => {
    expect(ENGINE_REGISTRY.filter((e: E) => e.gpuCompute).map((e: E) => e.id)).toEqual([
      "granular",
      "swe",
      "dust-particles",
    ]);
  });

  it("FR-018-47 · an unknown id has no entry (no prototype keys, no empty string)", () => {
    for (const id of ["", "nope", "__proto__", "constructor", "toString", "DES", " des"]) {
      expect(engineById(id)).toBeUndefined();
    }
  });

  it("FR-018-47 · the engines of every case in the case registry are exactly the registry rows that list that case", () => {
    const cases = loadCaseRegistry().cases;
    for (const [caseId, entry] of Object.entries(cases)) {
      const fromTable = ENGINE_REGISTRY.filter((e: E) => e.cases.includes(caseId)).map((e: E) => e.id);
      expect([...entry.engines].sort(), caseId).toEqual(fromTable.sort());
    }
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Parity gate (FR-018-63)
// ---------------------------------------------------------------------------------------------------------------------
const reportPath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/018-web-cases/contracts/examples/parity-report.valid.json",
);
const validReport = () =>
  JSON.parse(readFileSync(reportPath, "utf8")) as { engines: Array<Record<string, unknown>> };

describe("parity gate (FR-018-63)", () => {
  const passing = ["blasting", "geotech", "mincut", "des", "gns"];
  for (const id of passing) {
    it(`FR-018-63 · ${id} is listed with verdict pass in the example report: live, no notice`, () => {
      expect(parityGate(id, validReport())).toEqual({ live: true, notice: null });
    });
  }

  it("FR-018-63 · an engine whose verdict is fail (detector) is not live and says parity is not confirmed", () => {
    expect(parityGate("detector", validReport())).toEqual({ live: false, notice: PARITY_NOT_CONFIRMED });
    expect(PARITY_NOT_CONFIRMED).toBe("parity not confirmed — showing precomputed results");
  });

  it("FR-018-63 · an engine that was not run (swe, verdict not_run) is not live", () => {
    expect(parityGate("swe", validReport()).live).toBe(false);
  });

  it("FR-018-63 · an engine the report does not list is not live", () => {
    for (const id of ["plume", "volume", "traffic", "granular", "unet"]) {
      expect(parityGate(id, validReport())).toEqual({ live: false, notice: PARITY_NOT_CONFIRMED });
    }
  });

  it("FR-018-63 · an engine with two entries, one pass and one fail, is not live", () => {
    const report = validReport();
    report.engines.push({
      ...(report.engines[0] as object),
      tolerance: { class: "analytical-iterative", rtol: 1e-8, atol_scale: 1e-12, solver_tol: 1e-9 },
      verdict: "fail",
    });
    expect(parityGate("blasting", report).live).toBe(false);
  });

  it("FR-018-63 · flipping a passing engine to fail in an otherwise valid report turns exactly that engine off", () => {
    const report = validReport();
    for (const e of report.engines) if (e.engine === "gns") e.verdict = "fail";
    expect(parityGate("gns", report).live).toBe(false);
    expect(parityGate("blasting", report).live).toBe(true);
  });

  const unusable: Array<[string, unknown]> = [
    ["undefined", undefined],
    ["null", null],
    ["a string", "pass"],
    ["a number", 7],
    ["an array", []],
    ["an empty object", {}],
    ["engines not an array", { engines: "des" }],
    ["engines empty", { engines: [] }],
    ["an entry without a verdict", { engines: [{ engine: "des" }] }],
    ["an upper-case verdict", { engines: [{ engine: "des", verdict: "PASS" }] }],
    ["a verdict of the wrong type", { engines: [{ engine: "des", verdict: true }] }],
    ["null entries", { engines: [null, 3, "des"] }],
  ];
  for (const [name, report] of unusable) {
    it(`FR-018-63 · ${name} confirms nothing and does not throw`, () => {
      let out: ReturnType<typeof parityGate> | undefined;
      expect(() => {
        out = parityGate("des", report);
      }).not.toThrow();
      expect(out).toEqual({ live: false, notice: PARITY_NOT_CONFIRMED });
    });
  }

  it("FR-018-63 · property-style sweep: every engine of the table is gated, and only report-listed passing ones are live", () => {
    const live = ENGINE_REGISTRY.filter((e: E) => parityGate(e.id, validReport()).live).map((e: E) => e.id);
    expect(live.sort()).toEqual([...passing].sort());
  });
});

describe("what is shown (FR-018-14, FR-018-32, FR-018-63)", () => {
  const report = () => validReport();

  it("FR-018-14 · a passing TypeScript engine on T2 is computed here: LIVE, no notice", () => {
    expect(engineMode("blasting", "t2", report())).toEqual({ mode: "live", badge: "LIVE", notice: null });
    expect(engineMode("gns", "t1", report())).toEqual({ mode: "live", badge: "LIVE", notice: null });
  });

  it("FR-018-63 · a failing engine shows REPLAY with the parity notice instead of LIVE", () => {
    expect(engineMode("detector", "t2", report())).toEqual({
      mode: "replay",
      badge: "REPLAY",
      notice: PARITY_NOT_CONFIRMED,
    });
  });

  it("FR-018-14 · T0 shows baked results only: REPLAY for every engine, even a passing one", () => {
    for (const e of ENGINE_REGISTRY) {
      const out = engineMode(e.id, "t0", report());
      expect(out.mode).toBe("replay");
      expect(out.badge).toBe("REPLAY");
    }
  });

  it("FR-018-32 · a GPU-compute engine on T2 shows its replay with 'needs WebGPU to compute live'", () => {
    for (const id of ["granular", "swe", "dust-particles"]) {
      const out = engineMode(id, "t2", report());
      expect(out).toEqual({ mode: "replay", badge: "REPLAY", notice: NEEDS_WEBGPU });
    }
    expect(NEEDS_WEBGPU).toBe("needs WebGPU to compute live");
  });

  it("FR-018-63 · a GPU-compute engine on T1 without a passing report is held back by the parity gate (WGSL parity runs only in the webgpu project)", () => {
    expect(engineMode("swe", "t1", report())).toEqual({
      mode: "replay",
      badge: "REPLAY",
      notice: PARITY_NOT_CONFIRMED,
    });
    expect(engineMode("granular", "t1", report())).toEqual({
      mode: "replay",
      badge: "REPLAY",
      notice: PARITY_NOT_CONFIRMED,
    });
  });

  it("FR-018-63 · with no report at all no engine is LIVE on any tier", () => {
    for (const e of ENGINE_REGISTRY) {
      for (const tier of ["t1", "t2", "t0"] as const) {
        expect(engineMode(e.id, tier, undefined).badge, `${e.id} ${tier}`).toBe("REPLAY");
      }
    }
  });

  it("FR-018-63 · an unknown engine id is never LIVE", () => {
    expect(engineMode("nope", "t2", report()).badge).toBe("REPLAY");
  });
});
