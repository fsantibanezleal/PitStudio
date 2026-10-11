// T-018-066 [red] · FR-018-51 (AP-42 and Gaussian-plume port, parity within 1e-12 s_y + rtol |y|), P-018-37 (plume linear in the source
// strength), P-018-38 (crosswind symmetry), P-018-39 (AP-42 power law) for the `plume` engine of spec 018.
//
// Expected API (module `~/engines/analytical/environment`, file web/src/engines/analytical/environment/index.ts). Every function takes the
// `args` of its DC-018-02 request and returns the `result` object (specs/018-web-cases/contracts/engines/plume.schema.json), SI, snake_case:
//     ap42_emission_factor(args) -> { emission_factor_kg_per_m }
//     pasquill_sigmas(args)      -> { sigma_y_m, sigma_z_m }
//     plume_grid(args)           -> { concentration_kg_per_m3: Float64Array, rows, cols, max_concentration_kg_per_m3, max_x_m, max_y_m }
//   The grid is row-major, rows = ny (y index), cols = nx (x index): value (iy, ix) is at iy * nx + ix, at x = x_start + ix x_step,
//   y = y_start + iy y_step, receptor height `receptor_height_m`. The maximum is the first cell of the largest value in that order.
//   A value outside a validity range of the schema (silt 0.018-0.252, mean weight 1,814.36948-263,083.5746 kg, ...) throws an error with
//   `code === "E_RANGE"`; a grid larger than 256 x 256 `E_SIZE`; an unknown enum value `E_SCHEMA` (FR-018-38).
//
// Oracles (independent of the code under test):
//   - AP-42 eq. 1a (US EPA 2006, section 13.2.2): E = k (s/12)^a (W/3)^b x 0.45359237 / 1609.344 (lb/VMT to kg/m), s in %, W in short tons,
//     (k, a, b) = (0.15, 0.9, 0.45), (1.5, 0.9, 0.45), (4.9, 0.7, 0.45); values recomputed with numpy on 2026-10-11 and the plan-006 hand values
//     (silt 10 %, 290 short tons: 0.995870 / 9.958701 / 33.739896 lb/VMT; silt 8 %, 200 short tons PM10: 6.892362 lb/VMT).
//   - ISC3 dispersion (US EPA 1995, Tables 1-1 to 1-4) hand points of the minephys plan 006 (printed to 6 decimals): rural D at 1 km
//     (68.126741, 32.093), D at 0.5 km (36.146194, 18.296893), C at 1 km (103.113800, 61.141), F at 2 km (63.675319, 21.627177), A at 0.2 km
//     (49.971379, 29.301954); urban D at 1 km (135.224681, 122.788123); Briggs urban formulas of every class at 2 km.
//   - The Gaussian plume with ground reflection (ISC3 eq. 1-1): C = q / (2 pi u sy sz) exp(-y^2 / 2 sy^2) [exp(-(z-h)^2 / 2 sz^2) + exp(-(z+h)^2 / 2 sz^2)],
//     evaluated in this file.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as env from "~/engines/analytical/environment";
import { expectAnalyticalParity } from "~/test-support/parity-fixtures";

const LB_PER_VMT = 0.45359237 / 1609.344;
const SHORT_TON = 907.18474;
const COEFFS: Record<string, [number, number, number]> = {
  "PM2.5": [0.15, 0.9, 0.45],
  PM10: [1.5, 0.9, 0.45],
  PM30: [4.9, 0.7, 0.45],
};
const ap42 = (silt: number, weightKg: number, size: string) =>
  (
    env.ap42_emission_factor({ silt_fraction: silt, mean_weight_kg: weightKg, size_class: size }) as {
      emission_factor_kg_per_m: number;
    }
  ).emission_factor_kg_per_m;
const hand = (silt: number, weightKg: number, size: string) => {
  const [k, a, b] = COEFFS[size] as [number, number, number];
  return k * ((100 * silt) / 12) ** a * (weightKg / SHORT_TON / 3) ** b * LB_PER_VMT;
};
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}

describe("AP-42 unpaved-road emission factor (FR-018-51, P-018-39)", () => {
  it("FR-018-51 · silt 10 %, 290 short tons: 0.995870 / 9.958701 / 33.739896 lb/VMT, i.e. 2.806852088e-4, 2.806852088e-3 and 9.509563824e-3 kg/m", () => {
    const w = 290 * SHORT_TON;
    expect(ap42(0.1, w, "PM2.5")).toBeCloseTo(2.806852088493755e-4, 15);
    expect(ap42(0.1, w, "PM10")).toBeCloseTo(2.806852088493755e-3, 14);
    expect(ap42(0.1, w, "PM30")).toBeCloseTo(9.509563824322454e-3, 14);
    expect(Math.abs(ap42(0.1, w, "PM2.5") / LB_PER_VMT - 0.99587)).toBeLessThan(6e-7);
    expect(Math.abs(ap42(0.1, w, "PM10") / LB_PER_VMT - 9.958701)).toBeLessThan(6e-7);
    expect(Math.abs(ap42(0.1, w, "PM30") / LB_PER_VMT - 33.739896)).toBeLessThan(6e-7);
  });

  it("FR-018-51 · silt 8 %, 200 short tons, PM10: 6.892362 lb/VMT = 1.942606845e-3 kg/m; silt 8 %, 20 short tons: 6.892629186e-4 kg/m", () => {
    expect(ap42(0.08, 200 * SHORT_TON, "PM10")).toBeCloseTo(1.942606845004902e-3, 14);
    expect(Math.abs(ap42(0.08, 200 * SHORT_TON, "PM10") / LB_PER_VMT - 6.892362)).toBeLessThan(6e-7);
    expect(ap42(0.08, 20 * SHORT_TON, "PM10")).toBeCloseTo(6.892629186245324e-4, 15);
  });

  it("FR-018-51 · at s = 12 % and W = 3 short tons both factors are 1: E = k lb/VMT exactly (rtol 1e-12)", () => {
    for (const [cls, [k]] of Object.entries(COEFFS)) {
      // silt 0.12 is inside the schema range; 3 short tons = 2,721.55422 kg is inside the weight range
      const e = ap42(0.12, 3 * SHORT_TON, cls);
      expect(Math.abs(e - k * LB_PER_VMT)).toBeLessThanOrEqual(1e-12 * k * LB_PER_VMT);
    }
  });

  it("FR-018-51 · the SI factor equals AP-42's printed 1 lb/VMT = 281.9 g/VKT within rtol 2e-4", () => {
    const oneLb = ap42(0.12, 3 * SHORT_TON, "PM10") / 1.5; // kg per metre for 1 lb/VMT
    expect(Math.abs((oneLb * 1e6) / 281.9 - 1)).toBeLessThan(2e-4);
  });

  it("P-018-03/FR-018-51 · PM2.5 is a tenth of PM10, and PM10 < PM30, for every valid silt and weight", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.018, max: 0.252, noNaN: true }),
        fc.double({ min: 1814.36948, max: 263083.5746, noNaN: true }),
        (s, w) => {
          const pm25 = ap42(s, w, "PM2.5");
          const pm10 = ap42(s, w, "PM10");
          return Math.abs(pm25 - 0.1 * pm10) <= 1e-12 * pm10 && pm10 < ap42(s, w, "PM30");
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-39 · doubling the silt content multiplies the factor by 2^a (2^0.9 for PM2.5 and PM10, 2^0.7 for PM30) and doubling the mean weight by 2^0.45 (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.018, max: 0.126, noNaN: true }),
        fc.double({ min: 1814.36948, max: 131541, noNaN: true }),
        fc.constantFrom("PM2.5", "PM10", "PM30"),
        (s, w, cls) => {
          const a = (COEFFS[cls] as [number, number, number])[1];
          const base = ap42(s, w, cls);
          const siltRatio = ap42(2 * s, w, cls) / base;
          const weightRatio = ap42(s, 2 * w, cls) / base;
          return (
            Math.abs(siltRatio - 2 ** a) <= 1e-12 * 2 ** a &&
            Math.abs(weightRatio - 2 ** 0.45) <= 1e-12 * 2 ** 0.45
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · the result matches the published-unit expression for random valid inputs (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.018, max: 0.252, noNaN: true }),
        fc.double({ min: 1814.36948, max: 263083.5746, noNaN: true }),
        fc.constantFrom("PM2.5", "PM10", "PM30"),
        (s, w, cls) => Math.abs(ap42(s, w, cls) - hand(s, w, cls)) <= 1e-12 * hand(s, w, cls),
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · values outside the AP-42 validity range are E_RANGE (the reference only warns, the engine is stricter), an unknown size class E_SCHEMA", () => {
    expect(codeOf(() => ap42(0.017, 50000, "PM10"))).toBe("E_RANGE");
    expect(codeOf(() => ap42(0.253, 50000, "PM10"))).toBe("E_RANGE");
    expect(codeOf(() => ap42(0.1, 1814, "PM10"))).toBe("E_RANGE");
    expect(codeOf(() => ap42(0.1, 263084, "PM10"))).toBe("E_RANGE");
    expect(codeOf(() => ap42(0.1, 50000, "PM5"))).toBe("E_SCHEMA");
    expect(codeOf(() => ap42(0.1, 50000, "pm10"))).toBe("E_SCHEMA");
  });
});

describe("ISC3 dispersion coefficients (FR-018-51)", () => {
  const sig = (x: number, cls: string, terrain = "rural") =>
    env.pasquill_sigmas({ downwind_distance_m: x, stability_class: cls, terrain }) as {
      sigma_y_m: number;
      sigma_z_m: number;
    };
  const points: Array<[string, number, number, number]> = [
    ["D", 1000, 68.126741, 32.093],
    ["D", 500, 36.146194, 18.296893],
    ["C", 1000, 103.1138, 61.141],
    ["F", 2000, 63.675319, 21.627177],
    ["A", 200, 49.971379, 29.301954],
  ];
  for (const [cls, x, sy, sz] of points) {
    it(`FR-018-51 · rural class ${cls} at ${x} m: sigma_y = ${sy} m, sigma_z = ${sz} m (minephys plan 006 hand values, 6 decimals)`, () => {
      const s = sig(x, cls);
      expect(Math.abs(s.sigma_y_m - sy)).toBeLessThan(6e-7);
      expect(Math.abs(s.sigma_z_m - sz)).toBeLessThan(6e-7);
    });
  }

  it("FR-018-51 · sigma_y follows 465.11628 x_km tan(0.017453293 (c - d ln x_km)) with the ISC3 Table 1-1 (c, d) for every class, at 1.5 km (rtol 1e-12)", () => {
    const CD: Record<string, [number, number]> = {
      A: [24.167, 2.5334],
      B: [18.333, 1.8096],
      C: [12.5, 1.0857],
      D: [8.333, 0.72382],
      E: [6.25, 0.54287],
      F: [4.1667, 0.36191],
    };
    for (const [cls, [c, d]] of Object.entries(CD)) {
      const xk = 1.5;
      const expected = 465.11628 * xk * Math.tan(0.017453293 * (c - d * Math.log(xk)));
      expect(Math.abs(sig(1500, cls).sigma_y_m - expected), cls).toBeLessThanOrEqual(1e-12 * expected);
    }
  });

  it("FR-018-51 · the vertical coefficient is capped at 5,000 m for A, B and C and equals 5,000 m for class A beyond 3.11 km; sigma_y has no cap", () => {
    for (const x of [3500, 10_000, 100_000]) expect(sig(x, "A").sigma_z_m).toBe(5000);
    expect(sig(50_000, "B").sigma_z_m).toBe(5000);
    for (const cls of ["D", "E", "F"]) expect(sig(50_000, cls).sigma_z_m).toBeLessThan(5000);
    expect(sig(100_000, "A").sigma_y_m).toBeGreaterThan(5000);
  });

  it("FR-018-51 · the band edge belongs to the lower band: at 300 m class D the value at the edge equals the left limit, not the right one", () => {
    const left = sig(300 * (1 - 1e-9), "D").sigma_z_m;
    const edge = sig(300, "D").sigma_z_m;
    const right = sig(300 * (1 + 1e-9), "D").sigma_z_m;
    expect(Math.abs(edge - left)).toBeLessThan(Math.abs(edge - right));
    expect(Math.abs(edge - left) / left).toBeLessThan(1e-8);
  });

  it("FR-018-51 · urban class D at 1,000 m: sigma_y = 0.16 x / sqrt(1 + 0.0004 x) = 135.224681, sigma_z = 0.14 x / sqrt(1 + 0.0003 x) = 122.788123", () => {
    const s = sig(1000, "D", "urban");
    expect(s.sigma_y_m).toBeCloseTo((0.16 * 1000) / Math.sqrt(1 + 0.0004 * 1000), 12);
    expect(s.sigma_z_m).toBeCloseTo((0.14 * 1000) / Math.sqrt(1 + 0.0003 * 1000), 12);
    expect(Math.abs(s.sigma_y_m - 135.224681)).toBeLessThan(6e-7);
    expect(Math.abs(s.sigma_z_m - 122.788123)).toBeLessThan(6e-7);
  });

  it("FR-018-51 · the Briggs urban formulas of every class at 2,000 m (ISC3 Tables 1-3 and 1-4, hand calculation, rtol 1e-12)", () => {
    const x = 2000;
    const yForm = (c: number) => (c * x) / Math.sqrt(1 + 0.0004 * x);
    const z: Record<string, number> = {
      A: 0.24 * x * Math.sqrt(1 + 0.001 * x),
      B: 0.24 * x * Math.sqrt(1 + 0.001 * x),
      C: 0.2 * x,
      D: (0.14 * x) / Math.sqrt(1 + 0.0003 * x),
      E: (0.08 * x) / Math.sqrt(1 + 0.0015 * x),
      F: (0.08 * x) / Math.sqrt(1 + 0.0015 * x),
    };
    const y: Record<string, number> = { A: 0.32, B: 0.32, C: 0.22, D: 0.16, E: 0.11, F: 0.11 };
    for (const cls of "ABCDEF") {
      const s = sig(x, cls, "urban");
      expect(Math.abs(s.sigma_y_m - yForm(y[cls] as number)), `${cls} y`).toBeLessThanOrEqual(
        1e-12 * yForm(y[cls] as number),
      );
      expect(Math.abs(s.sigma_z_m - (z[cls] as number)), `${cls} z`).toBeLessThanOrEqual(
        1e-12 * (z[cls] as number),
      );
    }
  });

  const xArb = fc.double({ min: Math.log(10), max: Math.log(100_000), noNaN: true }).map(Math.exp);

  it("FR-018-51 · sigma_y is strictly increasing in x and sigma_z non-decreasing (a drop at a band edge is at most 1e-4 relative), rural and urban", () => {
    fc.assert(
      fc.property(
        xArb,
        fc.double({ min: 1.0001, max: 1.5, noNaN: true }),
        fc.constantFrom(..."ABCDEF"),
        fc.constantFrom("rural", "urban"),
        (x, f, cls, terrain) => {
          const a = sig(x, cls, terrain);
          const b = sig(x * f, cls, terrain);
          return b.sigma_y_m > a.sigma_y_m && b.sigma_z_m >= a.sigma_z_m * (1 - 1e-4);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · at any fixed x both coefficients are ordered A >= B >= C >= D >= E >= F, rural and urban", () => {
    fc.assert(
      fc.property(xArb, fc.constantFrom("rural", "urban"), (x, terrain) => {
        const s = [..."ABCDEF"].map((c) => sig(x, c, terrain));
        for (let i = 1; i < s.length; i++) {
          const p = s[i - 1] as { sigma_y_m: number; sigma_z_m: number };
          const q = s[i] as { sigma_y_m: number; sigma_z_m: number };
          if (!(p.sigma_y_m >= q.sigma_y_m * (1 - 1e-12) && p.sigma_z_m >= q.sigma_z_m * (1 - 1e-12)))
            return false;
        }
        return true;
      }),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · hostile: a non-positive distance is E_RANGE, an unknown class or terrain E_SCHEMA", () => {
    expect(codeOf(() => sig(0, "D"))).toBe("E_RANGE");
    expect(codeOf(() => sig(-5, "D"))).toBe("E_RANGE");
    expect(codeOf(() => sig(100, "G"))).toBe("E_SCHEMA");
    expect(codeOf(() => sig(100, "d"))).toBe("E_SCHEMA");
    expect(codeOf(() => sig(100, "D", "suburban"))).toBe("E_SCHEMA");
  });
});

describe("Gaussian plume on a receptor grid (FR-018-51, P-018-37, P-018-38)", () => {
  const baseArgs = {
    source_strength_kg_per_s: 1,
    wind_speed_m_per_s: 2,
    stability_class: "D",
    terrain: "rural",
    release_height_m: 0,
    x_start_m: 500,
    x_step_m: 500,
    nx: 2,
    y_start_m: -50,
    y_step_m: 50,
    ny: 3,
    receptor_height_m: 0,
  };
  type Grid = {
    concentration_kg_per_m3: Float64Array;
    rows: number;
    cols: number;
    max_concentration_kg_per_m3: number;
    max_x_m: number;
    max_y_m: number;
  };
  const grid = (over: Record<string, unknown> = {}) => env.plume_grid({ ...baseArgs, ...over }) as Grid;
  const gauss = (q: number, u: number, y: number, z: number, h: number, sY: number, sZ: number) =>
    (q / (2 * Math.PI * u * sY * sZ)) *
    Math.exp((-y * y) / (2 * sY * sY)) *
    (Math.exp(-((z - h) ** 2) / (2 * sZ * sZ)) + Math.exp(-((z + h) ** 2) / (2 * sZ * sZ)));
  // class D rural coefficients at 0.5 and 1 km (c = 8.333, d = 0.72382; a = 32.093, b = 0.81066): same band for both distances
  const sigmaD = (x: number): [number, number] => {
    const xk = x / 1000;
    return [
      465.11628 * xk * Math.tan(0.017453293 * (8.333 - 0.72382 * Math.log(xk))),
      32.093 * xk ** 0.81066,
    ];
  };

  it("FR-018-51 · ground-level release at ground-level receptors: the 2 x 3 grid equals the formula with the ISC3 coefficients (rtol 1e-12) and the numpy values", () => {
    const g = grid();
    expect(g.rows).toBe(3);
    expect(g.cols).toBe(2);
    expect(g.concentration_kg_per_m3).toHaveLength(6);
    const embedded = [
      [9.244469310072084e-5, 5.560660074049605e-5],
      [2.406468729660521e-4, 7.279343291643247e-5],
      [9.244469310072084e-5, 5.560660074049605e-5],
    ];
    for (let iy = 0; iy < 3; iy++) {
      for (let ix = 0; ix < 2; ix++) {
        const x = 500 + 500 * ix;
        const y = -50 + 50 * iy;
        const [sy, sz] = sigmaD(x);
        const c = g.concentration_kg_per_m3[iy * 2 + ix] as number;
        const expected = gauss(1, 2, y, 0, 0, sy, sz);
        expect(Math.abs(c - expected), `(${iy},${ix})`).toBeLessThanOrEqual(1e-12 * expected);
        expect(Math.abs(c - ((embedded[iy] as number[])[ix] as number))).toBeLessThanOrEqual(1e-9 * c);
      }
    }
  });

  it("FR-018-51 · an elevated release (h = 20 m) seen at z = 5 m includes the ground-reflection image term", () => {
    const g = grid({ release_height_m: 20, receptor_height_m: 5 });
    const embedded = [
      [5.120428125752956e-5, 4.5453476285916685e-5],
      [1.332921312602923e-4, 5.95021909769055e-5],
      [5.120428125752956e-5, 4.5453476285916685e-5],
    ];
    for (let iy = 0; iy < 3; iy++) {
      for (let ix = 0; ix < 2; ix++) {
        const [sy, sz] = sigmaD(500 + 500 * ix);
        const c = g.concentration_kg_per_m3[iy * 2 + ix] as number;
        const expected = gauss(1, 2, -50 + 50 * iy, 5, 20, sy, sz);
        expect(Math.abs(c - expected)).toBeLessThanOrEqual(1e-12 * expected);
        expect(Math.abs(c - ((embedded[iy] as number[])[ix] as number))).toBeLessThanOrEqual(1e-9 * c);
      }
    }
  });

  it("FR-018-51 · the maximum and its position are reported: the centre-line cell at 500 m (2.406468729660521e-4 kg/m3)", () => {
    const g = grid();
    expect(Math.abs(g.max_concentration_kg_per_m3 - 2.406468729660521e-4)).toBeLessThanOrEqual(1e-9 * 2.4e-4);
    expect(g.max_x_m).toBe(500);
    expect(g.max_y_m).toBe(0);
  });

  it("P-018-37 · the concentration is linear in the source strength: C(kQ) = k C(Q) (rtol 1e-12), and zero at Q = 0", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1e-3, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1000, noNaN: true }),
        fc.constantFrom(..."ABCDEF"),
        (q, k, cls) => {
          const a = grid({ source_strength_kg_per_s: q, stability_class: cls }).concentration_kg_per_m3;
          const b = grid({ source_strength_kg_per_s: k * q, stability_class: cls }).concentration_kg_per_m3;
          return Array.from(a).every(
            (v, i) => Math.abs((b[i] as number) - k * v) <= 1e-12 * Math.max(Math.abs(k * v), 1e-300),
          );
        },
      ),
      { numRuns: 200 },
    );
    expect(
      Array.from(grid({ source_strength_kg_per_s: 0 }).concentration_kg_per_m3).every((v) => v === 0),
    ).toBe(true);
  });

  it("P-018-38 · crosswind symmetry: C(x, y, z) = C(x, -y, z) on a symmetric y axis (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(..."ABCDEF"),
        fc.constantFrom("rural", "urban"),
        fc.double({ min: 0, max: 100, noNaN: true }),
        fc.double({ min: 0, max: 50, noNaN: true }),
        fc.integer({ min: 1, max: 6 }),
        (cls, terrain, h, z, half) => {
          const ny = 2 * half + 1;
          const g = grid({
            stability_class: cls,
            terrain,
            release_height_m: h,
            receptor_height_m: z,
            nx: 4,
            ny,
            y_start_m: -half * 30,
            y_step_m: 30,
            x_start_m: 200,
          });
          const c = g.concentration_kg_per_m3;
          for (let iy = 0; iy < ny; iy++) {
            for (let ix = 0; ix < 4; ix++) {
              const a = c[iy * 4 + ix] as number;
              const b = c[(ny - 1 - iy) * 4 + ix] as number;
              if (Math.abs(a - b) > 1e-12 * Math.max(Math.abs(a), 1e-300)) return false;
            }
          }
          return true;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · the concentration is inversely proportional to the wind speed (C(2u) = C(u) / 2)", () => {
    const slow = grid({ wind_speed_m_per_s: 1.5 }).concentration_kg_per_m3;
    const fast = grid({ wind_speed_m_per_s: 3 }).concentration_kg_per_m3;
    for (const [i, v] of Array.from(slow).entries())
      expect(Math.abs((fast[i] as number) - v / 2)).toBeLessThanOrEqual(1e-12 * v);
  });

  it("FR-018-51 · a mixing lid adds image sources: never lower than the unbounded plume, equal when the lid is far above the plume, zero when the release is above it", () => {
    const open = grid({
      x_start_m: 2000,
      x_step_m: 2000,
      nx: 3,
      release_height_m: 30,
      receptor_height_m: 10,
    }).concentration_kg_per_m3;
    const lid = grid({
      x_start_m: 2000,
      x_step_m: 2000,
      nx: 3,
      release_height_m: 30,
      receptor_height_m: 10,
      mixing_height_m: 150,
    }).concentration_kg_per_m3;
    expect(Array.from(lid).every((v, i) => v >= (open[i] as number) * (1 - 1e-12))).toBe(true);
    expect(Array.from(lid).some((v, i) => v > (open[i] as number) * (1 + 1e-6))).toBe(true);
    const faraway = grid({
      release_height_m: 30,
      receptor_height_m: 10,
      mixing_height_m: 10000,
    }).concentration_kg_per_m3;
    const plain = grid({ release_height_m: 30, receptor_height_m: 10 }).concentration_kg_per_m3;
    for (const [i, v] of Array.from(plain).entries())
      expect(Math.abs((faraway[i] as number) - v)).toBeLessThanOrEqual(1e-12 * v);
    const above = grid({ release_height_m: 200, mixing_height_m: 100 });
    expect(Array.from(above.concentration_kg_per_m3).every((v) => v === 0)).toBe(true);
    expect(above.max_concentration_kg_per_m3).toBe(0);
  });

  it("FR-018-51 · hostile: a grid above 256 x 256 is E_SIZE; non-positive wind, negative source or height, x_start 0 and a non-positive mixing height are E_RANGE; an unknown class is E_SCHEMA", () => {
    expect(codeOf(() => grid({ nx: 257 }))).toBe("E_SIZE");
    expect(codeOf(() => grid({ ny: 257 }))).toBe("E_SIZE");
    expect(codeOf(() => grid({ nx: 0 }))).toMatch(/E_RANGE|E_SCHEMA/);
    expect(codeOf(() => grid({ wind_speed_m_per_s: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ source_strength_kg_per_s: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ release_height_m: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ receptor_height_m: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ x_start_m: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ mixing_height_m: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => grid({ stability_class: "Z" }))).toBe("E_SCHEMA");
  });
});

describe("parity with minephys.environment (FR-018-51)", () => {
  it("FR-018-51 · ap42_emission_factor equals the reference on its fixture (>= 200 vectors, both ends of the validity ranges)", () => {
    expectAnalyticalParity("plume", "ap42_emission_factor", (args) =>
      env.ap42_emission_factor(args as never),
    );
  });
  it("FR-018-51 · pasquill_sigmas equals the reference on its fixture", () => {
    expectAnalyticalParity("plume", "pasquill_sigmas", (args) => env.pasquill_sigmas(args as never));
  });
  it("FR-018-51 · plume_grid equals the reference on its fixture", () => {
    expectAnalyticalParity("plume", "plume_grid", (args) => env.plume_grid(args as never));
  });
});
