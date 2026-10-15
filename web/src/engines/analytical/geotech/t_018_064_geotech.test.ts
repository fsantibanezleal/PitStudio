// T-018-064 [red] · FR-018-51 (analytical parity within 1e-12 s_y + rtol |y|), FR-018-52 (Monte-Carlo probability of failure),
// P-018-28..36 and P-018-76 for the `geotech` engine of spec 018: limit equilibrium (Bishop, Spencer), Monte Carlo, inverse velocity,
// the Bayesian failure band and the slope-radar line of sight.
//
// Expected API (module `~/engines/analytical/geotech`, file web/src/engines/analytical/geotech/index.ts). Every function takes the
// `args` object of its DC-018-02 request and returns the `result` object (specs/018-web-cases/contracts/engines/geotech.schema.json),
// in SI units, with the schema's snake_case names; the two buffers of `slope_radar_los` are Float64Array (or number[]) of 3 x pixels
// values, row-major (x, y, z per pixel), and its `los_m` is a Float64Array.
//     bishop(args)            -> { fos, iterations }
//     spencer(args)           -> { fos, theta_rad, iterations }
//     pof_monte_carlo(args)   -> { n_samples, failures, pof, wilson_low, wilson_high }     draws with PCG64 (T-018-051) from `seed`
//     pof_from_samples(args)  -> { n_samples, failures, pof, wilson_low, wilson_high }     failure = factor of safety < 1
//     inverse_velocity(args)  -> { accelerating, failure_time_s?, slope_per_m, intercept_s_per_m, r_squared, n_used }
//                                `failure_time_s` is absent when the fitted slope is >= 0 (not accelerating)
//     failure_band(args)      -> { status: "band" | "no-accelerating-draw", median_s?, lower_s?, upper_s?, fraction_not_accelerating,
//                                  posterior_mean, posterior_cov }
//     slope_radar_los(args)   -> { los_m }
//   A violation of a physical domain throws an error with `code === "E_RANGE"`, a malformed argument `code === "E_SCHEMA"`, and a
//   failure to converge `code === "E_RUNTIME"` (FR-018-38 typed errors; FR-018-51 for E_RANGE).
//
// Oracles (independent of the code under test):
//   - minephys spec 003 section 7.4 hand calculations, recomputed here with a separate implementation (numpy/scipy, 2026-10-11):
//     Bishop 1.2842940552716662 / 1.0026750531647228, Spencer 1.27751773 (theta 0.47196086 rad) / 1.00133149 (theta 0.4543977 rad);
//     c' only: F = sum(c' l) / sum(W sin a) = 1.4623899; phi' only: tan(30 deg)/tan(20 deg) = 1.5862568; the Rocscience hand calculation
//     #1 (Bishop 2.113 printed, 2.1129427 recomputed); the Voight alpha = 2 series (v = 1 / (A (t_f - t))), its OLS fit and the flat-prior
//     Bayesian posterior with its analytical quantiles 854,367.67 s and 873,924.60 s; the radar geometry values.
//   - the metamorphic relations of spec 018 section 4 (P-018-28..36, P-018-76), tolerances as stated there.
//   - the parity fixtures of the reference (`minephys.geotech`), DC-018-04, through web/src/test-support/parity-fixtures.ts.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as geotech from "~/engines/analytical/geotech";
import { expectAnalyticalParity, loadParityFixtures } from "~/test-support/parity-fixtures";

const DEG = Math.PI / 180;
type Slice = { width_m: number; weight_n_per_m: number; base_angle_rad: number; pore_pressure_pa: number };
const slices = (b: number[], w: number[], a: number[], u: number[]): Slice[] =>
  b.map((width_m, i) => ({
    width_m,
    weight_n_per_m: w[i] as number,
    base_angle_rad: (a[i] as number) * DEG,
    pore_pressure_pa: u[i] as number,
  }));

/** The code of the typed error a call throws, or null when it does not throw. */
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}

// Three slices, b = 2 m, W = (60, 120, 80) kN/m, alpha = (5, 25, 50) deg: minephys spec 003 hand case.
const A3 = slices([2, 2, 2], [60e3, 120e3, 80e3], [5, 25, 50], [0, 0, 0]);
const A3u = slices([2, 2, 2], [60e3, 120e3, 80e3], [5, 25, 50], [0, 20e3, 10e3]);
// phi' = 0 case: W = (40, 80, 50) kN/m, alpha = (-10, 15, 40) deg.
const P0 = slices([2, 2, 2], [40e3, 80e3, 50e3], [-10, 15, 40], [0, 0, 0]);

describe("limit equilibrium by hand (FR-018-51)", () => {
  it("FR-018-51 · Bishop on the three-slice case: 1.2842940552716662 dry and 1.0026750531647228 with pore pressures (0, 20, 10) kPa", () => {
    const dry = geotech.bishop({ slices: A3, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG });
    expect(dry.fos).toBeCloseTo(1.2842940552716662, 9);
    expect(dry.iterations).toBeGreaterThanOrEqual(1);
    const wet = geotech.bishop({ slices: A3u, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG });
    expect(wet.fos).toBeCloseTo(1.0026750531647228, 9);
  });

  it("FR-018-51 · Spencer on the same case: 1.27751773 at theta 0.47196086 rad dry, 1.00133149 at 0.4543977 rad wet", () => {
    const dry = geotech.spencer({ slices: A3, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG });
    expect(dry.fos).toBeCloseTo(1.27751773, 7);
    expect(dry.theta_rad).toBeCloseTo(0.47196086, 6);
    const wet = geotech.spencer({ slices: A3u, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG });
    expect(wet.fos).toBeCloseTo(1.00133149, 7);
    expect(wet.theta_rad).toBeCloseTo(0.4543977, 6);
  });

  it("FR-018-51 · with phi' = 0 Bishop's F is the sum of c' l over the sum of W sin alpha = 1.4623899", () => {
    expect(geotech.bishop({ slices: P0, cohesion_pa: 10e3, friction_angle_rad: 0 }).fos).toBeCloseTo(
      1.4623899,
      6,
    );
    // hand: l = b / cos(alpha): 2.030871 + 2.070552 + 2.610814 = 6.712237 m; sum W sin(alpha) = 45899.0 N/m
    expect((10e3 * 6.712237) / 45899.0).toBeCloseTo(1.4623899, 5);
  });

  it("FR-018-51 · with c' = 0, dry slices and all base angles equal to 20 deg, F = tan(30 deg) / tan(20 deg) = 1.5862568", () => {
    const flat = slices([2, 2, 2], [1e4, 2e4, 3e4], [20, 20, 20], [0, 0, 0]);
    expect(geotech.bishop({ slices: flat, cohesion_pa: 0, friction_angle_rad: 30 * DEG }).fos).toBeCloseTo(
      Math.tan(30 * DEG) / Math.tan(20 * DEG),
      9,
    );
  });

  it("FR-018-51 · Rocscience hand calculation #1 (7 slices, b = 2.5 m, c' = 20 kPa, phi' = 20 deg, 20 kN/m3): F = 2.113 as printed", () => {
    const heights = [0.8, 2.3, 3.3, 3.9, 4.1, 3.6, 1.65];
    const rocs = slices(
      Array(7).fill(2.5),
      heights.map((h) => 20e3 * 2.5 * h),
      [-9, 0.5, 9, 18.5, 28, 39, 52],
      Array(7).fill(0),
    );
    const f = geotech.bishop({ slices: rocs, cohesion_pa: 20e3, friction_angle_rad: 20 * DEG }).fos;
    expect(Math.abs(f - 2.113)).toBeLessThan(6e-4);
    expect(f).toBeCloseTo(2.1129426616473928, 9);
  });

  it("FR-018-51 · Spencer's moment equation at theta = 0 has Bishop's F as its root: with every slice at the same angle both methods agree closely", () => {
    const same = slices([2, 2, 2], [1e4, 2e4, 3e4], [20, 20, 20], [0, 0, 0]);
    const b = geotech.bishop({ slices: same, cohesion_pa: 0, friction_angle_rad: 30 * DEG }).fos;
    const s = geotech.spencer({ slices: same, cohesion_pa: 0, friction_angle_rad: 30 * DEG }).fos;
    expect(s).toBeCloseTo(b, 6);
  });
});

describe("hostile limit-equilibrium inputs (FR-018-51, FR-018-38)", () => {
  const base = { slices: A3, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG };
  it("FR-018-51 · a driving moment sum W sin(alpha) <= 0 is E_RANGE for both methods", () => {
    const uphill = slices([2, 2], [1e4, 1e4], [-20, -30], [0, 0]);
    expect(codeOf(() => geotech.bishop({ ...base, slices: uphill }))).toBe("E_RANGE");
    expect(codeOf(() => geotech.spencer({ ...base, slices: uphill }))).toBe("E_RANGE");
  });
  const bad: Array<[string, Record<string, unknown>]> = [
    ["a negative cohesion", { cohesion_pa: -1 }],
    ["a friction angle of 90 deg", { friction_angle_rad: Math.PI / 2 }],
    ["a friction angle above the 60 deg cap", { friction_angle_rad: 61 * DEG }],
    ["a zero width", { slices: slices([0, 2, 2], [6e4, 12e4, 8e4], [5, 25, 50], [0, 0, 0]) }],
    ["a base angle of 90 deg", { slices: slices([2, 2, 2], [6e4, 12e4, 8e4], [5, 25, 90], [0, 0, 0]) }],
    ["a negative weight", { slices: slices([2, 2, 2], [6e4, -12e4, 8e4], [5, 25, 50], [0, 0, 0]) }],
    ["a negative pore pressure", { slices: slices([2, 2, 2], [6e4, 12e4, 8e4], [5, 25, 50], [0, -1, 0]) }],
  ];
  for (const [name, over] of bad) {
    it(`FR-018-51 · ${name} is E_RANGE`, () => {
      expect(codeOf(() => geotech.bishop({ ...base, ...over }))).toBe("E_RANGE");
    });
  }
  it("FR-018-51 · a solver that cannot converge in the allowed iterations is E_RUNTIME (ConvergenceError of the reference)", () => {
    expect(codeOf(() => geotech.bishop({ ...base, max_iterations: 1 }))).toBe("E_RUNTIME");
  });
});

describe("limit-equilibrium metamorphic relations (P-018-28, P-018-29, P-018-30)", () => {
  // pore pressure is at most 30 % of the slice normal stress scale W / b, so every effective normal force stays positive
  const sliceArb = fc
    .record({
      width_m: fc.double({ min: 0.5, max: 10, noNaN: true }),
      weight_n_per_m: fc.double({ min: 1e4, max: 5e6, noNaN: true }),
      base_angle_rad: fc.double({ min: -0.15, max: 0.9, noNaN: true }),
      pore_fraction: fc.double({ min: 0, max: 0.3, noNaN: true }),
    })
    .map(({ pore_fraction, ...s }) => ({
      ...s,
      pore_pressure_pa: (pore_fraction * s.weight_n_per_m) / s.width_m,
    }));
  // a dominant steep slice guarantees a positive driving moment and a convergent Bishop iteration
  const setArb = fc
    .array(sliceArb, { minLength: 2, maxLength: 20 })
    .map((s) => [...s, { width_m: 4, weight_n_per_m: 6e6, base_angle_rad: 0.8, pore_pressure_pa: 0 }]);
  const phiArb = fc.double({ min: 10 * DEG, max: 45 * DEG, noNaN: true });

  it("P-018-28 · Bishop's factor of safety is non-decreasing in the effective cohesion", () => {
    fc.assert(
      fc.property(
        setArb,
        phiArb,
        fc.double({ min: 0, max: 5e4, noNaN: true }),
        fc.double({ min: 1e3, max: 5e4, noNaN: true }),
        (s, phi, c, dc) => {
          const f1 = geotech.bishop({ slices: s, cohesion_pa: c, friction_angle_rad: phi }).fos;
          const f2 = geotech.bishop({ slices: s, cohesion_pa: c + dc, friction_angle_rad: phi }).fos;
          return f2 >= f1;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-28 · Spencer's factor of safety is strictly ordered in the cohesion on the hand case (0, 2, 5, 10, 20 kPa)", () => {
    const f = [0, 2e3, 5e3, 10e3, 20e3].map(
      (c) => geotech.spencer({ slices: A3, cohesion_pa: c, friction_angle_rad: 25 * DEG }).fos,
    );
    for (let i = 1; i < f.length; i++) expect(f[i] as number).toBeGreaterThan(f[i - 1] as number);
  });

  it("P-018-29 · the factor of safety does not depend on the order of the slices (the slice list carries no absolute position, so a translation of the section cannot change it)", () => {
    fc.assert(
      fc.property(setArb, phiArb, fc.integer({ min: 1, max: 1000 }), (s, phi, seed) => {
        const shuffled = [...s].sort((a, b) => ((a.width_m * seed) % 7) - ((b.width_m * seed) % 7));
        const a = geotech.bishop({ slices: s, cohesion_pa: 1e4, friction_angle_rad: phi }).fos;
        const b = geotech.bishop({ slices: shuffled, cohesion_pa: 1e4, friction_angle_rad: phi }).fos;
        return Math.abs(a - b) <= 1e-9 * Math.abs(a);
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-30 · similarity: scaling lengths and c' by k (weights by k^2, pore pressures by k, phi' fixed) leaves the factor of safety unchanged", () => {
    fc.assert(
      fc.property(setArb, phiArb, fc.double({ min: 0.1, max: 10, noNaN: true }), (s, phi, k) => {
        const scaled = s.map((x) => ({
          width_m: x.width_m * k,
          weight_n_per_m: x.weight_n_per_m * k * k,
          base_angle_rad: x.base_angle_rad,
          pore_pressure_pa: x.pore_pressure_pa * k,
        }));
        const a = geotech.bishop({ slices: s, cohesion_pa: 1e4, friction_angle_rad: phi }).fos;
        const b = geotech.bishop({ slices: scaled, cohesion_pa: 1e4 * k, friction_angle_rad: phi }).fos;
        return Math.abs(a - b) <= 1e-9 * Math.abs(a);
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-30 · the same similarity holds for Spencer on the hand case (k = 0.1, 3, 10)", () => {
    const base = geotech.spencer({ slices: A3, cohesion_pa: 5e3, friction_angle_rad: 25 * DEG }).fos;
    for (const k of [0.1, 3, 10]) {
      const scaled = A3.map((x) => ({
        width_m: x.width_m * k,
        weight_n_per_m: x.weight_n_per_m * k * k,
        base_angle_rad: x.base_angle_rad,
        pore_pressure_pa: x.pore_pressure_pa * k,
      }));
      const f = geotech.spencer({ slices: scaled, cohesion_pa: 5e3 * k, friction_angle_rad: 25 * DEG }).fos;
      expect(Math.abs(f - base)).toBeLessThanOrEqual(1e-9 * base);
    }
  });
});

describe("inverse velocity (FR-018-51, P-018-31, P-018-32, P-018-33, P-018-76)", () => {
  const DAY = 86400;
  const voight = (A: number, tf: number, times: number[]) =>
    times.map((t_s) => ({ t_s, velocity_m_per_s: 1 / (A * (tf - t_s)) }));

  it("FR-018-51 · the noise-free alpha = 2 series of minephys 7.4 (A = 10 /m, t_f = 10 days, days 0 to 6) gives t_f = 864,000 s, slope -10, intercept 8.64e6, r2 = 1", () => {
    const record = voight(
      10,
      864000,
      [0, 1, 2, 3, 4, 5, 6].map((d) => d * DAY),
    );
    expect(record[0]?.velocity_m_per_s).toBeCloseTo(1.1574074e-7, 14);
    const r = geotech.inverse_velocity({ record });
    expect(r.accelerating).toBe(true);
    expect(Math.abs((r.failure_time_s as number) - 864000)).toBeLessThanOrEqual(1e-12 * 864000);
    expect(r.slope_per_m).toBeCloseTo(-10, 9);
    expect(Math.abs(r.intercept_s_per_m - 8.64e6)).toBeLessThanOrEqual(1e-9 * 8.64e6);
    expect(r.r_squared).toBeCloseTo(1, 12);
    expect(r.n_used).toBe(7);
  });

  it("FR-018-51 · a window of 3 uses only the last 3 samples (and still recovers t_f on a noise-free series)", () => {
    const record = voight(
      10,
      864000,
      [0, 1, 2, 3, 4, 5, 6].map((d) => d * DAY),
    );
    const r = geotech.inverse_velocity({ record, window: 3 });
    expect(r.n_used).toBe(3);
    expect(Math.abs((r.failure_time_s as number) - 864000)).toBeLessThanOrEqual(1e-9 * 864000);
  });

  it("FR-018-51 · a decelerating record (1/v rising) is not accelerating and has no failure time", () => {
    const record = [0, 1, 2, 3, 4].map((d) => ({ t_s: d * DAY, velocity_m_per_s: 1e-7 / (1 + d) }));
    const r = geotech.inverse_velocity({ record });
    expect(r.accelerating).toBe(false);
    expect("failure_time_s" in r).toBe(false);
    expect(r.slope_per_m).toBeGreaterThanOrEqual(0);
  });

  it("P-018-33 · twenty hand-parametrised Voight alpha = 2 series return their true failure time (rtol 1e-12)", () => {
    for (let i = 0; i < 20; i++) {
      const tf = 864000 * (1 + i / 4);
      const A = 5 + 2 * i;
      const n = 6 + i;
      const times = Array.from({ length: n }, (_, k) => (0.8 * tf * k) / (n - 1));
      const r = geotech.inverse_velocity({ record: voight(A, tf, times) });
      expect(Math.abs((r.failure_time_s as number) - tf), `series ${i}`).toBeLessThanOrEqual(1e-12 * tf);
    }
  });

  // t_f in [1e7, 1e8] s and A in [10, 100] /m keep every velocity (and k x velocity, or 3600 x velocity) far below the 0.01 m/s cap of the schema
  const recordArb = fc
    .record({
      tf: fc.double({ min: 1e7, max: 1e8, noNaN: true }),
      A: fc.double({ min: 10, max: 100, noNaN: true }),
      n: fc.integer({ min: 3, max: 60 }),
      frac: fc.double({ min: 0.3, max: 0.9, noNaN: true }),
    })
    .map(({ tf, A, n, frac }) => ({
      tf,
      A,
      times: Array.from({ length: n }, (_, k) => (frac * tf * k) / (n - 1)),
    }));

  it("P-018-31 · shifting every observation time by delta shifts the predicted failure time by delta (rtol 1e-12 of the record span)", () => {
    fc.assert(
      fc.property(recordArb, fc.double({ min: -1e6, max: 1e6, noNaN: true }), ({ tf, A, times }, delta) => {
        const base = geotech.inverse_velocity({ record: voight(A, tf, times) });
        const moved = geotech.inverse_velocity({
          record: voight(A, tf, times).map((p) => ({
            t_s: p.t_s + delta,
            velocity_m_per_s: p.velocity_m_per_s,
          })),
        });
        const span = (times[times.length - 1] as number) - (times[0] as number);
        return (
          Math.abs((moved.failure_time_s as number) - ((base.failure_time_s as number) + delta)) <=
          1e-12 * span + 1e-9
        );
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-32 · multiplying every velocity by k > 0 leaves the predicted failure time unchanged (rtol 1e-12)", () => {
    fc.assert(
      fc.property(recordArb, fc.double({ min: 1e-3, max: 1e3, noNaN: true }), ({ tf, A, times }, k) => {
        const base = geotech.inverse_velocity({ record: voight(A, tf, times) }).failure_time_s as number;
        const scaled = geotech.inverse_velocity({
          record: voight(A, tf, times).map((p) => ({ t_s: p.t_s, velocity_m_per_s: p.velocity_m_per_s * k })),
        }).failure_time_s as number;
        return Math.abs(scaled - base) <= 1e-12 * Math.abs(base);
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-76 · expressing times in hours and velocities per hour predicts the same failure instant (rtol 1e-12)", () => {
    fc.assert(
      fc.property(recordArb, ({ tf, A, times }) => {
        const seconds = geotech.inverse_velocity({ record: voight(A, tf, times) }).failure_time_s as number;
        const hours = geotech.inverse_velocity({
          record: voight(A, tf, times).map((p) => ({
            t_s: p.t_s / 3600,
            velocity_m_per_s: p.velocity_m_per_s * 3600,
          })),
        }).failure_time_s as number;
        return Math.abs(hours * 3600 - seconds) <= 1e-12 * Math.abs(seconds);
      }),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · hostile records: times not strictly increasing, a non-positive velocity, fewer than 3 samples and a window below 3 are E_RANGE or E_SCHEMA", () => {
    const ok = voight(
      10,
      864000,
      [0, 1, 2, 3].map((d) => d * DAY),
    );
    const repeated = ok.map((p, i) => (i === 2 ? { ...p, t_s: (ok[1] as { t_s: number }).t_s } : p));
    expect(["E_RANGE", "E_SCHEMA"]).toContain(codeOf(() => geotech.inverse_velocity({ record: repeated })));
    const zero = ok.map((p, i) => (i === 1 ? { ...p, velocity_m_per_s: 0 } : p));
    expect(["E_RANGE", "E_SCHEMA"]).toContain(codeOf(() => geotech.inverse_velocity({ record: zero })));
    const negative = ok.map((p, i) => (i === 1 ? { ...p, velocity_m_per_s: -1e-7 } : p));
    expect(["E_RANGE", "E_SCHEMA"]).toContain(codeOf(() => geotech.inverse_velocity({ record: negative })));
    expect(["E_RANGE", "E_SCHEMA"]).toContain(
      codeOf(() => geotech.inverse_velocity({ record: ok.slice(0, 2) })),
    );
    expect(["E_RANGE", "E_SCHEMA"]).toContain(
      codeOf(() => geotech.inverse_velocity({ record: ok, window: 2 })),
    );
  });
});

describe("Bayesian failure band (FR-018-51)", () => {
  const DAY = 86400;
  const record = [0, 1, 2, 3, 4, 5, 6].map((d) => ({
    t_s: d * DAY,
    velocity_m_per_s: 1 / (10 * (864000 - d * DAY)),
  }));
  // flat prior, known sigma = 4.32e4 s/m (minephys 7.4): posterior covariance = sigma^2 (X'X)^-1, mean = OLS
  const sigma = 4.32e4;
  const ts = record.map((p) => p.t_s);
  const n = ts.length;
  const st = ts.reduce((a, b) => a + b, 0);
  const stt = ts.reduce((a, b) => a + b * b, 0);
  const det = n * stt - st * st;
  const cov = [
    [(sigma ** 2 * stt) / det, (-(sigma ** 2) * st) / det],
    [(-(sigma ** 2) * st) / det, (sigma ** 2 * n) / det],
  ];

  it("FR-018-51 · the posterior of a flat prior is the OLS fit with covariance sigma^2 (X'X)^-1 (8.66468571e8, 8.92857143e-3 on the diagonal)", () => {
    const r = geotech.failure_band({
      record,
      seed: 7,
      n_draws: 1000,
      noise_sd_s_per_m: sigma,
      credible: 0.9,
    });
    expect(r.posterior_mean[0]).toBeCloseTo(8.64e6, 3);
    expect(r.posterior_mean[1]).toBeCloseTo(-10, 9);
    const pc = r.posterior_cov as number[][];
    expect((pc[0]?.[0] as number) / 8.66468571e8).toBeCloseTo(1, 8);
    expect((pc[1]?.[1] as number) / 8.92857143e-3).toBeCloseTo(1, 8);
    expect((pc[0]?.[1] as number) / ((cov[0] as number[])[1] as number)).toBeCloseTo(1, 9);
    expect(pc[1]?.[0]).toBe(pc[0]?.[1]);
  });

  it("FR-018-51 · the median and the 90 % equal-tailed band of t_f agree with the analytical quantiles 864,000, 854,367.67 and 873,924.60 s within sampling error (200 s)", () => {
    const r = geotech.failure_band({
      record,
      seed: 20261007,
      n_draws: 100000,
      noise_sd_s_per_m: sigma,
      credible: 0.9,
    });
    expect(r.status).toBe("band");
    expect(Math.abs((r.median_s as number) - 864000)).toBeLessThan(200);
    expect(Math.abs((r.lower_s as number) - 854367.67)).toBeLessThan(200);
    expect(Math.abs((r.upper_s as number) - 873924.6)).toBeLessThan(200);
    expect(r.fraction_not_accelerating).toBe(0);
  });

  it("FR-018-51 · the same seed gives the same band and a different seed a different one", () => {
    const run = (seed: number) =>
      geotech.failure_band({ record, seed, n_draws: 2000, noise_sd_s_per_m: sigma, credible: 0.9 });
    expect(run(5)).toEqual(run(5));
    expect(run(5).median_s).not.toBe(run(6).median_s);
  });

  it("FR-018-51 · a clearly decelerating record leaves no accelerating draw: status no-accelerating-draw and fraction 1", () => {
    const slow = [0, 1, 2, 3, 4, 5].map((d) => ({ t_s: d * DAY, velocity_m_per_s: 1e-7 / (1 + d) }));
    const r = geotech.failure_band({ record: slow, seed: 1, n_draws: 200, noise_sd_s_per_m: 1 });
    expect(r.status).toBe("no-accelerating-draw");
    expect(r.fraction_not_accelerating).toBe(1);
    expect("median_s" in r).toBe(false);
  });
});

describe("Monte-Carlo probability of failure (FR-018-52)", () => {
  // minephys 7.4: phi' = 0 slices, c' ~ N(10 kPa, 2 kPa): F ~ N(1.4623899, 0.2924780), PoF = Phi(-1.58094) = 0.056946
  const hand = 0.056945964167333;
  const N = 20000;
  const args = (seed: number) => ({
    surfaces: [P0],
    method: "bishop" as const,
    n_samples: N,
    seed,
    cohesion_pa: { distribution: "normal" as const, mean: 10e3, sd: 2e3 },
    friction_angle_rad: { distribution: "normal" as const, mean: 0, sd: 1e-9 },
  });

  it("FR-018-52 · on the phi' = 0 slices with c' ~ N(10, 2) kPa the PoF is within 3 sqrt(p(1-p)/N) + 1/N of Phi(-1.58094) = 0.056946", () => {
    const bound = 3 * Math.sqrt((hand * (1 - hand)) / N) + 1 / N;
    for (const seed of [20261007, 1, 99]) {
      const r = geotech.pof_monte_carlo(args(seed));
      expect(r.n_samples).toBe(N);
      expect(r.pof).toBe(r.failures / N);
      expect(Math.abs(r.pof - hand)).toBeLessThanOrEqual(bound);
      expect(r.wilson_low).toBeLessThanOrEqual(r.pof);
      expect(r.wilson_high).toBeGreaterThanOrEqual(r.pof);
      expect(r.wilson_low).toBeGreaterThanOrEqual(0);
      expect(r.wilson_high).toBeLessThanOrEqual(1);
    }
  }, 120_000);

  it("FR-018-52 · the same seed gives the same count; different seeds give different counts", () => {
    const a = geotech.pof_monte_carlo(args(5)).failures;
    expect(geotech.pof_monte_carlo(args(5)).failures).toBe(a);
    expect(new Set([1, 2, 3, 4].map((s) => geotech.pof_monte_carlo(args(s)).failures)).size).toBeGreaterThan(
      1,
    );
  }, 120_000);

  it("FR-018-52 · with a strong wall (c' ~ N(50, 1) kPa on the same slices) no sample fails and the Wilson interval starts at 0", () => {
    const r = geotech.pof_monte_carlo({
      ...args(3),
      n_samples: 2000,
      cohesion_pa: { distribution: "normal", mean: 50e3, sd: 1e3 },
    });
    expect(r.failures).toBe(0);
    expect(r.pof).toBe(0);
    expect(r.wilson_low).toBeCloseTo(0, 12);
    expect(r.wilson_high).toBeGreaterThan(0);
  });

  it("FR-018-52 · pof_from_samples counts the samples whose factor of safety is below 1: hand case c' in {5000, 6838, 6839, 8000, 10000, 12000} Pa gives 2 failures of 6", () => {
    // F(c') = c' x 1.4623899e-4 on the phi' = 0 slices, so F < 1 iff c' < 6838.2 Pa
    const samples = [5000, 6838, 6839, 8000, 10000, 12000].map((c) => ({
      cohesion_pa: c,
      friction_angle_rad: 0,
    }));
    const r = geotech.pof_from_samples({ surfaces: [P0], method: "bishop", samples });
    expect(r.n_samples).toBe(6);
    expect(r.failures).toBe(2);
    expect(r.pof).toBeCloseTo(1 / 3, 12);
  });

  it("FR-018-52 · adding a second surface can only raise the failure count (the probability is over the weakest surface)", () => {
    const heavier = P0.map((s) => ({ ...s, weight_n_per_m: s.weight_n_per_m * 2 }));
    const samples = [5000, 6838, 6839, 8000, 10000, 12000].map((c) => ({
      cohesion_pa: c,
      friction_angle_rad: 0,
    }));
    const one = geotech.pof_from_samples({ surfaces: [P0], method: "bishop", samples }).failures;
    const two = geotech.pof_from_samples({ surfaces: [P0, heavier], method: "bishop", samples }).failures;
    expect(two).toBeGreaterThanOrEqual(one);
  });

  it("FR-018-52 · hostile: n_samples 0, a negative seed and an unknown distribution are rejected", () => {
    expect(["E_RANGE", "E_SCHEMA"]).toContain(
      codeOf(() => geotech.pof_monte_carlo({ ...args(1), n_samples: 0 })),
    );
    expect(["E_RANGE", "E_SCHEMA"]).toContain(
      codeOf(() => geotech.pof_monte_carlo({ ...args(-1), n_samples: 10 })),
    );
    expect(["E_RANGE", "E_SCHEMA"]).toContain(
      codeOf(() =>
        geotech.pof_monte_carlo({
          ...args(1),
          n_samples: 10,
          cohesion_pa: { distribution: "weibull" as never, mean: 1, sd: 1 },
        }),
      ),
    );
  });

  it("FR-018-52 · the reference's failing-sample count is reproduced exactly on the fixture's sample matrix", () => {
    const fixtures = loadParityFixtures("geotech").filter((f) => f.function === "pof_from_samples");
    expect(
      fixtures.length,
      "a monte-carlo-count fixture for geotech.pof_from_samples exists",
    ).toBeGreaterThan(0);
    for (const fx of fixtures) {
      expect(fx.tolerance.class).toBe("monte-carlo-count");
      for (const [i, v] of fx.cases.entries()) {
        const samples = (v.variates?.samples ?? []).map(([c, phi]) => ({
          cohesion_pa: c as number,
          friction_angle_rad: phi as number,
        }));
        expect(samples.length, `${fx.file} #${i}: sample matrix`).toBeGreaterThan(0);
        const r = geotech.pof_from_samples({
          ...(v.input as { surfaces: Slice[][]; method: "bishop" }),
          samples,
        });
        const expected = (v.output.failures ?? v.output.failing_samples) as number;
        expect(r.failures, `${fx.file} #${i}`).toBe(expected);
      }
    }
  });
});

describe("slope-radar line of sight (FR-018-51, P-018-34, P-018-35, P-018-36)", () => {
  const radar = [0, 0, 0] as [number, number, number];

  it("FR-018-51 · radar at the origin, target (1000, 0, 0), u = (-0.01, 0.01, 0): d = -0.01 m (toward the radar)", () => {
    const r = geotech.slope_radar_los({
      radar_position_m: radar,
      targets_m: new Float64Array([1000, 0, 0]),
      displacements_m: new Float64Array([-0.01, 0.01, 0]),
    });
    expect(r.los_m).toHaveLength(1);
    expect(r.los_m[0]).toBeCloseTo(-0.01, 15);
  });

  it("FR-018-51 · a displacement of 0.02 m at 60 deg to the line of sight projects to 0.01 m (hand: 0.02 cos 60 deg)", () => {
    const u = [0.02 * Math.cos(60 * DEG), 0.02 * Math.sin(60 * DEG), 0];
    const r = geotech.slope_radar_los({
      radar_position_m: radar,
      targets_m: new Float64Array([1000, 0, 0]),
      displacements_m: new Float64Array(u),
    });
    expect(r.los_m[0]).toBeCloseTo(0.01, 12);
  });

  it("FR-018-51 · it works per pixel on many pixels, and number[] buffers are accepted", () => {
    const targets = [1000, 0, 0, 0, 500, 0, 0, 0, 200];
    const disp = [0.01, 0, 0, 0, 0.02, 0, 0, 0, -0.03];
    const r = geotech.slope_radar_los({
      radar_position_m: radar,
      targets_m: targets as never,
      displacements_m: disp as never,
    });
    expect(Array.from(r.los_m)).toEqual([0.01, 0.02, -0.03]);
  });

  const vec = fc.tuple(
    fc.double({ min: -5e3, max: 5e3, noNaN: true }),
    fc.double({ min: -5e3, max: 5e3, noNaN: true }),
    fc.double({ min: -5e3, max: 5e3, noNaN: true }),
  );
  const small = fc.tuple(
    fc.double({ min: -0.5, max: 0.5, noNaN: true }),
    fc.double({ min: -0.5, max: 0.5, noNaN: true }),
    fc.double({ min: -0.5, max: 0.5, noNaN: true }),
  );
  const far = vec.filter(([x, y, z]) => Math.hypot(x, y, z) > 10);
  const los = (p: number[], t: number[], d: number[]) =>
    geotech.slope_radar_los({
      radar_position_m: p as [number, number, number],
      targets_m: new Float64Array(t),
      displacements_m: new Float64Array(d),
    }).los_m[0] as number;

  it("P-018-34 · the line of sight is linear in the displacement: LOS(a d1 + b d2) = a LOS(d1) + b LOS(d2)", () => {
    fc.assert(
      fc.property(
        far,
        small,
        small,
        fc.double({ min: -3, max: 3, noNaN: true }),
        fc.double({ min: -3, max: 3, noNaN: true }),
        (t, d1, d2, a, b) => {
          const lhs = los(
            radar,
            t,
            d1.map((x, i) => a * x + b * (d2[i] as number)),
          );
          const rhs = a * los(radar, t, d1) + b * los(radar, t, d2);
          return Math.abs(lhs - rhs) <= 1e-12 * Math.max(1, Math.abs(rhs)) + 1e-14;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-35 · a displacement perpendicular to the line of sight projects to 0 (atol 1e-12 m) and a parallel one to +-|d|", () => {
    fc.assert(
      fc.property(far, fc.double({ min: -1, max: 1, noNaN: true }), (t, mag) => {
        const norm = Math.hypot(...t);
        const e = t.map((x) => x / norm);
        // any vector perpendicular to e: cross(e, helper)
        const helper = Math.abs(e[0] as number) < 0.9 ? [1, 0, 0] : [0, 1, 0];
        const h = helper as [number, number, number];
        const ev = e as [number, number, number];
        const perp = [ev[1] * h[2] - ev[2] * h[1], ev[2] * h[0] - ev[0] * h[2], ev[0] * h[1] - ev[1] * h[0]];
        const pn = Math.hypot(...perp);
        const dPerp = perp.map((x) => (x / pn) * mag);
        const dPar = e.map((x) => x * mag);
        return Math.abs(los(radar, t, dPerp)) <= 1e-12 && Math.abs(los(radar, t, dPar) - mag) <= 1e-12;
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-36 · rotating the scene and the radar together leaves every LOS value unchanged (rtol 1e-12)", () => {
    const rot = (axis: number[], angle: number) => {
      const n = Math.hypot(...axis);
      const [x, y, z] = axis.map((v) => v / n) as [number, number, number];
      const c = Math.cos(angle);
      const s = Math.sin(angle);
      const C = 1 - c;
      return [
        [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
        [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
        [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
      ];
    };
    const apply = (m: number[][], v: number[]) =>
      (m as number[][]).map((row) => row.reduce((acc, r, i) => acc + r * (v[i] as number), 0));
    fc.assert(
      fc.property(
        vec,
        far,
        small,
        vec.filter(([x, y, z]) => Math.hypot(x, y, z) > 0.1),
        fc.double({ min: 0, max: 6.28, noNaN: true }),
        (p, t, d, axis, angle) => {
          const R = rot(axis, angle);
          const tRel = t.map((x, i) => x - (p[i] as number));
          if (Math.hypot(...tRel) < 10) return true;
          const base = los(p, t, d);
          const turned = los(apply(R, p), apply(R, t), apply(R, d));
          return Math.abs(turned - base) <= 1e-12 * Math.max(1, Math.abs(base)) + 1e-14;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · hostile: a target at the radar position is E_RANGE; buffers of different length or not a multiple of 3 are E_SCHEMA", () => {
    expect(codeOf(() => los(radar, [0, 0, 0], [1, 0, 0]))).toBe("E_RANGE");
    expect(
      codeOf(() =>
        geotech.slope_radar_los({
          radar_position_m: radar,
          targets_m: new Float64Array([1, 0, 0, 2, 0, 0]),
          displacements_m: new Float64Array([1, 0, 0]),
        }),
      ),
    ).toBe("E_SCHEMA");
    expect(
      codeOf(() =>
        geotech.slope_radar_los({
          radar_position_m: radar,
          targets_m: new Float64Array([1, 0]),
          displacements_m: new Float64Array([1, 0]),
        }),
      ),
    ).toBe("E_SCHEMA");
  });
});

describe("parity with minephys.geotech (FR-018-51)", () => {
  it("FR-018-51 · bishop equals the reference on its fixture (>= 200 vectors, both ends of the validity ranges)", () => {
    expectAnalyticalParity("geotech", "bishop", (args) => geotech.bishop(args as never));
  });
  it("FR-018-51 · spencer equals the reference on its fixture", () => {
    expectAnalyticalParity("geotech", "spencer", (args) => geotech.spencer(args as never));
  });
  it("FR-018-51 · inverse_velocity equals the reference on its fixture", () => {
    expectAnalyticalParity("geotech", "inverse_velocity", (args) => geotech.inverse_velocity(args as never));
  });
  it("FR-018-51 · slope_radar_los equals the reference on its fixture", () => {
    expectAnalyticalParity("geotech", "slope_radar_los", (args) => geotech.slope_radar_los(args as never));
  });
});
