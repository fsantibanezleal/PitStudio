// T-018-068 [red] · FR-018-51 (blasting port, parity within 1e-12 s_y + rtol |y|), P-018-40 (Kuz-Ram x50 non-increasing in powder factor),
// P-018-41 (Swebrec anchors and monotonicity), P-018-42 (PPV square-root scaling) for the `blasting` engine of spec 018.
//
// Expected API (module `~/engines/analytical/blasting`, file web/src/engines/analytical/blasting/index.ts). Every function takes the `args`
// of its DC-018-02 request and returns the `result` object (specs/018-web-cases/contracts/engines/blasting.schema.json), SI, snake_case:
//     charge_per_hole(args)       -> { charge_kg }
//     powder_factor(args)         -> { powder_factor_kg_per_m3 }
//     kuznetsov_x50(args)         -> { x50_m }                      `variant` "cunningham1983" (default, exponent 19/30) or "cunningham2005" (19/20)
//     uniformity_index(args)      -> { uniformity }
//     swebrec_passing(args)       -> { passing }                    one value per entry of `sizes_m` (an array or Float64Array)
//     kco_undulation(args)        -> { undulation }
//     ppv_scaled_distance(args)   -> { scaled_distance_m_per_kg_half, ppv_m_per_s }
//     flyrock_range_no_drag(args) -> { range_m }                    `gravity_m_per_s2` defaults to 9.80665
//   A value outside the validity range of the schema throws an error with `code === "E_RANGE"`, a malformed argument or conditional rule
//   `E_SCHEMA` (FR-018-38 typed errors; FR-018-51 for the E_RANGE of the validity ranges).
//
// Oracles (independent of the code under test):
//   - minephys spec 002 section 7.4 worked example (spec writer's hand calculation, recomputed with numpy on 2026-10-11): rho_e = 850 kg/m3,
//     d = 0.25 m, L_c = 7.2 m, B = 6 m, S = 7 m, H = 12 m, A = 7, RWS = 100, W = 0.3 m, single column, xmax = 1.5 m:
//     charge 300.41480 kg, powder factor 0.59606111 kg/m3, x50 0.29940630 m (1983) and 0.31295501 m (2005), uniformity 1.1164546,
//     undulation 2.4940490, Swebrec x80 0.59521759 m, oversize > 1 m 3.1027 %, fines < 0.05 m 13.434 %;
//     PPV(300 m, 150 kg, K = 1, beta = 1.6) = 5.9907197e-3 m/s at the scaled distance 24.494897; flyrock range 163.15459 m (40 m/s, 45 deg).
//   - Cunningham (2005) eq. 1: x50 = A K^-0.8 Q^(1/6) (115 / RWS)^e (cm), Swebrec (Ouchterlony 2005): P = 1 / (1 + [ln(xmax/x) / ln(xmax/x50)]^b),
//     KCO link b = 2 ln 2 ln(xmax/x50) n, flyrock range v0^2 sin(2 theta) / g; the metamorphic relations of spec 018 section 4.
//   - the parity fixtures of the reference (`minephys.blasting`), DC-018-04, through web/src/test-support/parity-fixtures.ts.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as blasting from "~/engines/analytical/blasting";
import { expectAnalyticalParity } from "~/test-support/parity-fixtures";

function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}
const num = (r: unknown, key: string) => (r as Record<string, number>)[key] as number;
const close = (a: number, b: number, rtol: number) => Math.abs(a - b) <= rtol * Math.abs(b);

const CHARGE = 300.41479749952396;
const PF = 0.5960611061498491;
const X50 = 0.29940629803336255;
const UNIFORMITY = 1.116454646043959;

describe("worked example of minephys 7.4 (FR-018-51)", () => {
  it("FR-018-51 · charge per hole 300.41480 kg and powder factor 0.59606111 kg/m3", () => {
    const q = num(
      blasting.charge_per_hole({
        explosive_density_kg_per_m3: 850,
        hole_diameter_m: 0.25,
        charge_length_m: 7.2,
      }),
      "charge_kg",
    );
    expect(close(q, CHARGE, 1e-12)).toBe(true);
    expect(Math.abs(q - 300.4148)).toBeLessThan(5e-6);
    const k = num(
      blasting.powder_factor({ charge_kg: CHARGE, burden_m: 6, spacing_m: 7, bench_height_m: 12 }),
      "powder_factor_kg_per_m3",
    );
    expect(close(k, PF, 1e-12)).toBe(true);
    expect(Math.abs(k - 0.59606111)).toBeLessThan(5e-9);
  });

  it("FR-018-51 · Kuznetsov x50: 0.29940630 m by default (Cunningham 1983) and 0.31295501 m for cunningham2005, ratio 1.0452519", () => {
    const base = { rock_factor: 7, powder_factor_kg_per_m3: PF, charge_kg: CHARGE, rws: 100 };
    const a = num(blasting.kuznetsov_x50(base), "x50_m");
    const b = num(blasting.kuznetsov_x50({ ...base, variant: "cunningham2005" }), "x50_m");
    expect(close(a, X50, 1e-12)).toBe(true);
    expect(close(b, 0.3129550142277008, 1e-12)).toBe(true);
    expect(Math.abs(a - 0.2994063)).toBeLessThan(5e-9);
    expect(Math.abs(b - 0.31295501)).toBeLessThan(5e-9);
    expect(Math.abs(b / a - 1.0452519)).toBeLessThan(5e-8);
    expect(num(blasting.kuznetsov_x50({ ...base, variant: "cunningham1983" }), "x50_m")).toBe(a);
  });

  it("FR-018-51 · uniformity index 1.1164546 (single column: bottom and column charge lengths omitted) and the explicit equivalent (BCL = L, CCL = 0)", () => {
    const args = {
      burden_m: 6,
      spacing_m: 7,
      hole_diameter_m: 0.25,
      charge_length_m: 7.2,
      bench_height_m: 12,
      drilling_deviation_m: 0.3,
    };
    const n = num(blasting.uniformity_index(args), "uniformity");
    expect(close(n, UNIFORMITY, 1e-12)).toBe(true);
    expect(Math.abs(n - 1.1164546)).toBeLessThan(5e-8);
    const explicit = num(
      blasting.uniformity_index({ ...args, bottom_charge_length_m: 7.2, column_charge_length_m: 0 }),
      "uniformity",
    );
    expect(close(explicit, n, 1e-12)).toBe(true);
  });

  it("FR-018-51 · KCO undulation: 2 ln 2 ln(xmax/x50) n = 2.4940490", () => {
    const b = num(
      blasting.kco_undulation({ uniformity: 1.1164546, x50_m: 0.2994063, xmax_m: 1.5 }),
      "undulation",
    );
    expect(Math.abs(b - 2.494049)).toBeLessThan(5e-7);
    expect(
      close(
        num(blasting.kco_undulation({ uniformity: UNIFORMITY, x50_m: X50, xmax_m: 1.5 }), "undulation"),
        2.4940490458451468,
        1e-12,
      ),
    ).toBe(true);
  });

  it("FR-018-51 · Swebrec passing: x80 0.59521759 m gives 0.8, > 1 m is 3.1027 %, < 0.05 m is 13.434 %, 0.5 at x50 and 1 at and beyond xmax", () => {
    const sizes = [0.05, 0.2994063, 0.59521759, 1.0, 1.4, 1.5, 2.0];
    const p = Array.from(
      (
        blasting.swebrec_passing({ sizes_m: sizes, x50_m: 0.2994063, xmax_m: 1.5, undulation: 2.494049 }) as {
          passing: ArrayLike<number>;
        }
      ).passing,
    );
    expect(p).toHaveLength(7);
    expect(Math.abs((p[0] as number) - 0.13434)).toBeLessThan(5e-6);
    expect(Math.abs((p[1] as number) - 0.5)).toBeLessThan(1e-7);
    expect(Math.abs((p[2] as number) - 0.8)).toBeLessThan(1e-7);
    expect(Math.abs((p[3] as number) - (1 - 0.031027))).toBeLessThan(5e-7);
    expect(Math.abs((p[4] as number) - 0.999613664)).toBeLessThan(5e-8);
    expect(p[5]).toBe(1);
    expect(p[6]).toBe(1);
  });

  it("FR-018-51 · PPV by scaled distance: SD = 24.494897 m/kg^0.5 and PPV = K SD^-beta = 5.9907197e-3 m/s", () => {
    const r = blasting.ppv_scaled_distance({
      distance_m: 300,
      charge_per_delay_kg: 150,
      k_site_m_per_s: 1,
      site_exponent: 1.6,
    });
    expect(close(num(r, "scaled_distance_m_per_kg_half"), 24.49489742783178, 1e-12)).toBe(true);
    expect(close(num(r, "ppv_m_per_s"), 0.005990719697896703, 1e-12)).toBe(true);
    expect(Math.abs(num(r, "ppv_m_per_s") - 5.9907197e-3)).toBeLessThan(5e-11);
  });

  it("FR-018-51 · drag-free flyrock range v0^2 sin(2 theta) / g = 163.15459 m for 40 m/s at 45 deg; g is an option", () => {
    expect(
      close(
        num(
          blasting.flyrock_range_no_drag({ launch_speed_m_per_s: 40, launch_angle_rad: Math.PI / 4 }),
          "range_m",
        ),
        163.15459407646853,
        1e-12,
      ),
    ).toBe(true);
    expect(
      close(
        num(
          blasting.flyrock_range_no_drag({
            launch_speed_m_per_s: 40,
            launch_angle_rad: Math.PI / 4,
            gravity_m_per_s2: 9.81,
          }),
          "range_m",
        ),
        1600 / 9.81,
        1e-12,
      ),
    ).toBe(true);
  });
});

describe("hostile blasting inputs (FR-018-51, FR-018-38)", () => {
  const kuz = { rock_factor: 7, powder_factor_kg_per_m3: 0.6, charge_kg: 300, rws: 100 };
  it("FR-018-51 · a rock factor outside Cunningham's 0.8-22, a powder factor above 5 kg/m3 and an RWS below 20 are E_RANGE", () => {
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, rock_factor: 0.79 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, rock_factor: 22.01 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, powder_factor_kg_per_m3: 5.01 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, powder_factor_kg_per_m3: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, rws: 19.9 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, charge_kg: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kuznetsov_x50({ ...kuz, variant: "cunningham1999" as never }))).toBe(
      "E_SCHEMA",
    );
  });

  it("FR-018-51 · the uniformity factors leaving their domain (14 B / d >= 2.2, W >= B, BCL + CCL > L) are E_RANGE; only one of BCL and CCL is E_SCHEMA", () => {
    const u = {
      burden_m: 6,
      spacing_m: 7,
      hole_diameter_m: 0.25,
      charge_length_m: 7.2,
      bench_height_m: 12,
      drilling_deviation_m: 0.3,
    };
    expect(codeOf(() => blasting.uniformity_index({ ...u, burden_m: 20, hole_diameter_m: 0.1 }))).toBe(
      "E_RANGE",
    );
    expect(codeOf(() => blasting.uniformity_index({ ...u, drilling_deviation_m: 6 }))).toBe("E_RANGE");
    expect(
      codeOf(() => blasting.uniformity_index({ ...u, bottom_charge_length_m: 5, column_charge_length_m: 5 })),
    ).toBe("E_RANGE");
    expect(codeOf(() => blasting.uniformity_index({ ...u, bottom_charge_length_m: 5 }))).toBe("E_SCHEMA");
  });

  it("FR-018-51 · Swebrec with x50 >= xmax is E_RANGE; an empty size list is E_SCHEMA; a non-positive size is E_RANGE", () => {
    const s = { sizes_m: [0.1, 0.5], x50_m: 0.3, xmax_m: 1.5, undulation: 2 };
    expect(codeOf(() => blasting.swebrec_passing({ ...s, x50_m: 1.5 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.swebrec_passing({ ...s, x50_m: 2 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.swebrec_passing({ ...s, sizes_m: [] }))).toBe("E_SCHEMA");
    expect(codeOf(() => blasting.swebrec_passing({ ...s, sizes_m: [0.1, 0] }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.kco_undulation({ uniformity: 1, x50_m: 1.5, xmax_m: 1.5 }))).toBe("E_RANGE");
  });

  it("FR-018-51 · a flyrock angle above 90 deg or a negative one is E_RANGE; a non-positive distance or charge in the PPV law is E_RANGE", () => {
    expect(
      codeOf(() => blasting.flyrock_range_no_drag({ launch_speed_m_per_s: 40, launch_angle_rad: 1.6 })),
    ).toBe("E_RANGE");
    expect(
      codeOf(() => blasting.flyrock_range_no_drag({ launch_speed_m_per_s: 40, launch_angle_rad: -0.1 })),
    ).toBe("E_RANGE");
    expect(
      codeOf(() => blasting.flyrock_range_no_drag({ launch_speed_m_per_s: 0, launch_angle_rad: 0.5 })),
    ).toBe("E_RANGE");
    const p = { distance_m: 300, charge_per_delay_kg: 150, k_site_m_per_s: 1, site_exponent: 1.6 };
    expect(codeOf(() => blasting.ppv_scaled_distance({ ...p, distance_m: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.ppv_scaled_distance({ ...p, charge_per_delay_kg: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => blasting.ppv_scaled_distance({ ...p, site_exponent: 0 }))).toBe("E_RANGE");
  });
});

describe("Kuz-Ram metamorphic relations (P-018-40)", () => {
  const arb = fc.record({
    A: fc.double({ min: 0.8, max: 22, noNaN: true }),
    K: fc.double({ min: 0.1, max: 3, noNaN: true }),
    Q: fc.double({ min: 1, max: 3000, noNaN: true }),
    RWS: fc.double({ min: 50, max: 200, noNaN: true }),
  });
  const x50 = (a: number, k: number, q: number, rws: number, variant = "cunningham1983") =>
    num(
      blasting.kuznetsov_x50({ rock_factor: a, powder_factor_kg_per_m3: k, charge_kg: q, rws, variant }),
      "x50_m",
    );

  it("P-018-40 · x50 is strictly decreasing in the powder factor and in RWS", () => {
    fc.assert(
      fc.property(arb, fc.double({ min: 1.01, max: 1.5, noNaN: true }), ({ A, K, Q, RWS }, f) => {
        return x50(A, K * f, Q, RWS) < x50(A, K, Q, RWS) && x50(A, K, Q, RWS * f) < x50(A, K, Q, RWS);
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-40 · x50 is linear in the rock factor and multiplies by 2 when the charge multiplies by 64 (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        arb.filter(({ Q, A }) => Q <= 1500 && A <= 14),
        fc.double({ min: 1, max: 1.5, noNaN: true }),
        ({ A, K, Q, RWS }, f) => {
          const base = x50(A, K, Q, RWS);
          const linear = close(x50(A * f, K, Q, RWS), base * f, 1e-12);
          return linear && close(x50(A, K, Q * 2 ** 6, RWS), 2 * base, 1e-12);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-40 · the two variants agree at RWS = 115 and their ratio is (115 / RWS)^(19/20 - 19/30) elsewhere (rtol 1e-12)", () => {
    fc.assert(
      fc.property(arb, ({ A, K, Q, RWS }) => {
        const ratio = x50(A, K, Q, RWS, "cunningham2005") / x50(A, K, Q, RWS);
        return (
          close(ratio, (115 / RWS) ** (19 / 20 - 19 / 30), 1e-12) &&
          close(x50(A, K, Q, 115, "cunningham2005"), x50(A, K, Q, 115), 1e-12)
        );
      }),
      { numRuns: 200 },
    );
  });
});

describe("Swebrec metamorphic relations (P-018-41)", () => {
  const passing = (sizes: number[], x50: number, xmax: number, b: number) =>
    Array.from(
      (
        blasting.swebrec_passing({ sizes_m: sizes, x50_m: x50, xmax_m: xmax, undulation: b }) as {
          passing: ArrayLike<number>;
        }
      ).passing,
    );
  const arb = fc.record({
    xmax: fc.double({ min: 0.2, max: 3, noNaN: true }),
    r: fc.double({ min: 0.05, max: 0.8, noNaN: true }),
    b: fc.double({ min: 0.5, max: 4, noNaN: true }),
  });

  it("P-018-41 · P(x50) = 0.5 (atol 1e-12), P(xmax) = 1, and P is non-decreasing in x", () => {
    fc.assert(
      fc.property(
        arb,
        fc.array(fc.double({ min: 0.001, max: 1, noNaN: true }), { minLength: 2, maxLength: 30 }),
        ({ xmax, r, b }, fr) => {
          const x50 = r * xmax;
          const at = passing([x50, xmax], x50, xmax, b);
          if (Math.abs((at[0] as number) - 0.5) > 1e-12 || at[1] !== 1) return false;
          const sizes = fr.map((f) => f * xmax).sort((p, q) => p - q);
          const p = passing(sizes, x50, xmax, b);
          return p.every((v, i) => i === 0 || v >= (p[i - 1] as number));
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-41 · sizes at and beyond xmax are exactly 1 and every value lies in [0, 1]", () => {
    fc.assert(
      fc.property(arb, fc.double({ min: 1, max: 5, noNaN: true }), ({ xmax, r, b }, f) => {
        const p = passing([xmax * f, 0.5 * xmax * r], r * xmax, xmax, b);
        return p[0] === 1 && (p[1] as number) >= 0 && (p[1] as number) <= 1;
      }),
      { numRuns: 200 },
    );
  });
});

describe("PPV scaled-distance scaling (P-018-42)", () => {
  const ppv = (d: number, w: number, k: number, beta: number) =>
    num(
      blasting.ppv_scaled_distance({
        distance_m: d,
        charge_per_delay_kg: w,
        k_site_m_per_s: k,
        site_exponent: beta,
      }),
      "ppv_m_per_s",
    );

  it("P-018-42 · PPV(kR, k^2 W) = PPV(R, W) (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 10, max: 1e4, noNaN: true }),
        fc.double({ min: 1, max: 5e3, noNaN: true }),
        fc.double({ min: 0.1, max: 10, noNaN: true }),
        fc.double({ min: 0.5, max: 100, noNaN: true }),
        fc.double({ min: 1, max: 2.5, noNaN: true }),
        (d, w, k, K, beta) => close(ppv(k * d, k * k * w, K, beta), ppv(d, w, K, beta), 1e-12),
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-42 · PPV is strictly decreasing in distance and strictly increasing in the charge per delay", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 10, max: 1e4, noNaN: true }),
        fc.double({ min: 1, max: 5e3, noNaN: true }),
        fc.double({ min: 1.01, max: 3, noNaN: true }),
        (d, w, f) => {
          return ppv(d * f, w, 1, 1.6) < ppv(d, w, 1, 1.6) && ppv(d, w * f, 1, 1.6) > ppv(d, w, 1, 1.6);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-42 · the flyrock range is symmetric about 45 deg, scales as v0^2 and as 1/g (rtol 1e-12)", () => {
    const range = (v: number, th: number, g?: number) =>
      num(
        blasting.flyrock_range_no_drag({
          launch_speed_m_per_s: v,
          launch_angle_rad: th,
          ...(g === undefined ? {} : { gravity_m_per_s2: g }),
        }),
        "range_m",
      );
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 300, noNaN: true }),
        fc.double({ min: 0.05, max: 1.5, noNaN: true }),
        fc.double({ min: 1.1, max: 3, noNaN: true }),
        (v, th, f) => {
          return (
            close(range(v, th), range(v, Math.PI / 2 - th), 1e-12) &&
            close(range(v * f, th), range(v, th) * f * f, 1e-12) &&
            close(range(v, th, 9.80665 * f), range(v, th) / f, 1e-12)
          );
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("parity with minephys.blasting (FR-018-51)", () => {
  const fns = [
    "charge_per_hole",
    "powder_factor",
    "kuznetsov_x50",
    "uniformity_index",
    "swebrec_passing",
    "kco_undulation",
    "ppv_scaled_distance",
    "flyrock_range_no_drag",
  ] as const;
  for (const fn of fns) {
    it(`FR-018-51 · ${fn} equals the reference on its fixture (>= 200 vectors, both ends of the validity ranges)`, () => {
      expectAnalyticalParity("blasting", fn, (args) =>
        (blasting[fn] as (a: never) => unknown)(args as never),
      );
    });
  }
});
