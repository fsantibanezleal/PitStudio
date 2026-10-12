// T-020-013 [red] · FR-020-49 (the teaching functions exact McNemar test, Gaussian two-sample AUC and paired-t interval equal their analytical forms and SciPy reference values within rtol 1e-9), FR-020-50 (NaN, infinity or an
// argument outside the domain: a RangeError naming the argument) and P-020-22, P-020-23, P-020-24 (McNemar), P-020-25, P-020-26, P-020-27 (AUC), P-020-28, P-020-29, P-020-30 (paired-t interval).
//
// Expected API (web/src/theory/fn/):
//   mcnemar.ts      mcnemar({ b, c }: { b: number; c: number }): number    the exact two-sided p-value min(1, 2 P(X <= min(b, c))), X ~ Binomial(b + c, 1/2); b and c are the discordant counts, integers >= 0; (0, 0) gives 1;
//                   RangeError naming the argument for a negative, fractional, non-finite or non-number count
//   gaussianAuc.ts  gaussianAuc({ deltaMu, sigma }): number                AUC of two equal-variance normal score distributions, Phi(deltaMu / (sigma sqrt 2)); RangeError for NaN, infinity or sigma <= 0 (deltaMu may be any finite number)
//   pairedTCi.ts    pairedTCi({ n, mean, sd, level = 0.95 }): { lo: number; hi: number }   mean -/+ t_{(1 + level)/2, n - 1} sd / sqrt(n); RangeError naming the argument for NaN, infinity, a non-integer n or n < 2, sd < 0, level outside (0, 1)
// Oracles: exact rationals by hand (b = 10, c = 0: 2 * 2^-10 = 0.001953125; b = 5, c = 1: 14/64; b = 8, c = 2: 112/1024), the closed forms of the t quantile for one and two degrees of freedom (df = 1: tan(pi (p - 1/2)) = 12.706204736174694;
// df = 2: (2p - 1) / sqrt(2 p (1 - p)) = 4.302652729749462 at p = 0.975), Phi(1) = 0.8413447460685429, and SciPy 1.18.1 reference values (recipes in the comments: scipy.stats.binomtest(min(b, c), b + c, 0.5).pvalue,
// scipy.special.ndtr(deltaMu / (sigma sqrt 2)), scipy.stats.t.ppf((1 + level) / 2, n - 1)); the algebraic relations of the properties.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { gaussianAuc } from "~/theory/fn/gaussianAuc";
import { mcnemar } from "~/theory/fn/mcnemar";
import { pairedTCi } from "~/theory/fn/pairedTCi";

const close = (a: number, b: number, rtol = 1e-9) =>
  Math.abs(a - b) <= rtol * Math.max(Math.abs(b), Number.MIN_VALUE);

describe("exact McNemar test (FR-020-49)", () => {
  // scipy.stats.binomtest(min(b, c), b + c, 0.5, alternative="two-sided").pvalue
  const refs: Array<[number, number, number]> = [
    [10, 0, 0.001953125],
    [5, 1, 0.21875],
    [8, 2, 0.109375],
    [3, 3, 1],
    [0, 0, 1],
    [0, 1, 1],
    [40, 20, 0.01348929373119186],
    [500, 400, 0.0009564441369189492],
    [4900, 5100, 0.04658552770494645],
    [10000, 9000, 4.194037144140854e-13],
    [7, 14, 0.18924713134765625],
  ];
  for (const [b, c, p] of refs) {
    it(`FR-020-49 · b = ${b}, c = ${c} gives p = ${p}`, () => {
      expect(close(mcnemar({ b, c }), p, 1e-9)).toBe(true);
    });
  }

  it("FR-020-49 · hand calculation: b = 10, c = 0 is 2 * 2^-10 = 0.001953125 (exactly), and b = 5, c = 1 is 14/64", () => {
    expect(mcnemar({ b: 10, c: 0 })).toBeCloseTo(2 ** -9, 15);
    expect(mcnemar({ b: 5, c: 1 })).toBeCloseTo(14 / 64, 15);
    expect(mcnemar({ b: 8, c: 2 })).toBeCloseTo(112 / 1024, 15);
  });

  for (const [name, bad] of [
    ["b", -1],
    ["b", 1.5],
    ["b", Number.NaN],
    ["b", Number.POSITIVE_INFINITY],
    ["c", -1],
    ["c", 0.1],
    ["c", Number.NaN],
    ["c", Number.NEGATIVE_INFINITY],
    ["b", "5"],
    ["c", null],
    ["b", undefined],
  ] as Array<[string, unknown]>) {
    it(`FR-020-50 · ${name} = ${String(bad)} throws a RangeError naming ${name}`, () => {
      expect(() => mcnemar({ b: 5, c: 3, [name]: bad } as never)).toThrow(RangeError);
      expect(() => mcnemar({ b: 5, c: 3, [name]: bad } as never)).toThrow(new RegExp(`\\b${name}\\b`));
    });
  }

  it("FR-020-49 · counts far beyond 10^4 stay finite and in [0, 1]", () => {
    for (const [b, c] of [
      [100_000, 99_000],
      [1_000_000, 0],
      [0, 1_000_000],
      [123_456, 123_456],
    ]) {
      const p = mcnemar({ b, c });
      expect(Number.isFinite(p)).toBe(true);
      expect(p).toBeGreaterThanOrEqual(0);
      expect(p).toBeLessThanOrEqual(1);
    }
  });

  const counts = fc.integer({ min: 0, max: 10_000 });
  it("P-020-22 · symmetry: p(b, c) = p(c, b)", () => {
    fc.assert(
      fc.property(counts, counts, (b, c) => {
        expect(mcnemar({ b, c })).toBe(mcnemar({ b: c, c: b }));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-23 · null: p(b, b) = 1", () => {
    fc.assert(
      fc.property(counts, (b) => {
        expect(mcnemar({ b, c: b })).toBe(1);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-24 · at a fixed b + c the p-value is non-increasing in |b - c| (an ulp of rounding is tolerated: the order is exact in the mathematics)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 10_000 }),
        fc.integer({ min: 0, max: 10_000 }),
        fc.integer({ min: 0, max: 10_000 }),
        (n, u, v) => {
          const split = (x: number) => Math.min(Math.floor(n / 2), x % (Math.floor(n / 2) + 1)); // the smaller count, 0..n/2
          const s1 = split(u);
          const s2 = split(v);
          const [more, less] = s1 <= s2 ? [s1, s2] : [s2, s1]; // `more` has the larger gap |b - c|
          const pMore = mcnemar({ b: more, c: n - more });
          const pLess = mcnemar({ b: less, c: n - less });
          expect(pMore).toBeLessThanOrEqual(pLess * (1 + 1e-12));
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("Gaussian two-sample AUC (FR-020-49)", () => {
  // scipy.special.ndtr(dmu / (sigma * sqrt(2)))
  const refs: Array<[number, number, number]> = [
    [0, 1, 0.5],
    [Math.SQRT2, 1, 0.8413447460685429],
    [0.3, 1, 0.5839979857136817],
    [1, 1, 0.7602499389065233],
    [2.5, 0.5, 0.9997965239912775],
    [-1, 1, 0.23975006109347674],
    [10, 1, 0.9999999999992313],
    [0.01, 2, 0.5014104710203875],
    [-8, 1, 7.70862895014001e-9],
  ];
  for (const [dmu, sigma, auc] of refs) {
    it(`FR-020-49 · deltaMu = ${dmu}, sigma = ${sigma} gives AUC = ${auc}`, () => {
      expect(close(gaussianAuc({ deltaMu: dmu, sigma }), auc, 1e-9)).toBe(true);
    });
  }

  it("FR-020-49 · AUC(0, sigma) is exactly 0.5 and Phi(1) = 0.8413447460685429 at deltaMu = sigma sqrt 2", () => {
    for (const s of [1e-6, 0.5, 1, 7, 1e6]) expect(gaussianAuc({ deltaMu: 0, sigma: s })).toBe(0.5);
    expect(close(gaussianAuc({ deltaMu: 3 * Math.SQRT2, sigma: 3 }), 0.8413447460685429, 1e-12)).toBe(true);
  });

  it("FR-020-49 · the AUC of a very large separation is 1 and of a very negative one is 0, never outside [0, 1]", () => {
    expect(gaussianAuc({ deltaMu: 1e6, sigma: 1 })).toBe(1);
    expect(gaussianAuc({ deltaMu: -1e6, sigma: 1 })).toBe(0);
    expect(gaussianAuc({ deltaMu: Number.MAX_VALUE, sigma: 1 })).toBe(1);
  });

  for (const [name, bad] of [
    ["sigma", 0],
    ["sigma", -1],
    ["sigma", Number.NaN],
    ["sigma", Number.POSITIVE_INFINITY],
    ["deltaMu", Number.NaN],
    ["deltaMu", Number.POSITIVE_INFINITY],
    ["deltaMu", Number.NEGATIVE_INFINITY],
  ] as Array<[string, number]>) {
    it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
      expect(() => gaussianAuc({ deltaMu: 1, sigma: 1, [name]: bad })).toThrow(RangeError);
      expect(() => gaussianAuc({ deltaMu: 1, sigma: 1, [name]: bad })).toThrow(new RegExp(`\\b${name}\\b`));
    });
  }

  it("P-020-25 · scale invariance: AUC(k deltaMu, k sigma) = AUC(deltaMu, sigma)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: 10, noNaN: true }),
        fc.double({ min: 0.01, max: 10, noNaN: true }),
        fc.double({ min: 1e-3, max: 1e3, noNaN: true }),
        (d, s, k) => {
          const a = gaussianAuc({ deltaMu: d, sigma: s });
          const b = gaussianAuc({ deltaMu: k * d, sigma: k * s });
          expect(Math.abs(a - b) <= 1e-12 * Math.max(a, 1e-300) || Math.abs(a - b) < 1e-15).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-26 · antisymmetry: AUC(-deltaMu, sigma) = 1 - AUC(deltaMu, sigma) within 1e-12, and AUC(0, sigma) = 0.5", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: 10, noNaN: true }),
        fc.double({ min: 0.1, max: 10, noNaN: true }),
        (z, s) => {
          expect(
            Math.abs(
              gaussianAuc({ deltaMu: -z * s, sigma: s }) - (1 - gaussianAuc({ deltaMu: z * s, sigma: s })),
            ),
          ).toBeLessThanOrEqual(1e-12);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-27 · the AUC is strictly increasing in deltaMu / sigma on [-8, 8]", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -8, max: 8, noNaN: true }),
        fc.double({ min: 1e-3, max: 8, noNaN: true }),
        (z, step) => {
          fc.pre(z + step <= 8);
          expect(gaussianAuc({ deltaMu: z + step, sigma: 1 })).toBeGreaterThan(
            gaussianAuc({ deltaMu: z, sigma: 1 }),
          );
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("paired-t confidence interval (FR-020-49)", () => {
  // scipy.stats.t.ppf(0.5 + level / 2, n - 1); interval = mean -/+ t sd / sqrt(n)
  const refs = [
    { n: 10, mean: 2.5, sd: 4, level: 0.95, lo: -0.3614276238826588, hi: 5.361427623882658 },
    { n: 2, mean: 0, sd: 1, level: 0.95, lo: -8.984643532093752, hi: 8.984643532093752 },
    { n: 30, mean: -1.2, sd: 0.8, level: 0.95, lo: -1.49872490940648, hi: -0.9012750905935198 },
    { n: 1000, mean: 0.05, sd: 2, level: 0.95, lo: -0.07410937128328966, hi: 0.17410937128328968 },
    { n: 5, mean: 10, sd: 3, level: 0.99, lo: 3.8229585356819618, hi: 16.177041464318037 },
    { n: 12, mean: 0.3, sd: 0.4, level: 0.9, lo: 0.09262908329753164, hi: 0.5073709167024684 },
    { n: 3, mean: 1, sd: 0, level: 0.95, lo: 1, hi: 1 },
  ];
  for (const { lo, hi, ...args } of refs) {
    it(`FR-020-49 · n = ${args.n}, mean = ${args.mean}, sd = ${args.sd}, level = ${args.level} gives [${lo}, ${hi}]`, () => {
      const got = pairedTCi(args);
      const scale = Math.max(Math.abs(args.mean), args.sd, 1e-300);
      expect(Math.abs(got.lo - lo)).toBeLessThanOrEqual(1e-9 * Math.max(Math.abs(lo), scale));
      expect(Math.abs(got.hi - hi)).toBeLessThanOrEqual(1e-9 * Math.max(Math.abs(hi), scale));
    });
  }

  it("FR-020-49 · closed forms of the t quantile: with two pairs (1 degree of freedom) the half-width is tan(0.475 pi) sd / sqrt 2, with three pairs 4.302652729749462 sd / sqrt 3", () => {
    const two = pairedTCi({ n: 2, mean: 0, sd: 1 });
    expect(close(two.hi, Math.tan(0.475 * Math.PI) / Math.SQRT2, 1e-9)).toBe(true);
    const three = pairedTCi({ n: 3, mean: 0, sd: 1 });
    expect(close(three.hi, 0.95 / Math.sqrt(2 * 0.975 * 0.025) / Math.sqrt(3), 1e-9)).toBe(true);
  });

  it("FR-020-49 · the default level is 0.95", () => {
    expect(pairedTCi({ n: 10, mean: 2.5, sd: 4 })).toEqual(
      pairedTCi({ n: 10, mean: 2.5, sd: 4, level: 0.95 }),
    );
  });

  it("FR-020-49 · the interval is centred on the mean", () => {
    const { lo, hi } = pairedTCi({ n: 17, mean: 1.25, sd: 0.7 });
    expect(Math.abs((lo + hi) / 2 - 1.25)).toBeLessThan(1e-13);
  });

  for (const [name, bad] of [
    ["n", 1],
    ["n", 0],
    ["n", -3],
    ["n", 2.5],
    ["n", Number.NaN],
    ["n", Number.POSITIVE_INFINITY],
    ["sd", -0.1],
    ["sd", Number.NaN],
    ["sd", Number.POSITIVE_INFINITY],
    ["mean", Number.NaN],
    ["mean", Number.POSITIVE_INFINITY],
    ["level", 0],
    ["level", 1],
    ["level", 1.5],
    ["level", -0.2],
    ["level", Number.NaN],
  ] as Array<[string, number]>) {
    it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
      expect(() => pairedTCi({ n: 10, mean: 1, sd: 1, level: 0.95, [name]: bad })).toThrow(RangeError);
      expect(() => pairedTCi({ n: 10, mean: 1, sd: 1, level: 0.95, [name]: bad })).toThrow(
        new RegExp(`\\b${name}\\b`),
      );
    });
  }

  const dom = fc.record({
    n: fc.integer({ min: 2, max: 1000 }),
    mean: fc.double({ min: -100, max: 100, noNaN: true }),
    sd: fc.double({ min: 0.01, max: 50, noNaN: true }),
  });
  const near = (a: number, b: number, scale: number) => Math.abs(a - b) <= 1e-12 * Math.max(scale, 1e-300);

  it("P-020-28 · translation: adding c to every difference shifts both bounds by c", () => {
    fc.assert(
      fc.property(dom, fc.double({ min: -100, max: 100, noNaN: true }), (a, c) => {
        const base = pairedTCi(a);
        const moved = pairedTCi({ ...a, mean: a.mean + c });
        const scale = Math.abs(a.mean) + Math.abs(c) + (base.hi - base.lo);
        expect(near(moved.lo, base.lo + c, scale)).toBe(true);
        expect(near(moved.hi, base.hi + c, scale)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-29 · scaling: multiplying every difference by k > 0 multiplies both bounds by k", () => {
    fc.assert(
      fc.property(dom, fc.double({ min: 1e-3, max: 1e3, noNaN: true }), (a, k) => {
        const base = pairedTCi(a);
        const scaled = pairedTCi({ ...a, mean: a.mean * k, sd: a.sd * k });
        const scale = k * (Math.abs(a.mean) + (base.hi - base.lo));
        expect(near(scaled.lo, base.lo * k, scale)).toBe(true);
        expect(near(scaled.hi, base.hi * k, scale)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-30 · at a fixed sample standard deviation the width is strictly decreasing in n", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 2, max: 999 }),
        fc.double({ min: 0.01, max: 50, noNaN: true }),
        fc.double({ min: -100, max: 100, noNaN: true }),
        (n, sd, mean) => {
          const w = (m: number) => {
            const { lo, hi } = pairedTCi({ n: m, mean, sd });
            return hi - lo;
          };
          expect(w(n + 1)).toBeLessThan(w(n));
        },
      ),
      { numRuns: 200 },
    );
  });
});
