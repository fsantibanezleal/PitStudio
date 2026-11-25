// T-018-080 [red] · FR-018-65 (`deriveLane` and its agreement with spec 001's lane gate on its conformance corpus), P-018-71 (monotonicity), P-018-72 (inclusive
// boundaries, hand table of 16 cases), P-018-73 (disjunction of the two time conditions).
//
// Expected API (module `~/lane/derive`, file web/src/lane/derive.ts)
//     interface LaneMeasurements { web_drivable: boolean; max_asset_bytes: number; interaction_ms: number | null; run_ms_t2: number | null; trace_bytes: number | null }
//     deriveLane(m: LaneMeasurements): "live" | "replay"
//         live iff m.web_drivable === true, max_asset_bytes <= 25,000,000, (interaction_ms <= 16 or run_ms_t2 <= 1,000), and (trace_bytes is null or <= 10,000,000); replay
//         otherwise. Any missing, negative or non-finite measurement (and any value that is not a number) fails ITS OWN condition: a bad interaction time does not
//         veto a good run time and vice versa, a bad asset or trace size vetoes `live`. `null` for interaction_ms or run_ms_t2 means "not measured" (fails that
//         disjunct); `null` for trace_bytes means "no trace" (passes). Never throws, whatever its argument is (null, a non-object, extra keys).
//   The thresholds are the `lane_gate.*` keys of specs/000-foundation/thresholds.yaml (25 MB, 16 ms, 1 s, 10 MB; MB = 10^6 bytes), read in this file as the oracle's constants.
//
// Oracles (independent of the code under test): the gate written in data-model 001 section 2.6 and FR-018-65; the hand table below; thresholds.yaml; the conformance corpus
// of spec 001 (DC-001-08, tests/contract/fixtures/manifest/{valid,invalid}/), whose valid manifests label every measured artefact with the lane the gate gives, and whose
// `manifest.hostile-web-lane-mismatch.json` labels one with a lane the gate does not give.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { deriveLane } from "~/lane/derive";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
type M = {
  web_drivable: unknown;
  max_asset_bytes: unknown;
  interaction_ms: unknown;
  run_ms_t2: unknown;
  trace_bytes: unknown;
};
const base: M = {
  web_drivable: true,
  max_asset_bytes: 1_000_000,
  interaction_ms: 4,
  run_ms_t2: 120,
  trace_bytes: null,
};
const d = (over: Partial<M>) => deriveLane({ ...base, ...over } as never);

describe("the gate and its thresholds (FR-018-65)", () => {
  it("FR-018-65 · the thresholds the tests use are the lane_gate keys of thresholds.yaml: 25 MB, 16 ms, 1 s, 10 MB", () => {
    const text = readFileSync(resolve(REPO, "specs/000-foundation/thresholds.yaml"), "utf8");
    const block = text.slice(text.indexOf("lane_gate:"));
    const num = (key: string) => Number(new RegExp(`${key}:\\s*([0-9.]+)`).exec(block)?.[1]);
    expect(num("live_asset_mb_max")).toBe(25);
    expect(num("interaction_ms_max")).toBe(16);
    expect(num("run_s_max")).toBe(1);
    expect(num("trace_mb_max")).toBe(10);
  });
});

describe("hand table of boundary cases (P-018-72, FR-018-65)", () => {
  const live: M = {
    web_drivable: true,
    max_asset_bytes: 25_000_000,
    interaction_ms: 16,
    run_ms_t2: null,
    trace_bytes: 10_000_000,
  };
  const table: Array<[string, Partial<M>, "live" | "replay"]> = [
    ["exactly 25 MB, 16 ms and 10 MB", {}, "live"],
    ["asset 25,000,001 bytes", { max_asset_bytes: 25_000_001 }, "replay"],
    ["interaction 16.000001 ms and no run", { interaction_ms: 16.000001 }, "replay"],
    ["run exactly 1,000 ms and no interaction", { interaction_ms: null, run_ms_t2: 1000 }, "live"],
    ["run 1,000.001 ms and no interaction", { interaction_ms: null, run_ms_t2: 1000.001 }, "replay"],
    ["trace 10,000,001 bytes", { trace_bytes: 10_000_001 }, "replay"],
    ["no trace (null)", { trace_bytes: null }, "live"],
    ["trace 0 bytes", { trace_bytes: 0 }, "live"],
    ["not web drivable", { web_drivable: false }, "replay"],
    ["interaction good, run bad", { interaction_ms: 16, run_ms_t2: 5000 }, "live"],
    ["interaction bad, run good", { interaction_ms: 50, run_ms_t2: 1000 }, "live"],
    ["interaction and run both bad", { interaction_ms: 17, run_ms_t2: 1001 }, "replay"],
    ["interaction and run both missing", { interaction_ms: null, run_ms_t2: null }, "replay"],
    ["asset 0 bytes, interaction 0 ms", { max_asset_bytes: 0, interaction_ms: 0 }, "live"],
    [
      "everything zero and the run at 0 ms",
      { max_asset_bytes: 0, interaction_ms: null, run_ms_t2: 0, trace_bytes: 0 },
      "live",
    ],
    [
      "asset exactly at the limit but trace over",
      { max_asset_bytes: 25_000_000, trace_bytes: 10_000_001 },
      "replay",
    ],
  ];
  expect(table).toHaveLength(16);
  for (const [name, over, expected] of table) {
    it(`P-018-72 · ${name} -> ${expected}`, () => {
      expect(deriveLane({ ...live, ...over } as never)).toBe(expected);
    });
  }
});

describe("missing, negative and non-finite measurements (FR-018-65)", () => {
  const bad = [
    Number.NaN,
    Number.POSITIVE_INFINITY,
    Number.NEGATIVE_INFINITY,
    -1,
    -0.001,
    "16",
    true,
    {},
    [] as unknown[],
  ];
  for (const value of bad) {
    const label = typeof value === "object" ? JSON.stringify(value) : String(value);
    it(`FR-018-65 · a bad asset size (${label}) is replay`, () => {
      expect(d({ max_asset_bytes: value })).toBe("replay");
    });
    it(`FR-018-65 · a bad trace size (${label}) is replay`, () => {
      expect(d({ trace_bytes: value })).toBe("replay");
    });
    it(`FR-018-65 · a bad interaction time (${label}) fails only its own disjunct: replay without a good run time, live with one`, () => {
      expect(d({ interaction_ms: value, run_ms_t2: null })).toBe("replay");
      expect(d({ interaction_ms: value, run_ms_t2: 500 })).toBe("live");
    });
    it(`FR-018-65 · a bad run time (${label}) fails only its own disjunct`, () => {
      expect(d({ interaction_ms: null, run_ms_t2: value })).toBe("replay");
      expect(d({ interaction_ms: 4, run_ms_t2: value })).toBe("live");
    });
  }

  it("FR-018-65 · a missing (undefined) field fails its condition: no asset size, no interaction and run time", () => {
    const { max_asset_bytes: _a, ...noAsset } = base;
    expect(deriveLane(noAsset as never)).toBe("replay");
    expect(deriveLane({ web_drivable: true, max_asset_bytes: 1 } as never)).toBe("replay");
  });

  it("FR-018-65 · web_drivable must be the boolean true: 1, 'true' and undefined are not", () => {
    for (const v of [1, "true", undefined, null]) expect(d({ web_drivable: v })).toBe("replay");
  });

  it("FR-018-65 · it never throws, whatever the argument", () => {
    for (const v of [null, undefined, 0, "live", [], {}, () => 1, Symbol("x")]) {
      let out: unknown;
      expect(() => {
        out = deriveLane(v as never);
      }).not.toThrow();
      expect(out).toBe("replay");
    }
  });

  it("FR-018-65 · extra keys are ignored", () => {
    expect(deriveLane({ ...base, note: "x", measured: { tier: "T2" } } as never)).toBe("live");
  });
});

describe("properties (P-018-71, P-018-73)", () => {
  const sizeArb = fc.oneof(
    fc.double({ min: 0, max: 4e7, noNaN: true }),
    fc.constantFrom(Number.NaN, -1, 25_000_000, 25_000_001, 0),
  );
  const msArb = fc.oneof(
    fc.constant(null),
    fc.double({ min: 0, max: 5000, noNaN: true }),
    fc.constantFrom(Number.NaN, -1, 16, 1000),
  );
  const traceArb = fc.oneof(
    fc.constant(null),
    fc.double({ min: 0, max: 2e7, noNaN: true }),
    fc.constantFrom(Number.NaN, 10_000_000, 10_000_001),
  );
  const mArb = fc.record({
    web_drivable: fc.boolean(),
    max_asset_bytes: sizeArb,
    interaction_ms: msArb,
    run_ms_t2: msArb,
    trace_bytes: traceArb,
  });

  it("P-018-71 · monotonicity: decreasing any size or time never turns live into replay (random measurements, NaN included)", () => {
    fc.assert(
      fc.property(
        mArb,
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (m, a, b, c, e) => {
          if (deriveLane(m as never) !== "live") return true;
          const shrink = (v: number | null, f: number) => (v === null ? null : v * f);
          const smaller = {
            ...m,
            max_asset_bytes: m.max_asset_bytes * a,
            interaction_ms: shrink(m.interaction_ms, b),
            run_ms_t2: shrink(m.run_ms_t2, c),
            trace_bytes: shrink(m.trace_bytes, e),
          };
          return deriveLane(smaller as never) === "live";
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-73 · with the other conditions met, either interaction <= 16 ms or run <= 1,000 ms suffices (and one of them is needed)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 100, noNaN: true }),
        fc.double({ min: 0, max: 5000, noNaN: true }),
        fc.boolean(),
        fc.boolean(),
        (i, r, haveI, haveR) => {
          const m = {
            web_drivable: true,
            max_asset_bytes: 1000,
            interaction_ms: haveI ? i : null,
            run_ms_t2: haveR ? r : null,
            trace_bytes: null,
          };
          const want = (haveI && i <= 16) || (haveR && r <= 1000);
          return deriveLane(m as never) === (want ? "live" : "replay");
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-65 · the result is exactly the gate formula on arbitrary measurements (oracle written in this file)", () => {
    const gate = (m: {
      web_drivable: boolean;
      max_asset_bytes: number;
      interaction_ms: number | null;
      run_ms_t2: number | null;
      trace_bytes: number | null;
    }) => {
      const ok = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0;
      const asset = ok(m.max_asset_bytes) && m.max_asset_bytes <= 25_000_000;
      const time =
        (ok(m.interaction_ms) && (m.interaction_ms as number) <= 16) ||
        (ok(m.run_ms_t2) && (m.run_ms_t2 as number) <= 1000);
      const trace = m.trace_bytes === null || (ok(m.trace_bytes) && (m.trace_bytes as number) <= 10_000_000);
      return m.web_drivable === true && asset && time && trace ? "live" : "replay";
    };
    fc.assert(
      fc.property(mArb, (m) => deriveLane(m as never) === gate(m)),
      { numRuns: 200 },
    );
  });
});

describe("agreement with spec 001's lane gate (FR-018-65, DC-001-08)", () => {
  const dir = resolve(REPO, "tests/contract/fixtures/manifest");
  /** Every object with both `lane` and `lane_measurements`, wherever it sits in the document. */
  function labelled(
    node: unknown,
    out: Array<{ lane: string; m: unknown; where: string }> = [],
    where = "$",
  ): Array<{ lane: string; m: unknown; where: string }> {
    if (Array.isArray(node)) {
      for (const [i, v] of node.entries()) labelled(v, out, `${where}[${i}]`);
    } else if (node !== null && typeof node === "object") {
      const o = node as Record<string, unknown>;
      if (typeof o.lane === "string" && o.lane_measurements !== undefined)
        out.push({ lane: o.lane, m: o.lane_measurements, where });
      for (const [k, v] of Object.entries(o)) labelled(v, out, `${where}.${k}`);
    }
    return out;
  }
  const load = (sub: string) =>
    existsSync(resolve(dir, sub))
      ? readdirSync(resolve(dir, sub))
          .filter((f) => f.endsWith(".json"))
          .map((f) => ({ file: `${sub}/${f}`, text: readFileSync(resolve(dir, sub, f), "utf8") }))
      : [];

  it("FR-018-65 · the conformance corpus of spec 001 is present with valid web manifests that carry measured artefacts", () => {
    expect(existsSync(dir), "tests/contract/fixtures/manifest exists (T-001-004)").toBe(true);
    const all = load("valid").flatMap(({ file, text }) => {
      try {
        return labelled(JSON.parse(text)).map((x) => ({ ...x, file }));
      } catch {
        return [];
      }
    });
    expect(all.length, "valid manifests with measured artefacts").toBeGreaterThan(0);
  });

  it("FR-018-65 · every valid manifest's measured artefact has the lane deriveLane gives", () => {
    for (const { file, text } of load("valid")) {
      let doc: unknown;
      try {
        doc = JSON.parse(text);
      } catch {
        continue;
      }
      for (const { lane, m, where } of labelled(doc)) {
        const mm = m as { run_ms_t2?: unknown; interaction_ms?: unknown };
        const normalised = {
          ...(m as object),
          trace_bytes: (m as { trace_bytes?: unknown }).trace_bytes ?? null,
          run_ms_t2: mm.run_ms_t2 ?? null,
          interaction_ms: mm.interaction_ms ?? null,
        };
        expect(deriveLane(normalised as never), `${file} ${where}`).toBe(lane);
      }
    }
  });

  it("FR-018-65 · the lane-mismatch hostile manifest holds an artefact whose label differs from deriveLane", () => {
    const entry = load("invalid").find((e) => e.file.includes("web-lane-mismatch"));
    expect(entry, "manifest.hostile-web-lane-mismatch.json exists").toBeDefined();
    const mismatches = labelled(JSON.parse(entry?.text ?? "null")).filter(({ lane, m }) => {
      const mm = m as { run_ms_t2?: unknown; interaction_ms?: unknown; trace_bytes?: unknown };
      return (
        deriveLane({
          ...(m as object),
          trace_bytes: mm.trace_bytes ?? null,
          run_ms_t2: mm.run_ms_t2 ?? null,
          interaction_ms: mm.interaction_ms ?? null,
        } as never) !== lane
      );
    });
    expect(mismatches.length).toBeGreaterThan(0);
  });
});
