// T-020-012 [red] · FR-020-49 (the teaching functions lidar range with Beer-Lambert extinction and the PPO clipped objective equal their analytical forms within rtol 1e-9), FR-020-50 (NaN, infinity or an argument outside the
// domain: a RangeError naming the argument) and P-020-16, P-020-17, P-020-18 (lidar), P-020-19, P-020-20, P-020-21 (PPO).
//
// Expected API:
//   `~/theory/fn/lidarRange` (web/src/theory/fn/lidarRange.ts):
//       lidarRange({ R, rho, sigma, p0 = 1, area = 1, eta = 1 }): number   received power P = p0 rho area eta exp(-2 sigma R) / (pi R^2): a Lambertian target that fills the beam at range R (m), reflectivity rho in [0, 1], extinction
//           coefficient sigma (1/m, >= 0), transmitted power p0 (W), receiver area (m^2) and system efficiency eta (all > 0); exp(-2 sigma R) is the two-way Beer-Lambert transmittance (the lidar range equation of an extended Lambertian
//           target, for example Weitkamp (ed.), Lidar: Range-Resolved Optical Remote Sensing of the Atmosphere, Springer 2005, chapter 1);
//       lidarMaxRange({ rho, sigma, threshold, p0 = 1, area = 1, eta = 1 }): number   the range at which the received power falls to `threshold` (W): the unique root of lidarRange(R) = threshold (the power decreases strictly with R);
//       RangeError naming the argument for NaN, infinity, R <= 0, threshold <= 0, p0, area or eta <= 0, sigma < 0, rho < 0 or rho > 1.
//   `~/theory/fn/ppoClip` (web/src/theory/fn/ppoClip.ts): ppoClip({ r, A, eps }): number = min(r A, clip(r, 1 - eps, 1 + eps) A), the PPO clipped surrogate objective (Schulman et al., arXiv:1707.06347, eq. 7), r >= 0 the probability ratio,
//       A the advantage; RangeError naming the argument for NaN or infinity, r < 0, and eps outside the open interval (0, 1).
// Oracles: the closed forms with decimal reference values computed outside the code under test (Python decimal at 50 digits; recipe: P = p0 * rho * area * eta * exp(-2 sigma R) / (pi R^2)); hand tables of the PPO objective.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { lidarMaxRange, lidarRange } from "~/theory/fn/lidarRange";
import { ppoClip } from "~/theory/fn/ppoClip";

const close = (a: number, b: number, rtol = 1e-9) =>
  Math.abs(a - b) <= rtol * Math.max(Math.abs(b), Number.MIN_VALUE);

describe("lidar range equation (FR-020-49)", () => {
  const cases = [
    { R: 10, rho: 0.5, sigma: 0.01, p0: 1000, area: 0.002, eta: 0.8, p: 0.002084880742619373 },
    { R: 50, rho: 0.9, sigma: 0, p0: 1, area: 1, eta: 1, p: 0.00011459155902616465 },
    { R: 120, rho: 0.1, sigma: 0.05, p0: 2.5, area: 0.01, eta: 0.5, p: 1.697711401802902e-13 },
    { R: 1, rho: 1, sigma: 0.1, p0: 1, area: 1, eta: 1, p: 0.26061009282742165 },
  ];
  for (const { p, ...args } of cases) {
    it(`FR-020-49 · R = ${args.R} m, rho = ${args.rho}, sigma = ${args.sigma}/m gives ${p} W`, () => {
      expect(close(lidarRange(args), p, 1e-12)).toBe(true);
    });
  }

  it("FR-020-49 · hand arithmetic: R = 50 m, rho = 0.9, no extinction, unit constants: 0.9 / (pi 2500) = 1.1459e-4", () => {
    expect(lidarRange({ R: 50, rho: 0.9, sigma: 0 })).toBeCloseTo(0.9 / (Math.PI * 2500), 14);
  });

  it("FR-020-49 · the defaults are p0 = area = eta = 1", () => {
    expect(lidarRange({ R: 7, rho: 0.3, sigma: 0.02 })).toBe(
      lidarRange({ R: 7, rho: 0.3, sigma: 0.02, p0: 1, area: 1, eta: 1 }),
    );
  });

  it("FR-020-49 · the maximum range without extinction is sqrt(p0 rho area eta / (pi threshold)) = 15.957691216057308 m (decimal reference)", () => {
    const r = lidarMaxRange({ rho: 0.5, sigma: 0, threshold: 1e-3, p0: 1000, area: 0.002, eta: 0.8 });
    expect(close(r, 15.957691216057308, 1e-9)).toBe(true);
  });

  it("FR-020-49 · with extinction the range is the root: the received power at the maximum range equals the threshold, and extinction shortens it", () => {
    const base = { rho: 0.5, threshold: 1e-3, p0: 1000, area: 0.002, eta: 0.8 };
    let previous = Number.POSITIVE_INFINITY;
    for (const sigma of [0, 0.001, 0.01, 0.05, 0.1]) {
      const r = lidarMaxRange({ ...base, sigma });
      expect(
        close(
          lidarRange({ R: r, rho: base.rho, sigma, p0: base.p0, area: base.area, eta: base.eta }),
          base.threshold,
          1e-9,
        ),
        `sigma ${sigma}`,
      ).toBe(true);
      expect(r).toBeLessThan(previous);
      previous = r;
    }
  });

  const ok = { R: 10, rho: 0.5, sigma: 0.01 };
  for (const [name, bad] of [
    ["R", 0],
    ["R", -1],
    ["R", Number.NaN],
    ["R", Number.POSITIVE_INFINITY],
    ["sigma", -0.001],
    ["sigma", Number.NaN],
    ["sigma", Number.POSITIVE_INFINITY],
    ["rho", -0.1],
    ["rho", 1.0001],
    ["rho", Number.NaN],
    ["p0", 0],
    ["p0", -1],
    ["area", 0],
    ["eta", -0.5],
    ["eta", Number.NaN],
  ] as Array<[string, number]>) {
    it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
      expect(() => lidarRange({ ...ok, [name]: bad })).toThrow(RangeError);
      expect(() => lidarRange({ ...ok, [name]: bad })).toThrow(new RegExp(`\\b${name}\\b`));
    });
  }

  it("FR-020-50 · the maximum range rejects a non-positive threshold and the same domain for the rest", () => {
    for (const bad of [0, -1, Number.NaN, Number.POSITIVE_INFINITY])
      expect(() => lidarMaxRange({ rho: 0.5, sigma: 0, threshold: bad })).toThrow(/\bthreshold\b/);
    expect(() => lidarMaxRange({ rho: 2, sigma: 0, threshold: 1 })).toThrow(/\brho\b/);
    expect(() => lidarMaxRange({ rho: 0.5, sigma: -1, threshold: 1 })).toThrow(/\bsigma\b/);
  });

  it("FR-020-50 · missing or mistyped arguments are rejected", () => {
    expect(() => lidarRange({ R: undefined as never, rho: 0.5, sigma: 0 })).toThrow(RangeError);
    expect(() => lidarRange({ R: "10" as never, rho: 0.5, sigma: 0 })).toThrow(RangeError);
  });

  it("P-020-16 · the received power is linear in the reflectivity: P(s rho) = s P(rho)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1000, noNaN: true }),
        fc.double({ min: 0.001, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 0.1, noNaN: true }),
        fc.double({ min: 0.001, max: 1, noNaN: true }),
        (R, rho, sigma, s) => {
          expect(
            close(lidarRange({ R, rho: rho * s, sigma }), s * lidarRange({ R, rho, sigma }), 1e-12),
          ).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-17 · without extinction, doubling the range quarters the received power", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 500, noNaN: true }),
        fc.double({ min: 0.001, max: 1, noNaN: true }),
        (R, rho) => {
          expect(
            close(lidarRange({ R: 2 * R, rho, sigma: 0 }), lidarRange({ R, rho, sigma: 0 }) / 4, 1e-12),
          ).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-18 · the extinction sigma multiplies the received power by the two-way transmittance exp(-2 sigma R)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1000, noNaN: true }),
        fc.double({ min: 0.001, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 0.1, noNaN: true }),
        (R, rho, sigma) => {
          const t = lidarRange({ R, rho, sigma }) / lidarRange({ R, rho, sigma: 0 });
          expect(close(t, Math.exp(-2 * sigma * R), 1e-12)).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("PPO clipped objective (FR-020-49)", () => {
  const eps = 0.2;
  const table: Array<[string, number, number, number]> = [
    ["A > 0, ratio above the clip: capped at (1 + eps) A", 1.5, 2, 2.4],
    ["A < 0, ratio above the clip: the unclipped r A is the pessimistic one", 1.5, -2, -3],
    ["A < 0, ratio below the clip: clipped at (1 - eps) A", 0.5, -2, -1.6],
    ["A > 0, ratio below the clip: the unclipped r A is the smaller", 0.5, 2, 1],
    ["r = 1 equals the advantage", 1, 3, 3],
    ["r exactly 1 + eps", 1.2, 5, 6],
    ["r exactly 1 - eps", 0.8, -5, -4],
    ["r = 0, A > 0", 0, 3, 0],
    ["r = 0, A < 0: clipped at (1 - eps) A", 0, -3, -2.4],
    ["A = 0 gives 0", 3, 0, 0],
  ];
  for (const [what, r, A, expected] of table) {
    it(`FR-020-49 · ${what}: L(${r}, ${A}) = ${expected}`, () => {
      expect(
        close(ppoClip({ r, A, eps }), expected, 1e-12) || Math.abs(ppoClip({ r, A, eps }) - expected) < 1e-12,
      ).toBe(true);
    });
  }

  it("FR-020-49 · eps = 0.5 moves the bounds to 0.5 and 1.5", () => {
    expect(ppoClip({ r: 2, A: 4, eps: 0.5 })).toBeCloseTo(6, 12);
    expect(ppoClip({ r: 0.1, A: -4, eps: 0.5 })).toBeCloseTo(-2, 12);
  });

  for (const [name, bad] of [
    ["eps", 0],
    ["eps", 1],
    ["eps", -0.1],
    ["eps", 1.5],
    ["eps", Number.NaN],
    ["eps", Number.POSITIVE_INFINITY],
    ["r", -0.001],
    ["r", Number.NaN],
    ["r", Number.POSITIVE_INFINITY],
    ["A", Number.NaN],
    ["A", Number.POSITIVE_INFINITY],
    ["A", Number.NEGATIVE_INFINITY],
  ] as Array<[string, number]>) {
    it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
      expect(() => ppoClip({ r: 1.1, A: 1, eps: 0.2, [name]: bad })).toThrow(RangeError);
      expect(() => ppoClip({ r: 1.1, A: 1, eps: 0.2, [name]: bad })).toThrow(new RegExp(`\\b${name}\\b`));
    });
  }

  it("P-020-19 · the objective is positively homogeneous in the advantage: L(r, k A) = k L(r, A) for k > 0", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 3, noNaN: true }),
        fc.double({ min: -10, max: 10, noNaN: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true }),
        fc.double({ min: 0.001, max: 1000, noNaN: true }),
        (r, A, e, k) => {
          const a = ppoClip({ r, A: k * A, eps: e });
          const b = k * ppoClip({ r, A, eps: e });
          expect(close(a, b, 1e-12) || Math.abs(a - b) < 1e-300).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-20 · at r = 1 the objective equals the advantage, exactly", () => {
    fc.assert(
      fc.property(
        fc.double({ min: -10, max: 10, noNaN: true }),
        fc.double({ min: 0.01, max: 0.99, noNaN: true }),
        (A, e) => {
          expect(ppoClip({ r: 1, A, eps: e })).toBe(A);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-21 · saturation: for A > 0 the objective is constant for r >= 1 + eps; for A < 0 it is constant for r <= 1 - eps", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 0.99, noNaN: true }),
        fc.double({ min: 0.001, max: 10, noNaN: true }),
        fc.double({ min: 0, max: 5, noNaN: true }),
        fc.double({ min: 0, max: 5, noNaN: true }),
        (e, a, d1, d2) => {
          const pos = ppoClip({ r: 1 + e + d1, A: a, eps: e });
          expect(ppoClip({ r: 1 + e + d2, A: a, eps: e })).toBe(pos);
          expect(pos).toBeCloseTo((1 + e) * a, 9);
          const lowAt = (d: number) => ppoClip({ r: Math.max(0, 1 - e - d), A: -a, eps: e });
          expect(lowAt(Math.min(d1, 1 - e))).toBe(lowAt(Math.min(d2, 1 - e)));
        },
      ),
      { numRuns: 200 },
    );
  });
});
