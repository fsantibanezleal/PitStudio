// T-018-070 [red] · FR-018-51 (comminution port, parity within 1e-12 s_y + rtol |y|, and the typed rejection of P80 >= F80),
// P-018-43 (Bond energy tends to 0 as P80 approaches F80), P-018-44 (monotone in P80, linear in the work index), P-018-45 (mine-to-mill chain
// mass balance) for the `comminution` engine of spec 018.
//
// Expected API (module `~/engines/analytical/comminution`, file web/src/engines/analytical/comminution/index.ts). Every function takes the `args`
// of its DC-018-02 request and returns the `result` object (specs/018-web-cases/contracts/engines/comminution.schema.json), SI, snake_case:
//     bond_energy(args)         -> { specific_energy_j_per_kg }      W = 10 Wi (1 / sqrt(P80) - 1 / sqrt(F80)), sizes in micrometres inside
//     passing_size(args)        -> { size_m }                        linear interpolation in (log x, log P) between the bracketing points; a grid
//                                                                    size exactly where `fraction` equals its passing value; `sizes_m` strictly monotone
//     mine_to_mill_chain(args)  -> { f80_m, fines_fraction, specific_energy_j_per_kg, crusher_feed_kg_per_s, mill_product_kg_per_s }
//                                  class masses -> crusher matrix model -> cumulative passing -> F80 at 0.8 -> Bond energy; the throughput
//                                  crusher_feed = mill_product = installed power / specific energy (Bond only; `energy_model` is the constant "bond")
//   P80 >= F80 throws an error with `code === "E_RANGE"` (the same class as the reference's InputError, FR-018-51); any other validity-range violation
//   `E_RANGE`, a malformed argument or an unknown enum value `E_SCHEMA` (FR-018-38 typed errors).
//
// Oracles (independent of the code under test):
//   - Bond's law (Bond 1961) by hand: Wi = 15 kWh/t, F80 = 2,000 um, P80 = 150 um gives 8.893347 kWh/t = 32,016.05 J/kg (minephys plan 005);
//     the published rod-ball stage energies 2.32 and 4.77 kWh/t (total 7.09) of the Bond efficiency guideline (McIvor 2016, p. 2);
//     1 kWh/t = 3,600 J/kg.
//   - The chain composed by hand in this file (steady-state crusher balance by forward substitution, cumulative passing, log-log interpolation,
//     Bond), cross-checked with numpy on 2026-10-11: f80 0.09253609008493312 m, energy 39,494.60906992494 J/kg, throughput 126.59955669259908 kg/s;
//     the three-class case of plan 005 (crusher product 0.12, 0.3816, 0.4984; cumulative 1.0, 0.88, 0.4984).
//   - the parity fixtures of the reference (`minephys.comminution`), DC-018-04, through web/src/test-support/parity-fixtures.ts.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as comminution from "~/engines/analytical/comminution";
import { expectAnalyticalParity } from "~/test-support/parity-fixtures";

const KWH = 3600;
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
const bond = (wi: number, f80: number, p80: number) =>
  num(
    comminution.bond_energy({ work_index_j_per_kg: wi, f80_m: f80, p80_m: p80 }),
    "specific_energy_j_per_kg",
  );
/** The bracket 10 / sqrt(P80) - 10 / sqrt(F80) of Bond's law with sizes in micrometres. */
const bracket = (fUm: number, pUm: number) => 10 / Math.sqrt(pUm) - 10 / Math.sqrt(fUm);

describe("Bond's law (FR-018-51)", () => {
  it("FR-018-51 · Wi = 15 kWh/t, F80 = 2,000 um, P80 = 150 um gives 8.893347 kWh/t = 32,016.05 J/kg", () => {
    const w = bond(15 * KWH, 2e-3, 1.5e-4);
    expect(close(w, 15 * KWH * bracket(2000, 150), 1e-12)).toBe(true);
    expect(close(w, 32016.048291598345, 1e-12)).toBe(true);
    expect(Math.abs(w - 32016.05)).toBeLessThan(5e-3);
    expect(Math.abs(w / KWH - 8.893347)).toBeLessThan(5e-7);
  });

  it("FR-018-51 · the published rod-ball stage energies: 9.5 kWh/t from 19,300 to 1,000 um is 2.32 kWh/t, 9.8 kWh/t from 1,000 to 155 um is 4.77 kWh/t, total 7.09", () => {
    const a = bond(9.5 * KWH, 19300e-6, 1000e-6) / KWH;
    const b = bond(9.8 * KWH, 1000e-6, 155e-6) / KWH;
    expect(Math.abs(a - 2.32)).toBeLessThanOrEqual(0.005);
    expect(Math.abs(b - 4.77)).toBeLessThanOrEqual(0.005);
    expect(Math.abs(a + b - 7.09)).toBeLessThanOrEqual(0.005 + 1e-9);
  });

  it("FR-018-51 · W tends to Wi as F80 grows at P80 = 100 um, with |W - Wi| <= 10 Wi / sqrt(F80 in um)", () => {
    const wi = 7.5 * KWH;
    for (const f of [0.1, 0.5, 1.0]) {
      const w = bond(wi, f, 1e-4);
      expect(w).toBeLessThan(wi);
      expect(Math.abs(w - wi)).toBeLessThanOrEqual(((10 * wi) / Math.sqrt(f * 1e6)) * (1 + 1e-9));
    }
  });

  it("FR-018-51 · P80 >= F80 is E_RANGE (the reference's InputError), for P80 = F80 and for P80 > F80", () => {
    expect(codeOf(() => bond(54000, 2e-3, 2e-3))).toBe("E_RANGE");
    expect(codeOf(() => bond(54000, 2e-3, 3e-3))).toBe("E_RANGE");
    expect(codeOf(() => bond(54000, 1e-3, 1))).toBe("E_RANGE");
  });

  it("FR-018-51 · a product finer than 70 um, a non-positive work index and a feed above 1 m are E_RANGE", () => {
    expect(codeOf(() => bond(54000, 2e-3, 6.9e-5))).toBe("E_RANGE");
    expect(codeOf(() => bond(0, 2e-3, 1.5e-4))).toBe("E_RANGE");
    expect(codeOf(() => bond(-5, 2e-3, 1.5e-4))).toBe("E_RANGE");
    expect(codeOf(() => bond(54000, 1.01, 1.5e-4))).toBe("E_RANGE");
    expect(codeOf(() => bond(360001, 2e-3, 1.5e-4))).toBe("E_RANGE");
  });
});

describe("Bond metamorphic relations (P-018-43, P-018-44)", () => {
  it("P-018-43 · the specific energy tends to 0 as P80 approaches F80 from below: at P80 = F80 (1 - 1e-9) it is below 1e-8 kWh/t", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 25, noNaN: true }),
        fc.double({ min: 500e-6, max: 1, noNaN: true }),
        (wiKwh, f80) => {
          const w = bond(wiKwh * KWH, f80, f80 * (1 - 1e-9));
          return w >= 0 && w / KWH <= 1e-8;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-44 · the specific energy is strictly decreasing in P80 at fixed F80 and Wi", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 40, noNaN: true }),
        fc.double({ min: 2e-4, max: 1, noNaN: true }),
        fc.double({ min: 0.05, max: 0.9, noNaN: true }),
        fc.double({ min: 0.05, max: 0.9, noNaN: true }),
        (wiKwh, f80, u, v) => {
          const lo = 7e-5 + Math.min(u, v) * (f80 * 0.95 - 7e-5);
          const hi = 7e-5 + Math.max(u, v) * (f80 * 0.95 - 7e-5);
          if (!(hi > lo * (1 + 1e-6))) return true;
          return bond(wiKwh * KWH, f80, lo) > bond(wiKwh * KWH, f80, hi);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-44 · the specific energy is linear in the work index (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 40, noNaN: true }),
        fc.double({ min: 0.1, max: 8, noNaN: true }),
        fc.double({ min: 5e-4, max: 1, noNaN: true }),
        (wiKwh, k, f80) => {
          const p80 = Math.max(7e-5, f80 / 10);
          return close(bond(k * wiKwh * KWH, f80, p80), k * bond(wiKwh * KWH, f80, p80), 1e-12);
        },
      ),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// passing_size
// ---------------------------------------------------------------------------------------------------------------------
const SIZES = [0.4, 0.2, 0.1, 0.05, 0.025];
const BLAST = [1.0, 0.85, 0.55, 0.3, 0.12];
const CLASSIFICATION = [0.9, 0.6, 0.2, 0.0, 0.0];
const BREAKAGE = [
  [0.0, 0.0, 0.0, 0.0, 0.0],
  [0.4, 0.0, 0.0, 0.0, 0.0],
  [0.3, 0.5, 0.0, 0.0, 0.0],
  [0.2, 0.3, 0.6, 0.0, 0.0],
  [0.1, 0.2, 0.4, 0.0, 0.0],
];
/** Size at which the curve reaches `fraction`: linear interpolation in (log size, log passing) between the bracketing points. */
function handSize(sizes: number[], passing: number[], fraction: number): number {
  for (let i = 0; i < sizes.length - 1; i++) {
    const p0 = passing[i] as number;
    const p1 = passing[i + 1] as number;
    if (p0 >= fraction && fraction >= p1) {
      const lx0 = Math.log(sizes[i] as number);
      const lx1 = Math.log(sizes[i + 1] as number);
      return Math.exp(
        lx0 + ((Math.log(fraction) - Math.log(p0)) * (lx1 - lx0)) / (Math.log(p1) - Math.log(p0)),
      );
    }
  }
  throw new Error("fraction outside the curve");
}
const psize = (sizes: number[], passing: number[], fraction: number) =>
  num(comminution.passing_size({ sizes_m: sizes, passing, fraction }), "size_m");

describe("passing size (FR-018-51)", () => {
  const crusherPassing = [1.0, 0.985, 0.8434, 0.52604, 0.207716];

  it("FR-018-51 · the 80 % size of the crusher product of the hand chain is 0.09253609008493312 m (log-log interpolation, rtol 1e-12)", () => {
    expect(close(psize(SIZES, crusherPassing, 0.8), 0.09253609008493312, 1e-12)).toBe(true);
    expect(close(psize(SIZES, crusherPassing, 0.8), handSize(SIZES, crusherPassing, 0.8), 1e-12)).toBe(true);
  });

  it("FR-018-51 · a fraction equal to a grid passing value returns exactly that grid size", () => {
    expect(psize(SIZES, [1.0, 0.9, 0.7, 0.5, 0.25], 0.7)).toBeCloseTo(0.1, 15);
    expect(psize(SIZES, [1.0, 0.9, 0.7, 0.5, 0.25], 0.5)).toBeCloseTo(0.05, 15);
  });

  it("FR-018-51 · the same curve given from fine to coarse (ascending sizes) gives the same size", () => {
    const asc = [...SIZES].reverse();
    const pAsc = [...crusherPassing].reverse();
    expect(close(psize(asc, pAsc, 0.8), 0.09253609008493312, 1e-12)).toBe(true);
  });

  it("FR-018-51 · scaling all sizes by lambda scales the result by lambda and the result is non-decreasing in the fraction", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1e-3, max: 100, noNaN: true }),
        fc.double({ min: 0.25, max: 0.95, noNaN: true }),
        fc.double({ min: 0.001, max: 0.04, noNaN: true }),
        (lam, f, df) => {
          const scaled = SIZES.map((s) => s * lam);
          const base = psize(SIZES, crusherPassing, f);
          const lowerFraction = psize(SIZES, crusherPassing, f - df);
          return (
            close(psize(scaled, crusherPassing, f), base * lam, 1e-12) && lowerFraction <= base * (1 + 1e-12)
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · hostile curves: a fraction outside the curve, sizes not strictly monotone, a passing value above 1 or not monotone, mismatched lengths and fewer than 2 points are rejected", () => {
    expect(codeOf(() => psize(SIZES, crusherPassing, 0.1))).toBe("E_RANGE");
    expect(codeOf(() => psize(SIZES, crusherPassing, 1.0000001))).toMatch(/E_RANGE|E_SCHEMA/);
    expect(codeOf(() => psize([0.4, 0.2, 0.2, 0.05, 0.025], crusherPassing, 0.8))).toBe("E_RANGE");
    expect(codeOf(() => psize([0.4, 0.2, 0.3, 0.05, 0.025], crusherPassing, 0.8))).toBe("E_RANGE");
    expect(codeOf(() => psize(SIZES, [1.0, 1.2, 0.8, 0.5, 0.2], 0.8))).toMatch(/E_RANGE|E_SCHEMA/);
    expect(codeOf(() => psize(SIZES, [1.0, 0.7, 0.8, 0.5, 0.2], 0.8))).toBe("E_RANGE");
    expect(codeOf(() => psize(SIZES, crusherPassing.slice(0, 4), 0.8))).toBe("E_SCHEMA");
    expect(codeOf(() => psize([0.4], [1.0], 0.8))).toMatch(/E_RANGE|E_SCHEMA/);
    expect(codeOf(() => psize([0.4, 0.2, 0, 0.05, 0.025], crusherPassing, 0.8))).toMatch(/E_RANGE|E_SCHEMA/);
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// mine-to-mill chain
// ---------------------------------------------------------------------------------------------------------------------
/** The composition class masses -> crusher -> cumulative passing, by forward substitution of x = f + B C x (strictly lower triangular B). */
function handCrusher(blast: number[], cl: number[], b: number[][]): number[] {
  const n = blast.length;
  const feed = blast.map((p, i) => (i < n - 1 ? p - (blast[i + 1] as number) : p));
  const x: number[] = [];
  for (let i = 0; i < n; i++) {
    let acc = feed[i] as number;
    for (let j = 0; j < i; j++)
      acc += ((b[i] as number[])[j] as number) * (cl[j] as number) * (x[j] as number);
    x.push(acc);
  }
  const product = x.map((xi, i) => (1 - (cl[i] as number)) * xi);
  const passing: number[] = [];
  let run = 0;
  for (let i = n - 1; i >= 0; i--) {
    run += product[i] as number;
    passing[i] = run;
  }
  return passing;
}
const chain = (over: Record<string, unknown> = {}) =>
  comminution.mine_to_mill_chain({
    sizes_m: SIZES,
    blast_passing: BLAST,
    classification: CLASSIFICATION,
    breakage: BREAKAGE,
    target_p80_m: 1.5e-4,
    installed_power_w: 5.0e6,
    energy_model: "bond",
    work_index_j_per_kg: 14 * KWH,
    fines_size_m: 0.05,
    ...over,
  }) as Record<string, number>;

describe("mine-to-mill chain (FR-018-51, P-018-45)", () => {
  it("FR-018-51 · the hand composition: F80 0.09253609008493312 m, energy 39,494.60906992494 J/kg, throughput 126.59955669259908 kg/s, fines (0.05 m) 0.52604", () => {
    const r = chain();
    const passing = handCrusher(BLAST, CLASSIFICATION, BREAKAGE);
    const f80 = handSize(SIZES, passing, 0.8);
    const energy = 14 * KWH * bracket(f80 * 1e6, 150);
    expect(close(r.f80_m as number, f80, 1e-12)).toBe(true);
    expect(close(r.specific_energy_j_per_kg as number, energy, 1e-12)).toBe(true);
    expect(close(r.crusher_feed_kg_per_s as number, 5.0e6 / energy, 1e-12)).toBe(true);
    expect(close(r.fines_fraction as number, passing[3] as number, 1e-12)).toBe(true);
    expect(close(r.f80_m as number, 0.09253609008493312, 1e-12)).toBe(true);
    expect(close(r.specific_energy_j_per_kg as number, 39494.60906992494, 1e-12)).toBe(true);
    expect(close(r.crusher_feed_kg_per_s as number, 126.59955669259908, 1e-12)).toBe(true);
    expect(close(r.fines_fraction as number, 0.52604, 1e-12)).toBe(true);
  });

  it("FR-018-51 · the three-class case of plan 005: crusher product (0.12, 0.3816, 0.4984), cumulative 1.0, 0.88, 0.4984, fines fraction 0.4984", () => {
    const sizes = [0.3, 0.1, 0.03];
    const blast = [1.0, 0.4, 0.1];
    const cl = [0.8, 0.4, 0.0];
    const b = [
      [0, 0, 0],
      [0.7, 0, 0],
      [0.3, 1.0, 0],
    ];
    const passing = handCrusher(blast, cl, b);
    expect(passing[0]).toBeCloseTo(1.0, 12);
    expect(passing[1]).toBeCloseTo(0.88, 12);
    expect(passing[2]).toBeCloseTo(0.4984, 12);
    const r = chain({
      sizes_m: sizes,
      blast_passing: blast,
      classification: cl,
      breakage: b,
      target_p80_m: 2e-4,
      installed_power_w: 2.0e6,
      work_index_j_per_kg: 12 * KWH,
      fines_size_m: 0.03,
    });
    expect(close(r.fines_fraction as number, 0.4984, 1e-12)).toBe(true);
    expect(close(r.f80_m as number, handSize(sizes, passing, 0.8), 1e-12)).toBe(true);
    expect(close(r.f80_m as number, 0.08172242338121362, 1e-9)).toBe(true);
  });

  it("FR-018-51 · an identity crusher (no classification, no breakage) with Bond equals Bond's law at the closed-form Swebrec x80 on a 200-point grid (rtol 5e-3)", () => {
    // Swebrec x50 = 0.25, xmax = 2, b = 2: x80 = xmax (x50 / xmax)^(0.25^(1/b)) = 0.70711 m
    const x50 = 0.25;
    const xmax = 2;
    const b = 2;
    const n = 200;
    const sizes = Array.from({ length: n }, (_, i) => xmax * (10e-6 / xmax) ** (i / (n - 1)));
    const passing = sizes.map((x, i) =>
      i === 0 ? 1 : 1 / (1 + (Math.log(xmax / x) / Math.log(xmax / x50)) ** b),
    );
    const r = chain({
      sizes_m: sizes,
      blast_passing: passing,
      classification: new Array(n).fill(0),
      breakage: Array.from({ length: n }, () => new Array(n).fill(0)),
      target_p80_m: 1e-4,
      installed_power_w: 1.0e7,
      work_index_j_per_kg: 15 * KWH,
      fines_size_m: sizes[100],
    });
    const x80 = xmax * (x50 / xmax) ** (0.25 ** (1 / b));
    expect(close(r.f80_m as number, handSize(sizes, passing, 0.8), 1e-12)).toBe(true);
    expect(close(r.f80_m as number, x80, 5e-3)).toBe(true);
    expect(close(r.specific_energy_j_per_kg as number, 15 * KWH * bracket(x80 * 1e6, 100), 5e-3)).toBe(true);
  });

  it("P-018-45 · mass balance: t/h leaving the mill equals t/h entering the crusher (rtol 1e-12), and both equal installed power / specific energy, for random designs", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 8, max: 20, noNaN: true }),
        fc.double({ min: 1e6, max: 5e7, noNaN: true }),
        fc.double({ min: 7e-5, max: 3e-4, noNaN: true }),
        (wiKwh, power, p80) => {
          const r = chain({ work_index_j_per_kg: wiKwh * KWH, installed_power_w: power, target_p80_m: p80 });
          const feed = r.crusher_feed_kg_per_s as number;
          const product = r.mill_product_kg_per_s as number;
          return (
            close(product, feed, 1e-12) && close(feed, power / (r.specific_energy_j_per_kg as number), 1e-12)
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-51 · the result is deterministic and the input arrays are not modified", () => {
    const sizes = [...SIZES];
    const blast = [...BLAST];
    const breakage = BREAKAGE.map((row) => [...row]);
    const a = chain({ sizes_m: sizes, blast_passing: blast, breakage });
    const b = chain({ sizes_m: sizes, blast_passing: blast, breakage });
    expect(a).toEqual(b);
    expect(sizes).toEqual(SIZES);
    expect(blast).toEqual(BLAST);
    expect(breakage).toEqual(BREAKAGE);
  });

  it("FR-018-51 · hostile chains: the Morrell model, a product finer than 70 um, a negative power, mismatched lengths and a curve that never reaches 80 % are rejected", () => {
    expect(codeOf(() => chain({ energy_model: "morrell" }))).toBe("E_SCHEMA");
    expect(codeOf(() => chain({ target_p80_m: 5e-5 }))).toBe("E_RANGE");
    expect(codeOf(() => chain({ installed_power_w: -1 }))).toBe("E_RANGE");
    expect(codeOf(() => chain({ classification: [0.9, 0.6, 0.2] }))).toBe("E_SCHEMA");
    expect(codeOf(() => chain({ breakage: BREAKAGE.slice(0, 4) }))).toBe("E_SCHEMA");
    expect(codeOf(() => chain({ classification: [0.9, 0.6, 1.2, 0, 0] }))).toMatch(/E_RANGE|E_SCHEMA/);
    expect(codeOf(() => chain({ blast_passing: [1.0, 0.95, 0.9, 0.85, 0.82] }))).toBe("E_RANGE");
  });
});

describe("parity with minephys.comminution (FR-018-51)", () => {
  it("FR-018-51 · bond_energy equals the reference on its fixture (>= 200 vectors, both ends of the validity ranges)", () => {
    expectAnalyticalParity("comminution", "bond_energy", (args) => comminution.bond_energy(args as never));
  });
  it("FR-018-51 · passing_size equals the reference on its fixture", () => {
    expectAnalyticalParity("comminution", "passing_size", (args) => comminution.passing_size(args as never));
  });
  it("FR-018-51 · mine_to_mill_chain equals the reference on its fixture", () => {
    expectAnalyticalParity("comminution", "mine_to_mill_chain", (args) =>
      comminution.mine_to_mill_chain(args as never),
    );
  });
});
