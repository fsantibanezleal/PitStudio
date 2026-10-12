// Engine registry: exactly the engines of the table of spec 018 section 7.1, in table order (FR-018-47), and the parity-report
// gate that decides whether an engine shows LIVE or REPLAY (FR-018-63, FR-018-14, FR-018-32).

export interface EngineEntry {
  id: string;
  cases: readonly string[];
  runtime: string;
  parityClass: string;
  reference: string;
  sizeCap: string;
  timeoutMs: number;
  t0Fallback: string;
  gpuCompute: boolean;
}

export const ENGINE_REGISTRY: readonly EngineEntry[] = [
  {
    id: "des",
    cases: ["A1"],
    runtime: "TS worker (spec 007)",
    parityClass: "exact event trace (FR-007-10)",
    reference: "minehaulsim through the spec 007 adapter",
    sizeCap: "as FR-007-03 and FR-007-13 (live bundles ≤ 40 trucks; ≤ 2×10⁶ events)",
    timeoutMs: 10000,
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
    timeoutMs: 10000,
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
    timeoutMs: 2000,
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
    timeoutMs: 2000,
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
    timeoutMs: 5000,
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
    timeoutMs: 10000,
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
    timeoutMs: 10000,
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
    timeoutMs: 30000,
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
    timeoutMs: 10000,
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
    timeoutMs: 10000,
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
    timeoutMs: 2000,
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
    timeoutMs: 5000,
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
    timeoutMs: 5000,
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
    timeoutMs: 10000,
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
    timeoutMs: 30000,
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
    timeoutMs: 10000,
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
    timeoutMs: 2000,
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
    timeoutMs: 30000,
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
    timeoutMs: 2000,
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
    timeoutMs: 5000,
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
    timeoutMs: 10000,
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
    timeoutMs: 2000,
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
    timeoutMs: 5000,
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
    timeoutMs: 10000,
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
    timeoutMs: 5000,
    t0Fallback: "baked volumes",
    gpuCompute: false,
  },
];

const BY_ID = new Map(ENGINE_REGISTRY.map((e) => [e.id, e]));

export function engineById(id: string): EngineEntry | undefined {
  return typeof id === "string" ? BY_ID.get(id) : undefined;
}

export const PARITY_NOT_CONFIRMED = "parity not confirmed \u2014 showing precomputed results";
export const NEEDS_WEBGPU = "needs WebGPU to compute live";

const VERDICTS = new Set(["pass", "fail", "not_run"]);

/** The report's entries when it is usable (an object with a non-empty list of well-formed entries), else null. */
function reportEntries(report: unknown): Array<{ engine: string; verdict: string }> | null {
  if (report === null || typeof report !== "object" || Array.isArray(report)) return null;
  const engines = (report as { engines?: unknown }).engines;
  if (!Array.isArray(engines) || engines.length === 0) return null;
  const out: Array<{ engine: string; verdict: string }> = [];
  for (const entry of engines) {
    if (entry === null || typeof entry !== "object" || Array.isArray(entry)) return null;
    const { engine, verdict } = entry as { engine?: unknown; verdict?: unknown };
    if (typeof engine !== "string" || typeof verdict !== "string" || !VERDICTS.has(verdict)) return null;
    out.push({ engine, verdict });
  }
  return out;
}

/** An engine is live only if the report lists it and every entry of it passes. Never throws. */
export function parityGate(engineId: string, report: unknown): { live: boolean; notice: string | null } {
  try {
    const entries = reportEntries(report);
    const mine = entries?.filter((e) => e.engine === engineId) ?? [];
    if (mine.length > 0 && mine.every((e) => e.verdict === "pass")) return { live: true, notice: null };
  } catch {
    // a hostile report confirms nothing
  }
  return { live: false, notice: PARITY_NOT_CONFIRMED };
}

export type EngineTier = "t1" | "t2" | "t0";

/** What an engine shows on a tier: the badge always follows what is shown (FR-018-14). */
export function engineMode(
  engineId: string,
  tier: EngineTier,
  report: unknown,
): { mode: "live" | "replay"; badge: "LIVE" | "REPLAY"; notice: string | null } {
  if (tier === "t0") return { mode: "replay", badge: "REPLAY", notice: null };
  if (tier === "t2" && engineById(engineId)?.gpuCompute) {
    return { mode: "replay", badge: "REPLAY", notice: NEEDS_WEBGPU };
  }
  const gate = parityGate(engineId, report);
  if (gate.live) return { mode: "live", badge: "LIVE", notice: null };
  return { mode: "replay", badge: "REPLAY", notice: gate.notice };
}
