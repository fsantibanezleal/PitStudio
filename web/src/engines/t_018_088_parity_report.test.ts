// T-018-088 [red] · SC-018-01 and FR-018-67: parity-report completeness at the web gate. Every engine of section 7.1 either passes its parity class or is shown in T0 and
// listed as such, and an invalid report or measurement file fails the build, naming the problem.
//
// Expected API (module `~/engines/parityReport`, file web/src/engines/parityReport.ts)
//     interface Problem { rule: string; engine?: string; message: string }
//     checkParityReport(report: unknown, opts: { commit: string; engines?: readonly string[] }): Problem[]       empty list = valid
//         rules: "schema" (the report fails DC-018-05), "commit-mismatch" (git_sha different from `opts.commit`, the deployed commit), "engine-missing" (an engine of
//         `opts.engines` has no entry), "verdict-inconsistent" (the verdict contradicts max_error and the tolerance of its class: pass with an error above the tolerance,
//         fail with every error within it), "class-not-allowed" (a class the engine's system class of section 7.2 does not allow), "hosted-owner-mismatch" (a hosted
//         entry whose `defined_by` is not the owning requirement of its engine), "duplicate-entry" (the same engine and class twice). Each problem names its engine.
//     checkLaneMeasurements(doc: unknown, opts?: { engines?: readonly string[]; artefacts?: readonly string[] }): Problem[]
//         rules: "schema" (fails DC-018-06), "engine-missing" (an engine of `opts.engines` has no entry), "duplicate-entry", "unknown-artefact" (an artefact entry whose
//         id is not in `opts.artefacts`)
//     parityStatus(report: unknown, engines: readonly string[]): Array<{ engine: string; status: "pass" | "t0"; reason: "pass" | "failing" | "not-run" | "not-listed" | "invalid" }>
//         one row per engine, in the order given: "pass" iff every report entry of the engine has verdict "pass"; otherwise "t0" with the reason; an invalid or missing
//         report gives "t0" / "invalid" for every engine
//
// Oracles (independent of the code under test): the spec's own example corpus (contracts/examples/parity-report.valid.json and its 15 hostile variants,
// lane-measurements.valid.json and its 14 hostile variants, each hostile one rejected by the schema at the pointer the author states); the checker classes listed for the
// two schemas in contracts/examples/index.json; the parity classes allowed per engine in section 7.2 (transcribed below); the owning requirements of FR-018-48.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { checkLaneMeasurements, checkParityReport, parityStatus } from "~/engines/parityReport";
import { ENGINE_IDS } from "~/test-support/engine-examples";

const EXAMPLES = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../specs/018-web-cases/contracts/examples",
);
const read = (name: string) =>
  JSON.parse(readFileSync(resolve(EXAMPLES, name), "utf8")) as Record<string, any>;
const valid = () => read("parity-report.valid.json");
const SHA = "3f2a9c1d4e5b6a7980c1d2e3f4a5b6c7d8e9f012";
const PRESENT = ["blasting", "geotech", "mincut", "swe", "des", "gns", "detector"];
const check = (r: unknown, over: { commit?: string; engines?: readonly string[] } = {}) =>
  checkParityReport(r, { commit: SHA, engines: PRESENT, ...over });
const rules = (ps: Array<{ rule: string }>) => ps.map((p) => p.rule).sort();

describe("the valid report and its hostile corpus (FR-018-67)", () => {
  it("FR-018-67 · the valid example report of the spec has no problem for the commit it names and the engines it lists", () => {
    expect(check(valid())).toEqual([]);
  });

  const hostile = readdirSync(EXAMPLES).filter((f) => /^parity-report\.hostile-.*\.json$/.test(f));
  it("FR-018-67 · the corpus holds 15 hostile reports", () => {
    expect(hostile).toHaveLength(15);
  });
  for (const file of hostile) {
    it(`FR-018-67 · ${file} fails the build with a schema problem`, () => {
      const problems = check(read(file), { commit: valid().git_sha, engines: undefined });
      expect(problems.length, JSON.stringify(problems)).toBeGreaterThan(0);
      expect(
        problems.some((p) => p.rule === "schema"),
        JSON.stringify(problems),
      ).toBe(true);
    });
  }

  it("FR-018-67 · a report that is not an object (null, a string, an array, a number) is a schema problem, never an exception", () => {
    for (const bad of [null, undefined, "report", [], 7, true]) {
      let out: Array<{ rule: string }> = [];
      expect(() => {
        out = check(bad);
      }).not.toThrow();
      expect(rules(out)).toContain("schema");
    }
  });
});

describe("checker rules beyond the schema (SC-018-01, FR-018-48, FR-018-63)", () => {
  it("FR-018-63 · a report whose git_sha is not the deployed commit is rejected", () => {
    expect(rules(check(valid(), { commit: "a".repeat(40) }))).toEqual(["commit-mismatch"]);
  });

  it("SC-018-01 · an engine of the engine table missing from the report is reported, once per engine", () => {
    const missing = checkParityReport(valid(), { commit: SHA, engines: ENGINE_IDS });
    const names = missing
      .filter((p) => p.rule === "engine-missing")
      .map((p) => p.engine)
      .sort();
    expect(names).toEqual(ENGINE_IDS.filter((e) => !PRESENT.includes(e)).sort());
    expect(names).toHaveLength(18);
  });

  it("FR-018-67 · a verdict that contradicts the error and the tolerance is reported: pass with an error above the tolerance, and fail with every error within it", () => {
    const passButOver = valid();
    passButOver.engines.find((e: any) => e.engine === "gns").max_error.abs = 2e-4; // tolerance max_abs 1e-4
    expect(check(passButOver)).toEqual([
      expect.objectContaining({ rule: "verdict-inconsistent", engine: "gns" }),
    ]);

    const closedFormOver = valid();
    closedFormOver.engines.find((e: any) => e.engine === "blasting").max_error.rel = 1e-7; // rtol 1e-9
    expect(check(closedFormOver)).toEqual([
      expect.objectContaining({ rule: "verdict-inconsistent", engine: "blasting" }),
    ]);

    const detectorPass = valid();
    detectorPass.engines.find((e: any) => e.engine === "detector").verdict = "pass"; // abs_px 0.71 > 0.5
    expect(check(detectorPass)).toEqual([
      expect.objectContaining({ rule: "verdict-inconsistent", engine: "detector" }),
    ]);

    const failButWithin = valid();
    failButWithin.engines.find((e: any) => e.engine === "blasting").verdict = "fail"; // rel 4.4e-15 <= 1e-9
    expect(check(failButWithin)).toEqual([
      expect.objectContaining({ rule: "verdict-inconsistent", engine: "blasting" }),
    ]);

    const mincutMismatch = valid();
    mincutMismatch.engines.find((e: any) => e.engine === "mincut").max_error.mismatches = 1; // an exact set is required
    expect(check(mincutMismatch)).toEqual([
      expect.objectContaining({ rule: "verdict-inconsistent", engine: "mincut" }),
    ]);
  });

  it("SC-018-01 · a class the engine's system class does not allow is reported (a WGSL class on an analytical engine, an analytical class on an ML model)", () => {
    const wrongClass = valid();
    const blasting = wrongClass.engines.find((e: any) => e.engine === "blasting");
    blasting.tolerance = { class: "wgsl-kernel", max_abs: 0.001 };
    blasting.max_error = { abs: 0.0001 };
    expect(rules(check(wrongClass))).toEqual(["class-not-allowed"]);
    const mlWrong = valid();
    const gns = mlWrong.engines.find((e: any) => e.engine === "gns");
    gns.tolerance = { class: "analytical-closed-form", rtol: 1e-9, atol_scale: 1e-12 };
    gns.max_error = { rel: 1e-12 };
    expect(rules(check(mlWrong))).toEqual(["class-not-allowed"]);
  });

  it("FR-018-48 · a hosted entry must name the owning requirement of its engine (des -> FR-007-10): FR-007-15 is a problem", () => {
    const wrongOwner = valid();
    wrongOwner.engines.find((e: any) => e.engine === "des").tolerance.defined_by = "FR-007-15";
    expect(check(wrongOwner)).toEqual([
      expect.objectContaining({ rule: "hosted-owner-mismatch", engine: "des" }),
    ]);
  });

  it("FR-018-63 · the same engine and class listed twice is a duplicate entry", () => {
    const twice = valid();
    twice.engines.push(structuredClone(twice.engines.find((e: any) => e.engine === "geotech")));
    expect(check(twice)).toEqual([expect.objectContaining({ rule: "duplicate-entry", engine: "geotech" })]);
  });

  it("FR-018-63 · the same engine with two different classes (granular kernels and observables) is allowed", () => {
    const two = valid();
    two.engines.push({
      engine: "granular",
      engine_version: "0.1.0",
      tolerance: { class: "wgsl-observables", observables: { repose_deg: 1.5, runout_rel: 0.05 } },
      fixtures: { files: 2, vectors: 2 },
      browsers: [],
      verdict: "not_run",
      reason: "no WebGPU adapter on the CI runner; runs in the webgpu project only",
    });
    expect(checkParityReport(two, { commit: SHA, engines: [...PRESENT, "granular"] })).toEqual([]);
  });
});

describe("completeness: every engine passes or is shown in T0 (SC-018-01)", () => {
  it("SC-018-01 · on the example report 5 engines pass and the other 20 are shown in T0 with their reason: failing (detector), not run (swe), not listed (the rest)", () => {
    const rows = parityStatus(valid(), ENGINE_IDS);
    expect(rows.map((r) => r.engine)).toEqual([...ENGINE_IDS]);
    expect(
      rows
        .filter((r) => r.status === "pass")
        .map((r) => r.engine)
        .sort(),
    ).toEqual(["blasting", "des", "geotech", "gns", "mincut"]);
    expect(rows.filter((r) => r.status === "t0")).toHaveLength(20);
    expect(rows.every((r) => r.status === "pass" || r.status === "t0")).toBe(true);
    const reason = (id: string) => rows.find((r) => r.engine === id)?.reason;
    expect(reason("detector")).toBe("failing");
    expect(reason("swe")).toBe("not-run");
    expect(reason("plume")).toBe("not-listed");
    expect(reason("blasting")).toBe("pass");
  });

  it("SC-018-01 · an engine with one passing and one failing entry is shown in T0", () => {
    const r = valid();
    r.engines.push({
      ...structuredClone(r.engines.find((e: any) => e.engine === "blasting")),
      tolerance: { class: "analytical-iterative", rtol: 1e-8, atol_scale: 1e-12, solver_tol: 1e-9 },
      verdict: "fail",
      max_error: { rel: 1e-5 },
    });
    expect(parityStatus(r, ["blasting"])).toEqual([{ engine: "blasting", status: "t0", reason: "failing" }]);
  });

  it("SC-018-01 · an invalid or missing report puts every engine in T0 with the reason invalid", () => {
    for (const bad of [null, undefined, {}, { engines: "x" }]) {
      const rows = parityStatus(bad, ["des", "gns"]);
      expect(rows).toEqual([
        { engine: "des", status: "t0", reason: "invalid" },
        { engine: "gns", status: "t0", reason: "invalid" },
      ]);
    }
  });
});

describe("the lane-measurement file (FR-018-64, FR-018-66, FR-018-67)", () => {
  const lane = () => read("lane-measurements.valid.json");
  it("FR-018-67 · the valid example has no problem", () => {
    expect(checkLaneMeasurements(lane())).toEqual([]);
  });

  const hostile = readdirSync(EXAMPLES).filter((f) => /^lane-measurements\.hostile-.*\.json$/.test(f));
  it("FR-018-67 · the corpus holds 14 hostile measurement files", () => {
    expect(hostile).toHaveLength(14);
  });
  for (const file of hostile) {
    it(`FR-018-67 · ${file} fails the build with a schema problem`, () => {
      const problems = checkLaneMeasurements(read(file));
      expect(
        problems.some((p) => p.rule === "schema"),
        JSON.stringify(problems),
      ).toBe(true);
    });
  }

  it("FR-018-64 · an engine of the engine table without an entry is reported, an artefact the manifest does not list is unknown, a repeated subject is a duplicate", () => {
    const doc = lane();
    const engines = ["des", "geotech", "granular", "gns", "plume"];
    expect(
      checkLaneMeasurements(doc, { engines })
        .filter((p) => p.rule === "engine-missing")
        .map((p) => p.engine),
    ).toEqual(["plume"]);
    expect(checkLaneMeasurements(doc, { artefacts: ["something-else"] }).map((p) => p.rule)).toEqual([
      "unknown-artefact",
    ]);
    expect(checkLaneMeasurements(doc, { artefacts: ["a3-granular-replay"] })).toEqual([]);
    doc.entries.push(structuredClone(doc.entries[0]));
    expect(checkLaneMeasurements(doc).map((p) => p.rule)).toContain("duplicate-entry");
  });

  it("FR-018-67 · a non-object, an empty object and a file without entries are schema problems, never exceptions", () => {
    for (const bad of [null, undefined, "x", [], {}, { entries: [] }]) {
      let out: Array<{ rule: string }> = [];
      expect(() => {
        out = checkLaneMeasurements(bad);
      }).not.toThrow();
      expect(rules(out)).toContain("schema");
    }
  });
});
