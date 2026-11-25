// @vitest-environment node
//
// T-007-022 (TypeScript half) · unsupported features, invalid seeds and horizons, and the event budget in the twin: typed errors within 2 s and no partial results: FR-007-12, FR-007-13.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-12 (a scenario that uses a reference-engine feature outside the twin's declared feature set is refused with `UnsupportedFeature` naming the feature,
// and the web falls back to the baked trace with that reason; the features outside the set are underground units (LHDs), ore passes, shaft bins, a planning overlay and a routing zone penalty other than
// 0) and FR-007-13 (a seed that is not an integer in [0, 2^63), a horizon <= 0 s or > 7 days, or a run past 2 x 10^6 executed events stops within 2 s with `InvalidSeed`, `InvalidHorizon` or
// `EventBudgetExceeded` and returns no partial KPIs); `contracts/haul-scenario.schema.json` (`reference_only`). The Python half is tests/pipeline/test_t_007_022_adapter_limits.py.
//
// Oracle: hand-built bundles with one reference-only feature each; the boundaries 0, 2^63 - 1, 2^63 and 604,800 written out; `performance.now()` as the stopwatch.
//
// Expected API: `runShift(bundle, seed, { eventBudget })` of `~/engines/des/twin`; `DEFAULT_EVENT_BUDGET` (= 2_000_000) exported from the same module; `unsupportedFeatures(bundle): string[]` and
// `checkTwinFeatures(bundle): void` of `~/engines/des/scenario` with the order and rules of the Python `unsupported_features` / `check_twin_features`; errors `UnsupportedFeature` (attribute
// `features: string[]`), `InvalidSeed`, `InvalidHorizon`, `EventBudgetExceeded` of `~/engines/des/errors`. The seed is checked first. `runShift` accepts a bigint or a safe non-negative integer number.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { EventBudgetExceeded, InvalidHorizon, InvalidSeed, UnsupportedFeature } from "~/engines/des/errors";
import { checkTwinFeatures, unsupportedFeatures } from "~/engines/des/scenario";
import { DEFAULT_EVENT_BUDGET, runShift } from "~/engines/des/twin";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const EX = resolve(REPO, "specs/007-haulage-dispatch/contracts/examples");
// biome-ignore lint/suspicious/noExplicitAny: bundles are plain JSON here
type B = Record<string, any>;
const readJson = (n: string): B => JSON.parse(readFileSync(resolve(EX, n), "utf-8"));
const smoke = () => readJson("haul-scenario.valid.json");

const LHD = { id: 1, lhd_class: "LHD_14", drawpoints: [1], tip_node: 3, pass_id: 1 };
const PASS = { id: 1, chute_node: 3, capacity_t: 500 };
const BIN = { node: 4, capacity_t: 800, hoist_t_per_h: 600 };
const OVERLAY = { path: "plans/pit-plan.json", sha256: "a".repeat(64) };

function thrown(f: () => unknown): unknown {
  try {
    f();
  } catch (e) {
    return e;
  }
  return undefined;
}

describe("FR-007-12 · the twin's declared feature set", () => {
  const cases: [string, B | null, string[]][] = [
    ["none", null, []],
    ["zero penalty", { zone_penalty_s: 0 }, []],
    ["empty lists", { lhds: [], ore_passes: [] }, []],
    ["lhds", { lhds: [LHD] }, ["lhds"]],
    ["ore passes", { ore_passes: [PASS] }, ["ore_passes"]],
    ["shaft bin", { shaft_bin: BIN }, ["shaft_bin"]],
    ["planning overlay", { planning_overlay: OVERLAY }, ["planning_overlay"]],
    ["zone penalty", { zone_penalty_s: 5 }, ["zone_penalty_s"]],
    ["tiny zone penalty", { zone_penalty_s: 0.001 }, ["zone_penalty_s"]],
    [
      "all",
      { zone_penalty_s: 30, lhds: [LHD], shaft_bin: BIN, ore_passes: [PASS], planning_overlay: OVERLAY },
      ["lhds", "ore_passes", "shaft_bin", "planning_overlay", "zone_penalty_s"],
    ],
  ];
  for (const [name, ro, expected] of cases) {
    it(`FR-007-12 · ${name}`, () => {
      const b = smoke();
      if (ro) b.reference_only = ro;
      expect(unsupportedFeatures(b)).toEqual(expected);
      if (expected.length === 0) {
        expect(() => checkTwinFeatures(b)).not.toThrow();
        return;
      }
      const e = thrown(() => checkTwinFeatures(b));
      expect(e).toBeInstanceOf(UnsupportedFeature);
      expect((e as UnsupportedFeature).features).toEqual(expected);
      for (const f of expected) expect(String((e as Error).message)).toContain(f);
      const e2 = thrown(() => runShift(b, 1n)); // the twin refuses to run it
      expect(e2).toBeInstanceOf(UnsupportedFeature);
    });
  }

  it("FR-007-12 · the valid examples use no unsupported feature", () => {
    for (const n of [
      "haul-scenario.valid.json",
      "haul-scenario.valid-exponential.json",
      "haul-scenario.valid-traffic-lp.json",
    ])
      expect(unsupportedFeatures(readJson(n))).toEqual([]);
  });
});

describe("FR-007-13 · seeds", () => {
  const bad: unknown[] = [
    -1n,
    2n ** 63n,
    2n ** 63n + 1n,
    2n ** 100n,
    1.5,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    "7",
    null,
    undefined,
    true,
    false,
    [1],
    -0.5,
    2 ** 53,
  ];
  for (const seed of bad) {
    it(`FR-007-13 · seed ${String(seed)} is InvalidSeed within two seconds`, () => {
      const t0 = performance.now();
      const e = thrown(() => runShift(smoke(), seed as never));
      expect(e).toBeInstanceOf(InvalidSeed);
      expect(performance.now() - t0).toBeLessThan(2000);
    });
  }
  for (const seed of [0n, 1n, 2n ** 63n - 1n, 0, 5]) {
    it(`FR-007-13 · seed ${String(seed)} is accepted`, () => {
      expect(runShift(smoke(), seed).results.events_executed).toBe(8);
    });
  }
});

describe("FR-007-13 · horizons", () => {
  const bad: unknown[] = [0, -1, -3600, 604800.001, 1e9, Number.NaN, Number.POSITIVE_INFINITY, "900", null];
  for (const h of bad) {
    it(`FR-007-13 · horizon ${String(h)} is InvalidHorizon within two seconds`, () => {
      const b = smoke();
      b.horizon_s = h;
      const t0 = performance.now();
      expect(thrown(() => runShift(b, 1n))).toBeInstanceOf(InvalidHorizon);
      expect(performance.now() - t0).toBeLessThan(2000);
    });
  }
});

describe("FR-007-13 · the event budget", () => {
  it("FR-007-13 · the default budget is two million", () => {
    expect(DEFAULT_EVENT_BUDGET).toBe(2_000_000);
  });

  for (const budget of [1, 8, 500, 5000]) {
    it(`FR-007-13 · a week of traffic with a budget of ${budget} stops with EventBudgetExceeded within two seconds and returns nothing`, () => {
      const b = smoke();
      b.mode = "traffic";
      b.horizon_s = 7 * 24 * 3600;
      b.fleet = Array.from({ length: 8 }, (_, i) => ({
        id: i + 1,
        truck_class: "CAT_793F",
        start_loader: i % 2 === 0 ? 1 : 2,
      }));
      let result: unknown;
      const t0 = performance.now();
      const e = thrown(() => {
        result = runShift(b, 1n, { eventBudget: budget });
      });
      expect(e).toBeInstanceOf(EventBudgetExceeded);
      expect(performance.now() - t0).toBeLessThan(2000);
      expect(result).toBeUndefined();
    });
  }

  it("FR-007-13 · a run exactly at the budget completes, one event fewer stops", () => {
    const n = runShift(smoke(), 1n).results.events_executed;
    expect(runShift(smoke(), 1n, { eventBudget: n }).results.events_executed).toBe(n);
    expect(thrown(() => runShift(smoke(), 1n, { eventBudget: n - 1 }))).toBeInstanceOf(EventBudgetExceeded);
  });

  for (const budget of [0, -1, 1.5, Number.NaN, "100", null]) {
    it(`FR-007-13 · an invalid event budget ${String(budget)} is a RangeError`, () => {
      expect(thrown(() => runShift(smoke(), 1n, { eventBudget: budget as never }))).toBeInstanceOf(
        RangeError,
      );
    });
  }
});
