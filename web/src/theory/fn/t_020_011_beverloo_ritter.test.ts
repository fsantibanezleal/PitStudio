// T-020-011 [red] · FR-020-49 (the teaching functions Beverloo discharge and Ritter dam break equal their analytical forms on hand-calculated cases within rtol 1e-9), FR-020-50 (NaN, infinity or an argument outside the domain:
// a RangeError naming the argument, no value) and P-020-10, P-020-11, P-020-12 (Beverloo), P-020-13, P-020-14, P-020-15 (Ritter).
//
// Expected API:
//   `~/theory/fn/beverloo` (web/src/theory/fn/beverloo.ts): beverloo({ D, d, C, k, rhoB }: { D: number; d: number; C: number; k: number; rhoB: number }, g = 9.80665): number
//       the mass discharge rate through an orifice, W = C rhoB sqrt(g) (D - k d)^(5/2) in kg/s (D orifice diameter in m, d grain diameter in m, C and k dimensionless, rhoB bulk density in kg/m^3, g in m/s^2), and 0 when D <= k d;
//       RangeError (message names the argument as written above) when an argument is NaN or infinite, or D, d, C, k, rhoB or g is <= 0.
//   `~/theory/fn/ritter` (web/src/theory/fn/ritter.ts): ritter({ x, t, h0 }, g = 9.80665): number, the depth h(x, t) in m of the Ritter dam-break solution on a dry bed (dam at x = 0, reservoir of depth h0 for x < 0, c0 = sqrt(g h0)):
//       h = h0 for x <= -c0 t; h = (2 c0 - x/t)^2 / (9 g) for -c0 t < x < 2 c0 t; h = 0 for x >= 2 c0 t; at t = 0: h0 for x < 0 and 0 for x > 0;
//       ritterFront({ t, h0 }, g = 9.80665): number = 2 sqrt(g h0) t; RangeError naming the argument for NaN, infinity, h0 <= 0, g <= 0, t < 0 (t = 0 is allowed), x non-finite.
// Oracles: the closed forms written out above with hand arithmetic (D - k d, 5/2 power, 4 h0 / 9, h0 / 9, front 2 sqrt(g h0) t), values computed outside the code under test with 50-digit decimal arithmetic (Python decimal, recipe in the
// comments), the Beverloo law W = C rho_b sqrt(g) (D - k d)^(5/2) (Beverloo, Leniger and van de Velde, Chem. Eng. Sci. 15, 260-269, 1961) and the Ritter solution (Ritter 1892; Stoker 1957).
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { beverloo } from "~/theory/fn/beverloo";
import { ritter, ritterFront } from "~/theory/fn/ritter";

const G = 9.80665;
const close = (a: number, b: number, rtol = 1e-9) =>
  Math.abs(a - b) <= rtol * Math.max(Math.abs(b), Number.MIN_VALUE);

describe("Beverloo discharge (FR-020-49)", () => {
  // Decimal reference: W = C * rho * sqrt(9.80665) * (D - k d)^2.5 with Python decimal at 50 digits.
  const cases = [
    { D: 0.1, d: 0.005, C: 0.58, k: 1.4, rhoB: 1500, w: 7.185995845594245 },
    { D: 0.25, d: 0.02, C: 0.55, k: 1.5, rhoB: 1800, w: 70.38048162258431 },
    { D: 0.05, d: 0.001, C: 0.62, k: 1.6, rhoB: 1200, w: 1.2007336382251483 },
    { D: 1.0, d: 0.1, C: 0.5, k: 2.0, rhoB: 3000, w: 2688.9118453381843 },
  ];
  for (const c of cases) {
    it(`FR-020-49 · D = ${c.D} m, d = ${c.d} m, C = ${c.C}, k = ${c.k}, rho_b = ${c.rhoB} kg/m3 gives ${c.w} kg/s`, () => {
      expect(close(beverloo(c), c.w, 1e-12)).toBe(true);
    });
  }

  it("FR-020-49 · hand arithmetic: D - k d = 0.093 m, 0.093^2.5 = 0.0026376..., W = 870 sqrt(g) * that = 7.186 kg/s", () => {
    const x = 0.1 - 1.4 * 0.005;
    expect(x).toBeCloseTo(0.093, 12);
    expect(x ** 2.5).toBeCloseTo(0.0026376, 6);
    expect(beverloo({ D: 0.1, d: 0.005, C: 0.58, k: 1.4, rhoB: 1500 })).toBeCloseTo(7.186, 3);
  });

  it("FR-020-49 · another gravity scales the discharge by sqrt(g): the Moon (1.62 m/s2) gives sqrt(1.62 / 9.80665) of the Earth value", () => {
    const earth = beverloo(cases[0] as never);
    expect(close(beverloo(cases[0] as never, 1.62), earth * Math.sqrt(1.62 / G), 1e-12)).toBe(true);
  });

  it("FR-020-49 · there is no discharge when the orifice is not larger than k grains: D = k d and D < k d give exactly 0", () => {
    expect(beverloo({ D: 0.0069, d: 0.005, C: 0.58, k: 1.4, rhoB: 1500 })).toBe(0);
    expect(beverloo({ D: 0.001, d: 0.005, C: 0.58, k: 1.4, rhoB: 1500 })).toBe(0);
    expect(beverloo({ D: 0.5, d: 0.5, C: 0.58, k: 1, rhoB: 1500 })).toBe(0);
  });

  const ok = { D: 0.1, d: 0.005, C: 0.58, k: 1.4, rhoB: 1500 };
  for (const name of ["D", "d", "C", "k", "rhoB"] as const) {
    for (const bad of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, 0, -1, -1e-300]) {
      it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
        expect(() => beverloo({ ...ok, [name]: bad })).toThrow(RangeError);
        expect(() => beverloo({ ...ok, [name]: bad })).toThrow(new RegExp(`\\b${name}\\b`));
      });
    }
  }

  it("FR-020-50 · a non-positive or non-finite g throws a RangeError naming g", () => {
    for (const bad of [0, -9.8, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => beverloo(ok, bad)).toThrow(RangeError);
      expect(() => beverloo(ok, bad)).toThrow(/\bg\b/);
    }
  });

  it("FR-020-50 · missing and mistyped arguments are rejected, not turned into NaN", () => {
    expect(() => beverloo({ ...ok, D: undefined as never })).toThrow(RangeError);
    expect(() => beverloo({ ...ok, d: "0.005" as never })).toThrow(RangeError);
    expect(() => beverloo({ ...ok, k: null as never })).toThrow(RangeError);
  });

  const dom = {
    D: fc.double({ min: 0.01, max: 5, noNaN: true }),
    d: fc.double({ min: 0.0005, max: 0.05, noNaN: true }),
    C: fc.double({ min: 0.3, max: 0.9, noNaN: true }),
    k: fc.double({ min: 1, max: 3, noNaN: true }),
    rhoB: fc.double({ min: 500, max: 3000, noNaN: true }),
  };

  it("P-020-10 · the discharge is linear in the bulk density: W(s rho) = s W(rho) for rho in [500, 3000]", () => {
    fc.assert(
      fc.property(fc.record(dom), fc.double({ min: 0.5, max: 2, noNaN: true }), (a, s) => {
        const w = beverloo(a);
        const scaled = beverloo({ ...a, rhoB: a.rhoB * s });
        expect(close(scaled, w * s, 1e-12) || (w === 0 && scaled === 0)).toBe(true);
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-11 · the discharge is 0 for D <= k d and strictly increasing in D above it", () => {
    fc.assert(
      fc.property(
        fc.record(dom),
        fc.double({ min: 1e-3, max: 1, noNaN: true }),
        fc.double({ min: 1e-3, max: 1, noNaN: true }),
        (a, e1, e2) => {
          const edge = a.k * a.d;
          expect(beverloo({ ...a, D: edge })).toBe(0);
          expect(beverloo({ ...a, D: edge * (1 - e1 / 2) })).toBe(0);
          const lo = edge * (1 + Math.min(e1, e2));
          const hi = edge * (1 + Math.max(e1, e2) + 0.01);
          expect(beverloo({ ...a, D: hi })).toBeGreaterThan(beverloo({ ...a, D: lo }));
          expect(beverloo({ ...a, D: lo })).toBeGreaterThan(0);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-12 · multiplying D and d by lambda multiplies the discharge by lambda^(5/2)", () => {
    fc.assert(
      fc.property(fc.record(dom), fc.double({ min: 0.1, max: 10, noNaN: true }), (a, lambda) => {
        const w = beverloo(a);
        fc.pre(w > 0);
        expect(close(beverloo({ ...a, D: a.D * lambda, d: a.d * lambda }), w * lambda ** 2.5, 1e-12)).toBe(
          true,
        );
      }),
      { numRuns: 200 },
    );
  });
});

describe("Ritter dam break (FR-020-49)", () => {
  const h0 = 2;
  const c0 = Math.sqrt(G * h0); // 4.428690551393267 m/s (decimal reference)
  const t = 3;

  it("FR-020-49 · the front is 2 sqrt(g h0) t: h0 = 2 m, t = 3 s gives 26.572143308359603 m (decimal reference)", () => {
    expect(close(ritterFront({ t, h0 }), 26.572143308359603, 1e-12)).toBe(true);
    expect(ritterFront({ t: 0, h0 })).toBe(0);
  });

  it("FR-020-49 · the depth at the dam, x = 0, is 4 h0 / 9 for every t > 0", () => {
    for (const time of [0.001, 0.5, 3, 1e3])
      expect(close(ritter({ x: 0, t: time, h0 }), (4 * h0) / 9, 1e-12), String(time)).toBe(true);
  });

  const xi: Array<[string, number, number]> = [
    ["far inside the reservoir", -3, h0],
    ["just inside the undisturbed reservoir (xi = -1.001)", -1.001, h0],
    ["the rarefaction at xi = -0.5", -0.5, (h0 * 2.5 ** 2) / 9],
    ["the rarefaction at xi = 0", 0, (4 * h0) / 9],
    ["the rarefaction at xi = 0.5", 0.5, (h0 * 1.5 ** 2) / 9],
    ["the rarefaction at xi = 1", 1, h0 / 9],
    ["the rarefaction at xi = 1.9", 1.9, (h0 * 0.1 ** 2) / 9],
    ["just beyond the front (xi = 2.001)", 2.001, 0],
    ["far downstream", 50, 0],
  ];
  for (const [what, ksi, expected] of xi) {
    it(`FR-020-49 · ${what}: h = ${expected}`, () => {
      const h = ritter({ x: ksi * c0 * t, t, h0 });
      if (expected === 0) expect(h).toBe(0);
      else expect(close(h, expected, 1e-12)).toBe(true);
    });
  }

  it("FR-020-49 · the profile is continuous at both ends of the rarefaction: h0 at x = -c0 t and 0 at the front", () => {
    expect(close(ritter({ x: -c0 * t * (1 - 1e-12), t, h0 }), h0, 1e-9)).toBe(true);
    expect(ritter({ x: 2 * c0 * t * (1 - 1e-12), t, h0 })).toBeLessThan(1e-9);
  });

  it("FR-020-49 · at t = 0 the dam is intact: h0 upstream, 0 downstream", () => {
    expect(ritter({ x: -1, t: 0, h0 })).toBe(h0);
    expect(ritter({ x: 1, t: 0, h0 })).toBe(0);
  });

  const ok = { x: 1, t: 2, h0: 1.5 };
  for (const [name, bad] of [
    ["x", Number.NaN],
    ["x", Number.POSITIVE_INFINITY],
    ["t", Number.NaN],
    ["t", -1],
    ["t", -1e-300],
    ["t", Number.POSITIVE_INFINITY],
    ["h0", 0],
    ["h0", -2],
    ["h0", Number.NaN],
    ["h0", Number.POSITIVE_INFINITY],
  ] as Array<[string, number]>) {
    it(`FR-020-50 · ${name} = ${bad} throws a RangeError naming ${name}`, () => {
      expect(() => ritter({ ...ok, [name]: bad })).toThrow(RangeError);
      expect(() => ritter({ ...ok, [name]: bad })).toThrow(new RegExp(`\\b${name}\\b`));
    });
  }

  it("FR-020-50 · the front function has the same domain: t < 0 and h0 <= 0 are rejected", () => {
    expect(() => ritterFront({ t: -1, h0: 1 })).toThrow(/\bt\b/);
    expect(() => ritterFront({ t: 1, h0: 0 })).toThrow(/\bh0\b/);
    expect(() => ritterFront({ t: Number.NaN, h0: 1 })).toThrow(RangeError);
    expect(() => ritter(ok, 0)).toThrow(/\bg\b/);
  });

  it("P-020-13 · self-similarity: h(lambda x, lambda t) = h(x, t) for lambda > 0, and h(0, t) = 4 h0 / 9", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.1, max: 50, noNaN: true }),
        fc.double({ min: 0.1, max: 20, noNaN: true }),
        fc.double({ min: -3, max: 3, noNaN: true }),
        fc.double({ min: 0.1, max: 10, noNaN: true }),
        (hh, tt, ksi, lambda) => {
          const c = Math.sqrt(G * hh);
          const x = ksi * c * tt;
          const a = ritter({ x, t: tt, h0: hh });
          const b = ritter({ x: x * lambda, t: tt * lambda, h0: hh });
          expect(close(a, b, 1e-12) || (a === 0 && b === 0)).toBe(true);
          expect(close(ritter({ x: 0, t: tt, h0: hh }), (4 * hh) / 9, 1e-12)).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-14 · mass conservation: the integral of h over the domain equals h0 L while the rarefaction has not reached the back wall (t < L / c0), trapezoid with 1e5 points", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 10, max: 1000, noNaN: true }),
        fc.double({ min: 0.5, max: 20, noNaN: true }),
        fc.double({ min: 0.05, max: 0.95, noNaN: true }),
        (L, hh, frac) => {
          const c = Math.sqrt(G * hh);
          const tt = (frac * L) / c; // t < L / c0
          const a = -L;
          const b = 2 * c * tt; // the front: nothing beyond
          const n = 100_000;
          const dx = (b - a) / n;
          let sum = 0.5 * (ritter({ x: a, t: tt, h0: hh }) + ritter({ x: b, t: tt, h0: hh }));
          for (let i = 1; i < n; i++) sum += ritter({ x: a + i * dx, t: tt, h0: hh });
          expect(Math.abs(sum * dx - hh * L) / (hh * L)).toBeLessThan(1e-6);
        },
      ),
      { numRuns: 20 },
    );
  });

  it("P-020-15 · multiplying h0 by k multiplies the front speed 2 sqrt(g h0) by sqrt(k)", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 100, noNaN: true }),
        fc.double({ min: 0.1, max: 10, noNaN: true }),
        fc.double({ min: 0.1, max: 50, noNaN: true }),
        (hh, k, tt) => {
          const base = ritterFront({ t: tt, h0: hh }) / tt;
          const scaled = ritterFront({ t: tt, h0: hh * k }) / tt;
          expect(close(scaled, base * Math.sqrt(k), 1e-12)).toBe(true);
          expect(close(base, 2 * Math.sqrt(G * hh), 1e-12)).toBe(true);
        },
      ),
      { numRuns: 200 },
    );
  });
});
