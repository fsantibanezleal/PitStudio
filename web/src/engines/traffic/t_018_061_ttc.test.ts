// T-018-061 [red] · FR-018-55 (constant-velocity time to collision and near-misses per 1,000 h), P-018-19 (velocity scaling), P-018-20 (rigid-motion
// invariance), P-018-21 (pair symmetry) for the `traffic` engine of spec 018. Browser half (FR-018-54, Rapier snapshot hash in three browsers):
// web/e2e/parity/t_018_061_rapier_hash.spec.ts.
//
// Expected API (module `~/engines/traffic/ttc`, file web/src/engines/traffic/ttc.ts; the Rapier world and agents live in world.ts and agents.ts):
//     ttc(args: { relative_position_m: [number, number]; relative_velocity_m_per_s: [number, number]; radius_m: number })
//       -> { status: "closing", ttc_s } | { status: "overlapping", ttc_s: 0 } | { status: "not-closing" }       (DC-018-02 `traffic` function "ttc")
//         p = position of b minus position of a, w = velocity of b minus velocity of a. TTC is the smallest positive root tau of |p + w tau| = R:
//         "overlapping" (ttc 0) when |p| <= R already; "not-closing" (no ttc_s, infinity) when the pair does not close (p . w >= 0) or the discriminant is
//         negative; a grazing contact (discriminant 0) is "closing".
//     nearMissesPer1000h(nearMisses: number, exposureSeconds: number): number          near-misses x 1000 / exposure in hours; RangeError for an exposure
//         <= 0, a non-finite value, or a negative or fractional count
//   A malformed or out-of-range argument (non-finite component, radius <= 0, a component beyond +-100 km or +-60 m/s) throws an error with `code === "E_RANGE"`
//   (non-finite: "E_NONFINITE"); a vector that is not a pair `E_SCHEMA` (FR-018-38 typed errors).
//
// Oracles (independent of the code under test):
//   - the published worked example of docs M20 (docs/methods and the traffic theory page): truck 10 m/s east, light vehicle 5 m/s west, 100 m apart, R = 4 m
//     gives TTC = 6.4 s; hand cases for head-on, radial, glancing, tangent (discriminant exactly 0), diverging, crossing and overlapping;
//   - the closed form of the smallest positive root of |p + w tau| = R written in this file;
//   - the metamorphic relations of spec 018 section 4 (P-018-19..21).
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { nearMissesPer1000h, ttc } from "~/engines/traffic/ttc";

type Vec = [number, number];
interface Out {
  status: "closing" | "overlapping" | "not-closing";
  ttc_s?: number;
}
const run = (p: Vec, w: Vec, R: number) =>
  ttc({ relative_position_m: p, relative_velocity_m_per_s: w, radius_m: R }) as Out;
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}
/** Closed form: the smallest positive root of |p + w tau| = R, or null when the pair never closes to R. */
function hand(p: Vec, w: Vec, R: number): number | "overlap" | null {
  const pp = p[0] * p[0] + p[1] * p[1];
  if (pp <= R * R) return "overlap";
  const ww = w[0] * w[0] + w[1] * w[1];
  const pw = p[0] * w[0] + p[1] * w[1];
  if (ww === 0 || pw >= 0) return null;
  const disc = pw * pw - ww * (pp - R * R);
  if (disc < 0) return null;
  return (-pw - Math.sqrt(disc)) / ww;
}

describe("hand cases (FR-018-55)", () => {
  it("FR-018-55 · docs M20: truck 10 m/s east, light vehicle 5 m/s west, 100 m apart, R = 4 m gives TTC = 6.4 s", () => {
    // p = (100, 0) - (0, 0), w = (-5, 0) - (10, 0) = (-15, 0): (100 - 15 tau) = 4
    const r = run([100, 0], [-15, 0], 4);
    expect(r.status).toBe("closing");
    expect(r.ttc_s).toBeCloseTo(6.4, 12);
  });

  it("FR-018-55 · radial approach p = (30, 40), w = (-3, -4), R = 5: TTC = (50 - 5) / 5 = 9 s", () => {
    const r = run([30, 40], [-3, -4], 5);
    expect(r.status).toBe("closing");
    expect(r.ttc_s).toBeCloseTo(9, 12);
  });

  it("FR-018-55 · a glancing pass p = (100, 0), w = (-10, 2), R = 20: 104 tau^2 - 2000 tau + 9600 = 0, discriminant 6,400, tau = 1920 / 208 = 9.230769 s", () => {
    const r = run([100, 0], [-10, 2], 20);
    expect(r.status).toBe("closing");
    expect(r.ttc_s).toBeCloseTo(1920 / 208, 12);
  });

  it("FR-018-55 · the same pass with R = 10 or 4 misses (negative discriminant): not closing, no TTC", () => {
    for (const R of [4, 10]) {
      const r = run([100, 0], [-10, 2], R);
      expect(r.status).toBe("not-closing");
      expect("ttc_s" in r).toBe(false);
    }
  });

  it("FR-018-55 · a tangent pass (closest approach exactly R = 80 m: p = (100, 0), w = (-3, 4), discriminant 0) is closing with TTC = 300 / 25 = 12 s", () => {
    const r = run([100, 0], [-3, 4], 80);
    expect(r.status).toBe("closing");
    expect(r.ttc_s).toBeCloseTo(12, 12);
    // the closest approach is |p x w| / |w| = 400 / 5 = 80 m: a larger radius is entered, a smaller one is missed
    expect(run([100, 0], [-3, 4], 80.0001).status).toBe("closing");
    expect(run([100, 0], [-3, 4], 79.9999).status).toBe("not-closing");
  });

  it("FR-018-55 · diverging, perpendicular and zero relative velocity are not closing", () => {
    expect(run([100, 0], [10, 0], 4).status).toBe("not-closing");
    expect(run([100, 0], [0, 10], 4).status).toBe("not-closing");
    expect(run([100, 0], [0, 0], 4).status).toBe("not-closing");
  });

  it("FR-018-55 · already overlapping (|p| <= R, the boundary included) is overlapping with TTC 0, whatever the velocity", () => {
    for (const w of [
      [-15, 0],
      [15, 0],
      [0, 0],
    ] as Vec[]) {
      const r = run([3, 0], w, 4);
      expect(r.status).toBe("overlapping");
      expect(r.ttc_s).toBe(0);
    }
    expect(run([4, 0], [-1, 0], 4)).toEqual({ status: "overlapping", ttc_s: 0 });
    expect(run([0, 0], [0, 0], 4).status).toBe("overlapping");
  });

  it("FR-018-55 · it agrees with the closed form on random inputs (rtol 1e-12) and classifies closing, not-closing and overlapping alike", () => {
    const comp = fc.double({ min: -500, max: 500, noNaN: true });
    fc.assert(
      fc.property(
        fc.tuple(comp, comp),
        fc.tuple(
          fc.double({ min: -30, max: 30, noNaN: true }),
          fc.double({ min: -30, max: 30, noNaN: true }),
        ),
        fc.double({ min: 0.5, max: 50, noNaN: true }),
        (p, w, R) => {
          const want = hand(p, w, R);
          const got = run(p, w, R);
          if (want === "overlap") return got.status === "overlapping" && got.ttc_s === 0;
          if (want === null) return got.status === "not-closing" && !("ttc_s" in got);
          return got.status === "closing" && Math.abs((got.ttc_s as number) - want) <= 1e-12 * want;
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("metamorphic relations (P-018-19, P-018-20, P-018-21)", () => {
  const comp = fc.double({ min: -500, max: 500, noNaN: true });
  const vel = fc.double({ min: -30, max: 30, noNaN: true });
  /** A pair that closes: a relative position, a velocity mostly towards the origin, and a radius the path reaches. */
  const closing = fc
    .record({
      p: fc.tuple(comp, comp),
      w: fc.tuple(vel, vel),
      R: fc.double({ min: 0.5, max: 50, noNaN: true }),
    })
    .filter(({ p, w, R }) => typeof hand(p, w, R) === "number" && (hand(p, w, R) as number) > 1e-6);

  it("P-018-19 · TTC(p, k w) = TTC(p, w) / k for closing pairs and k in [0.1, 10] (rtol 1e-12)", () => {
    fc.assert(
      fc.property(closing, fc.double({ min: 0.1, max: 10, noNaN: true }), ({ p, w, R }, k) => {
        const base = run(p, w, R).ttc_s as number;
        const scaled = run(p, [k * w[0], k * w[1]], R);
        return (
          scaled.status === "closing" && Math.abs((scaled.ttc_s as number) - base / k) <= 1e-12 * (base / k)
        );
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-20 · translating and rotating both agents (the relative vectors rotate, the translation cancels) leaves the TTC unchanged (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        closing,
        fc.double({ min: 0, max: 6.283185307179586, noNaN: true }),
        ({ p, w, R }, angle) => {
          const c = Math.cos(angle);
          const s = Math.sin(angle);
          const rot = (v: Vec): Vec => [c * v[0] - s * v[1], s * v[0] + c * v[1]];
          const base = run(p, w, R).ttc_s as number;
          const turned = run(rot(p), rot(w), R);
          return turned.status === "closing" && Math.abs((turned.ttc_s as number) - base) <= 1e-12 * base;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-21 · pair symmetry: TTC(a, b) = TTC(b, a), i.e. (p, w) and (-p, -w) give exactly the same answer", () => {
    fc.assert(
      fc.property(
        fc.tuple(comp, comp),
        fc.tuple(vel, vel),
        fc.double({ min: 0.5, max: 50, noNaN: true }),
        (p, w, R) => {
          const a = run(p, w, R);
          const b = run([-p[0], -p[1]], [-w[0], -w[1]], R);
          return a.status === b.status && a.ttc_s === b.ttc_s;
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("hostile TTC inputs and the near-miss rate (FR-018-55, FR-018-38)", () => {
  it("FR-018-55 · a radius <= 0, a component beyond the schema ranges and non-finite components are rejected", () => {
    expect(codeOf(() => run([100, 0], [-15, 0], 0))).toBe("E_RANGE");
    expect(codeOf(() => run([100, 0], [-15, 0], -4))).toBe("E_RANGE");
    expect(codeOf(() => run([100001, 0], [-15, 0], 4))).toBe("E_RANGE");
    expect(codeOf(() => run([100, 0], [-61, 0], 4))).toBe("E_RANGE");
    expect(codeOf(() => run([Number.NaN, 0], [-15, 0], 4))).toMatch(/E_NONFINITE|E_RANGE/);
    expect(codeOf(() => run([100, 0], [Number.POSITIVE_INFINITY, 0], 4))).toMatch(/E_NONFINITE|E_RANGE/);
    expect(
      codeOf(() =>
        ttc({ relative_position_m: [1, 2, 3], relative_velocity_m_per_s: [1, 2], radius_m: 4 } as never),
      ),
    ).toBe("E_SCHEMA");
    expect(
      codeOf(() =>
        ttc({ relative_position_m: [1], relative_velocity_m_per_s: [1, 2], radius_m: 4 } as never),
      ),
    ).toBe("E_SCHEMA");
  });

  it("FR-018-55 · near-misses per 1,000 h: 2 near-misses in 3,600 s is 2,000 per 1,000 h; 5 in 1,800 s is 10,000; none is 0", () => {
    expect(nearMissesPer1000h(2, 3600)).toBeCloseTo(2000, 9);
    expect(nearMissesPer1000h(5, 1800)).toBeCloseTo(10000, 9);
    expect(nearMissesPer1000h(0, 3600)).toBe(0);
    expect(nearMissesPer1000h(1, 3.6e6)).toBeCloseTo(1, 12); // 1 in 1,000 h
  });

  it("FR-018-55 · the rate is linear in the count and inversely proportional to the exposure (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1000 }),
        fc.double({ min: 1, max: 1e7, noNaN: true }),
        fc.double({ min: 1.1, max: 10, noNaN: true }),
        (n, t, k) => {
          const base = nearMissesPer1000h(n, t);
          return (
            Math.abs(nearMissesPer1000h(n, t * k) - base / k) <= 1e-12 * Math.max(base / k, 1e-300) &&
            Math.abs(nearMissesPer1000h(2 * n, t) - 2 * base) <= 1e-12 * Math.max(2 * base, 1e-300)
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-55 · an exposure <= 0 or non-finite and a negative, fractional or non-finite count throw a RangeError", () => {
    for (const t of [0, -1, Number.NaN, Number.POSITIVE_INFINITY])
      expect(() => nearMissesPer1000h(1, t)).toThrow(RangeError);
    for (const n of [-1, 0.5, Number.NaN, Number.POSITIVE_INFINITY])
      expect(() => nearMissesPer1000h(n, 3600)).toThrow(RangeError);
  });
});
