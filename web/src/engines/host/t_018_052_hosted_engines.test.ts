// T-018-052 [red] · FR-018-48: the engines specified by spec 007 (des, policies, haulage, lp, routing), spec 013 (dust-lidar) and
// spec 014 (il1-twin, il2-twin) run only through this spec's engine host and tiers, and the parity verdicts of their own suites
// (FR-007-10, FR-007-32, FR-007-15, FR-007-20, FR-007-39, P-013-15, FR-014-42) are written into the parity report (DC-018-05) so that
// FR-018-63 applies to them; a failing hosted engine runs in T0. E2E half: web/e2e/parity/t_018_052_hosted_report.spec.ts.
//
// Expected API (module `~/engines/host/hosted`, file web/src/engines/host/hosted.ts)
//   type HostedId = "des" | "policies" | "haulage" | "lp" | "routing" | "dust-lidar" | "il1-twin" | "il2-twin"
//   HOSTED_ENGINES: Readonly<Record<HostedId, { spec: "007" | "013" | "014"; definedBy: string }>>
//   hostedBackend(engineId: string, module: { run(request: unknown, ctx: { signal: AbortSignal }): Promise<unknown>; terminate(): void }):
//       EngineBackend of `~/engines/host/host`; throws a RangeError for an id that is not hosted
//   interface HostedSuiteResult { engine: string; version: string; definedBy: string; browsers: string[];
//        files: number; vectors: number; mismatches: number; verdict: "pass" | "fail" | "not_run"; reason?: string }
//   mergeHostedVerdicts(report: ParityReport, results: HostedSuiteResult[]): ParityReport
//       returns a NEW report (the input is untouched) with one entry per result, in the order given, appended to `report.engines`:
//       { engine, engine_version: version, tolerance: { class: "hosted", defined_by }, fixtures: { files, vectors },
//         max_error: { mismatches }, browsers, verdict, reason? } (`max_error` is omitted for not_run).
//       It throws (RangeError) for: an engine that is not hosted, a `definedBy` different from the owning requirement of the
//       engine, a pass with no browser, an empty fixture set (files or vectors < 1), a pass with mismatches > 0, a fail with 0
//       mismatches and no reason, a not_run without a reason, a browser outside chromium / firefox / webkit, an engine already listed
//       with class "hosted" in the report or twice in `results`.
//
// Oracles: the owning requirement per engine is the list in FR-018-48 and the checker rule of the parity-report schema ("hosted
// defined_by different from the owning requirement of the engine, e.g. des -> FR-007-10"); entry fields follow
// contracts/examples/parity-report.valid.json (des entry); the failing-engine rule is FR-018-63.
import { describe, expect, it, vi } from "vitest";
import {
  HOSTED_ENGINES,
  type HostedSuiteResult,
  hostedBackend,
  mergeHostedVerdicts,
} from "~/engines/host/hosted";
import { engineMode, parityGate } from "~/engines/registry";

const OWNER: Record<string, [string, string]> = {
  des: ["007", "FR-007-10"],
  policies: ["007", "FR-007-32"],
  haulage: ["007", "FR-007-15"],
  lp: ["007", "FR-007-20"],
  routing: ["007", "FR-007-39"],
  "dust-lidar": ["013", "P-013-15"],
  "il1-twin": ["014", "FR-014-42"],
  "il2-twin": ["014", "FR-014-42"],
};
const ALL3 = ["chromium", "firefox", "webkit"];

const emptyReport = () => ({
  schema_version: "1.0",
  git_sha: "3f2a9c1d4e5b6a7980c1d2e3f4a5b6c7d8e9f012",
  generated: "2026-10-07T12:00:00Z",
  engines: [
    {
      engine: "blasting",
      engine_version: "0.1.0",
      tolerance: { class: "analytical-closed-form", rtol: 1e-9, atol_scale: 1e-12 },
      fixtures: { files: 6, vectors: 1200 },
      max_error: { rel: 4.4e-15 },
      browsers: ALL3,
      verdict: "pass",
    },
  ],
});

const pass = (engine: string, over: Partial<HostedSuiteResult> = {}): HostedSuiteResult => ({
  engine,
  version: "0.1.0",
  definedBy: (OWNER[engine] as [string, string])[1],
  browsers: ALL3,
  files: 5,
  vectors: 5,
  mismatches: 0,
  verdict: "pass",
  ...over,
});

describe("the hosted engines (FR-018-48)", () => {
  it("FR-018-48 · exactly the eight engines of specs 007, 013 and 014 are hosted, each with its owning requirement", () => {
    expect(Object.keys(HOSTED_ENGINES).sort()).toEqual(Object.keys(OWNER).sort());
    for (const [id, [spec, req]] of Object.entries(OWNER)) {
      expect(HOSTED_ENGINES[id as keyof typeof HOSTED_ENGINES]).toEqual({ spec, definedBy: req });
    }
  });

  it("FR-018-48 · a hosted backend runs the owning module's code only through the module's run(), forwarding the abort signal", async () => {
    const run = vi.fn(async (_request: unknown, _ctx: { signal: AbortSignal }) => ({ kind: "output" }));
    const backend = hostedBackend("des", { run, terminate: vi.fn() });
    const ctrl = new AbortController();
    await backend.run({ kind: "input", engine: "des" } as never, { signal: ctrl.signal });
    expect(run).toHaveBeenCalledTimes(1);
    expect(run.mock.calls[0]?.[1].signal).toBe(ctrl.signal);
    backend.terminate();
  });

  it("FR-018-48 · terminate on the backend terminates the module", () => {
    const terminate = vi.fn();
    hostedBackend("policies", { run: async () => ({}), terminate }).terminate();
    expect(terminate).toHaveBeenCalledTimes(1);
  });

  it("FR-018-48 · an engine that is not hosted (geotech, an unknown id) cannot get a hosted backend", () => {
    for (const id of ["geotech", "gns", "nope", ""]) {
      expect(() => hostedBackend(id, { run: async () => ({}), terminate: () => undefined })).toThrow(
        RangeError,
      );
    }
  });
});

describe("merging the verdicts of the owning suites (FR-018-48, FR-018-63)", () => {
  it("FR-018-48 · a passing hosted suite becomes an entry of class hosted with the owning requirement, the browsers and the counts", () => {
    const merged = mergeHostedVerdicts(emptyReport(), [pass("des")]);
    expect(merged.engines).toHaveLength(2);
    expect(merged.engines[1]).toEqual({
      engine: "des",
      engine_version: "0.1.0",
      tolerance: { class: "hosted", defined_by: "FR-007-10" },
      fixtures: { files: 5, vectors: 5 },
      max_error: { mismatches: 0 },
      browsers: ALL3,
      verdict: "pass",
    });
  });

  it("FR-018-48 · all eight hosted engines can be merged in one call, in the given order, with their own requirement", () => {
    const merged = mergeHostedVerdicts(
      emptyReport(),
      Object.keys(OWNER).map((id) => pass(id)),
    );
    const hosted = merged.engines.slice(1);
    expect(hosted.map((e: { engine: string }) => e.engine)).toEqual(Object.keys(OWNER));
    for (const e of hosted as Array<{ engine: string; tolerance: { class: string; defined_by: string } }>) {
      expect(e.tolerance).toEqual({ class: "hosted", defined_by: (OWNER[e.engine] as [string, string])[1] });
    }
  });

  it("FR-018-48 · the input report is not modified", () => {
    const base = emptyReport();
    const before = structuredClone(base);
    mergeHostedVerdicts(base, [pass("lp")]);
    expect(base).toEqual(before);
  });

  it("FR-018-48 · a failing suite keeps its mismatch count and reason, and a not-run suite carries a reason and no error", () => {
    const failing = mergeHostedVerdicts(emptyReport(), [
      pass("routing", {
        verdict: "fail",
        mismatches: 2,
        reason: "route cost differs on 2 of 5 vectors in webkit",
      }),
    ]).engines[1];
    expect(failing).toMatchObject({ engine: "routing", verdict: "fail", max_error: { mismatches: 2 } });
    expect(failing.reason).toContain("webkit");
    const notRun = mergeHostedVerdicts(emptyReport(), [
      pass("il1-twin", { verdict: "not_run", browsers: [], reason: "twin bundle not built yet" }),
    ]).engines[1];
    expect(notRun.verdict).toBe("not_run");
    expect(notRun.reason).toBe("twin bundle not built yet");
    expect("max_error" in notRun).toBe(false);
  });

  const hostile: Array<[string, HostedSuiteResult[]]> = [
    ["an engine that is not hosted", [pass("des", { engine: "geotech" })]],
    ["a requirement that is not the owning one", [pass("des", { definedBy: "FR-007-15" })]],
    ["a requirement of another spec", [pass("dust-lidar", { definedBy: "FR-007-10" })]],
    ["a pass in no browser", [pass("des", { browsers: [] })]],
    ["an unknown browser", [pass("des", { browsers: ["chromium", "netscape"] })]],
    ["an empty fixture set (no files)", [pass("des", { files: 0 })]],
    ["an empty fixture set (no vectors)", [pass("des", { vectors: 0 })]],
    ["a pass with mismatches", [pass("des", { mismatches: 1 })]],
    ["a fail without mismatches and without a reason", [pass("des", { verdict: "fail", mismatches: 0 })]],
    ["a not_run without a reason", [pass("des", { verdict: "not_run", browsers: [] })]],
    ["the same engine twice", [pass("des"), pass("des")]],
    ["a negative count", [pass("des", { vectors: -1 })]],
    ["a fractional count", [pass("des", { files: 1.5 })]],
    ["a non-finite count", [pass("des", { mismatches: Number.NaN })]],
  ];
  for (const [name, results] of hostile) {
    it(`FR-018-67 · merging ${name} throws a RangeError and leaves nothing half-written`, () => {
      const base = emptyReport();
      const before = structuredClone(base);
      expect(() => mergeHostedVerdicts(base, results)).toThrow(RangeError);
      expect(base).toEqual(before);
    });
  }

  it("FR-018-67 · an engine already listed as hosted in the report cannot be merged again", () => {
    const once = mergeHostedVerdicts(emptyReport(), [pass("lp")]);
    expect(() => mergeHostedVerdicts(once, [pass("lp")])).toThrow(RangeError);
  });
});

describe("a failing hosted engine runs in T0 (FR-018-63)", () => {
  it("FR-018-63 · after merging, a passing hosted engine is LIVE on T2 and a failing one shows REPLAY with the parity notice", () => {
    const merged = mergeHostedVerdicts(emptyReport(), [
      pass("des"),
      pass("lp", { verdict: "fail", mismatches: 1, reason: "objective differs" }),
    ]);
    expect(parityGate("des", merged).live).toBe(true);
    expect(engineMode("des", "t2", merged).badge).toBe("LIVE");
    expect(parityGate("lp", merged).live).toBe(false);
    expect(engineMode("lp", "t2", merged)).toMatchObject({ mode: "replay", badge: "REPLAY" });
    expect(engineMode("lp", "t2", merged).notice).toContain("parity not confirmed");
  });

  it("FR-018-63 · a hosted engine missing from the report is not LIVE either", () => {
    const merged = mergeHostedVerdicts(emptyReport(), [pass("des")]);
    expect(parityGate("haulage", merged).live).toBe(false);
  });
});
