// Envelope decisions of the 011 surrogates (FR-011-11, FR-011-39, NFR-011-03) and the step-time bookkeeping (NFR-011-02).
// Oracles: the `training_envelope` of the contract examples read from disk (not copied here), hand-picked limits, hand medians.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { median, particleCap, StepTimer } from "~/engines/gns/stepTime";
import {
  FNO_ENVELOPE,
  fnoIsExtrapolation,
  fnoIsLive,
  GNS_ENVELOPE,
  gnsIsExtrapolation,
  insideRange,
} from "./envelope";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../../../specs/011-surrogates/contracts/examples");
type Range = { min: number; max: number };
type Envelope = Record<string, Range>;
const load = (name: string): Envelope =>
  (JSON.parse(readFileSync(join(EXAMPLES, name), "utf8")) as { training_envelope: Envelope })
    .training_envelope;

describe("the envelopes are those of the contract examples (DC-011-02)", () => {
  it("every GNS family parameter has the range of surrogate-io.valid.json", () => {
    const doc = load("surrogate-io.valid.json");
    for (const family of Object.values(GNS_ENVELOPE))
      for (const [name, range] of Object.entries(family))
        expect(range).toEqual({ min: (doc[name] as Range).min, max: (doc[name] as Range).max });
  });

  it("every C2 parameter has the range of surrogate-io.valid-fno.json", () => {
    const doc = load("surrogate-io.valid-fno.json");
    for (const name of ["breach_row", "breach_col", "release_volume", "yield_stress", "plastic_viscosity"])
      expect(FNO_ENVELOPE[name]).toEqual({
        min: (doc[name] as { min: number }).min,
        max: (doc[name] as { max: number }).max,
      });
  });
});

describe("range membership", () => {
  it("includes both limits and excludes anything else, NaN and infinities included", () => {
    const r = { min: 0.5, max: 4 };
    for (const v of [0.5, 4, 2]) expect(insideRange(v, r)).toBe(true);
    for (const v of [0.4999, 4.0001, 6, Number.NaN, Number.POSITIVE_INFINITY])
      expect(insideRange(v, r)).toBe(false);
  });
});

describe("FR-011-11 GNS extrapolation", () => {
  it("aspect ratio 0.5 and 4 are inside, 6 is outside", () => {
    const base = { column_width: 0.5 };
    expect(gnsIsExtrapolation("column-collapse", { ...base, column_aspect_ratio: 0.5 })).toBe(false);
    expect(gnsIsExtrapolation("column-collapse", { ...base, column_aspect_ratio: 4 })).toBe(false);
    expect(gnsIsExtrapolation("column-collapse", { ...base, column_aspect_ratio: 6 })).toBe(true);
  });

  it("a missing parameter and an unknown family count as extrapolation", () => {
    expect(gnsIsExtrapolation("column-collapse", { column_aspect_ratio: 1 })).toBe(true);
    expect(gnsIsExtrapolation("nope" as never, {})).toBe(true);
  });
});

describe("FR-011-39 FNO extrapolation", () => {
  const names = ["breach_row", "breach_col", "release_volume", "yield_stress", "plastic_viscosity"];
  const inside = {
    breach_row: 32,
    breach_col: 32,
    release_volume: 1e5,
    yield_stress: 100,
    plastic_viscosity: 0.5,
  };
  it("limits of the range are inside; 500 Pa is outside", () => {
    for (const v of [10, 200]) expect(fnoIsExtrapolation(names, { ...inside, yield_stress: v })).toBe(false);
    expect(fnoIsExtrapolation(names, { ...inside, yield_stress: 500 })).toBe(true);
    expect(fnoIsExtrapolation(names, { ...inside, yield_stress: 100 })).toBe(false);
  });
  it("wind 80 m/s is outside, 0 and 50 inside, direction 0 and 359 inside", () => {
    const wind = ["wind_speed", "wind_direction"];
    expect(fnoIsExtrapolation(wind, { wind_speed: 80, wind_direction: 90 })).toBe(true);
    for (const s of [0, 50])
      expect(fnoIsExtrapolation(wind, { wind_speed: s, wind_direction: 90 })).toBe(false);
    for (const d of [0, 359])
      expect(fnoIsExtrapolation(wind, { wind_speed: 5, wind_direction: d })).toBe(false);
  });
});

describe("NFR-011-03 live budget", () => {
  it("1,000 ms is live, slower or not measured is not", () => {
    expect(fnoIsLive(1000)).toBe(true);
    expect(fnoIsLive(12.5)).toBe(true);
    expect(fnoIsLive(1000.1)).toBe(false);
    expect(fnoIsLive(Number.NaN)).toBe(false);
    expect(fnoIsLive(-1)).toBe(false);
  });
});

describe("NFR-011-02 step time", () => {
  it("median by hand: odd, even, empty, non-finite ignored", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 2, 3])).toBe(2.5);
    expect(Number.isNaN(median([]))).toBe(true);
    expect(median([1, Number.NaN, 3])).toBe(2);
  });

  it("the timer keeps the last 100 steps only and ignores invalid times", () => {
    const timer = new StepTimer();
    for (let i = 1; i <= 150; i++) timer.record(i);
    timer.record(Number.NaN);
    timer.record(-3);
    expect(timer.count).toBe(100);
    expect(timer.median()).toBe(100.5); // 51..150
  });

  it("the T2 cap is the largest measured count within the budget and the engine cap, else null", () => {
    const m = [
      { particles: 500, medianMs: 12 },
      { particles: 2000, medianMs: 49.9 },
      { particles: 3000, medianMs: 50 },
      { particles: 4000, medianMs: 80 },
      { particles: 9000, medianMs: 10 },
    ];
    expect(particleCap(m, 50, 5000)).toBe(3000);
    expect(particleCap([{ particles: 500, medianMs: 90 }], 50, 5000)).toBeNull();
    expect(particleCap([], 50, 5000)).toBeNull();
  });
});
