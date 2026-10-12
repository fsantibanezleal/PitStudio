// T-020-030 [red] · FR-020-22 (the decision-rule display: "<challenger> better than <baseline>" only when the oriented interval has lo > 0, "<baseline> better than <challenger>" only when hi < 0, "no significant difference" otherwise,
// an interval touching 0 included; McNemar needs p < 0.05 and takes its direction from the discordant counts; n = 1 reads "single real event — no significance test"), FR-000-05 and P-020-01, P-020-02, P-020-03.
//
// Existing API of `~/results/verdict` (kept): pairedVerdict(interval, orientation): "challenger" | "baseline" | "none" | "unavailable"; mcnemarVerdict(b, c, p).
// New API of this task (web/src/results/verdict.ts):
//   verdictLabel(verdict: Verdict | "single", challenger: string, baseline: string): string
//       "challenger" -> "<challenger> better than <baseline>", "baseline" -> "<baseline> better than <challenger>", "none" -> "no significant difference",
//       "single" -> "single real event — no significance test", "unavailable" -> "" (an unusable interval claims nothing and prints no claim);
//   singleEventVerdict(n: number): "single" | null            "single" exactly when n === 1;
//   mcnemarVerdict additionally returns "unavailable" for a negative, fractional or non-finite count (the discordant counts of a McNemar table are integers >= 0).
// Oracles: the EARS truth table written out by hand; exact McNemar p = 2 * P(X <= min(b, c)), X ~ Binomial(b + c, 1/2) (b = 10, c = 0: 2 * 2^-10 = 0.001953125, hand calculation); the algebra of the rule for the properties
// (negation swaps the roles, negation with the orientation flipped leaves the verdict, widening cannot create a claim, a positive scale cannot change a sign).
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { mcnemarVerdict, pairedVerdict, singleEventVerdict, verdictLabel } from "~/results/verdict";

const H = "higher-is-better";
const L = "lower-is-better";
const iv = (lo: number, hi: number) => ({ lo, hi });

describe("paired verdict: the truth table of FR-020-22", () => {
  const table: Array<[string, number, number, string, string]> = [
    ["above 0", 0.1, 2, H, "challenger"],
    ["below 0", -2, -0.1, H, "baseline"],
    ["straddling 0", -1, 1, H, "none"],
    ["lower bound exactly 0 (touching)", 0, 1, H, "none"],
    ["upper bound exactly 0 (touching)", -1, 0, H, "none"],
    ["the point interval 0", 0, 0, H, "none"],
    ["a tiny positive lower bound", 1e-300, 1, H, "challenger"],
    ["a tiny negative upper bound", -1, -1e-300, H, "baseline"],
    ["above 0, lower is better", 0.1, 2, L, "baseline"],
    ["below 0, lower is better", -2, -0.1, L, "challenger"],
    ["straddling, lower is better", -1, 1, L, "none"],
    ["touching at 0, lower is better", 0, 1, L, "none"],
    ["touching at 0 from below, lower is better", -1, 0, L, "none"],
  ];
  for (const [what, lo, hi, orientation, expected] of table) {
    it(`FR-020-22 · ${what} (${orientation}): ${expected}`, () => {
      expect(pairedVerdict(iv(lo, hi), orientation)).toBe(expected);
    });
  }

  it("FR-020-22 · a non-finite or reversed interval, a missing one or an unknown orientation claims nothing", () => {
    for (const bad of [
      iv(Number.NaN, 1),
      iv(0, Number.POSITIVE_INFINITY),
      iv(Number.NEGATIVE_INFINITY, 1),
      iv(2, 1),
      undefined,
    ]) {
      expect(pairedVerdict(bad as never, H), JSON.stringify(bad)).toBe("unavailable");
    }
    for (const o of ["", "up", "HIGHER-IS-BETTER", "higher_is_better"])
      expect(pairedVerdict(iv(1, 2), o), o).toBe("unavailable");
  });
});

describe("McNemar verdict (FR-020-22)", () => {
  it("FR-020-22 · p below 0.05 with more challenger-only wins is the challenger; with more baseline-only wins the baseline", () => {
    expect(mcnemarVerdict(10, 0, 0.001953125)).toBe("challenger");
    expect(mcnemarVerdict(0, 10, 0.001953125)).toBe("baseline");
  });

  it("FR-020-22 · p of 0.05 or more is no difference whatever the counts, and p just below 0.05 is a claim", () => {
    expect(mcnemarVerdict(10, 2, 0.05)).toBe("none");
    expect(mcnemarVerdict(10, 2, 0.5)).toBe("none");
    expect(mcnemarVerdict(10, 2, 1)).toBe("none");
    expect(mcnemarVerdict(10, 2, 0.0499999)).toBe("challenger");
  });

  it("FR-020-22 · equal discordant counts are no difference even with p below 0.05 (the direction is undefined)", () => {
    expect(mcnemarVerdict(7, 7, 0.01)).toBe("none");
  });

  it("FR-020-22 · the exact test by hand: b = 10, c = 0 gives p = 2 * 2^-10 = 0.001953125, which is below 0.05", () => {
    const p = 2 * 0.5 ** 10;
    expect(p).toBe(0.001953125);
    expect(mcnemarVerdict(10, 0, p)).toBe("challenger");
  });

  it("FR-020-22 · negative, fractional or non-finite counts and a non-finite p claim nothing", () => {
    for (const [b, c, p] of [
      [-1, 5, 0.01],
      [5, -1, 0.01],
      [1.5, 5, 0.01],
      [5, 0.5, 0.01],
      [Number.NaN, 1, 0.01],
      [10, 0, Number.NaN],
      [10, 0, Number.POSITIVE_INFINITY],
      [Number.POSITIVE_INFINITY, 0, 0.01],
    ] as Array<[number, number, number]>) {
      expect(mcnemarVerdict(b, c, p), JSON.stringify([b, c, p])).toBe("unavailable");
    }
  });
});

describe("the words of the display (FR-020-22, FR-000-05)", () => {
  it("FR-020-22 · '<challenger> better than <baseline>', '<baseline> better than <challenger>' and 'no significant difference'", () => {
    expect(verdictLabel("challenger", "learned dispatcher", "shortest-queue rule")).toBe(
      "learned dispatcher better than shortest-queue rule",
    );
    expect(verdictLabel("baseline", "learned dispatcher", "shortest-queue rule")).toBe(
      "shortest-queue rule better than learned dispatcher",
    );
    expect(verdictLabel("none", "learned dispatcher", "shortest-queue rule")).toBe(
      "no significant difference",
    );
  });

  it("FR-020-22 · for n = 1 the label is 'single real event — no significance test', and only for n = 1", () => {
    expect(singleEventVerdict(1)).toBe("single");
    for (const n of [0, 2, 3, 100, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])
      expect(singleEventVerdict(n), String(n)).toBeNull();
    expect(verdictLabel("single", "a", "b")).toBe("single real event — no significance test");
  });

  it("FR-000-05 · an unusable verdict prints no claim at all, neither 'better than' nor 'no significant difference'", () => {
    expect(verdictLabel("unavailable", "a", "b")).toBe("");
  });

  it("FR-000-05 · the label of a verdict never names the challenger when the baseline won and the other way round, whatever the names", () => {
    for (const [c, b] of [
      ["x", "y"],
      ["better than", "no significant difference"],
      ["", "base"],
      ["<b>c</b>", "é中"],
    ]) {
      const win = verdictLabel("challenger", c as string, b as string);
      expect(win.startsWith(c as string)).toBe(true);
      expect(win.endsWith(b as string)).toBe(true);
      const loss = verdictLabel("baseline", c as string, b as string);
      expect(loss.startsWith(b as string)).toBe(true);
      expect(loss.endsWith(c as string)).toBe(true);
    }
  });
});

describe("properties of the rule", () => {
  const swap = (v: string) => (v === "challenger" ? "baseline" : v === "baseline" ? "challenger" : v);
  const flip = (o: string) => (o === H ? L : H);
  const value = fc.oneof(
    fc.constant(0),
    fc.double({ min: 1e-9, max: 1e9, noNaN: true }),
    fc.double({ min: 1e-9, max: 1e9, noNaN: true }).map((x) => -x),
  );
  const interval = fc.tuple(value, value).map(([a, b]) => (a <= b ? iv(a, b) : iv(b, a)));
  const orientation = fc.constantFrom(H, L);

  it("P-020-01 · negating the interval swaps challenger and baseline and keeps 'no significant difference'", () => {
    fc.assert(
      fc.property(interval, orientation, (i, o) => {
        expect(pairedVerdict(iv(-i.hi, -i.lo), o)).toBe(swap(pairedVerdict(i, o)));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-01 · negating the interval and flipping the orientation leaves the verdict unchanged (the same claim about the same systems)", () => {
    fc.assert(
      fc.property(interval, orientation, (i, o) => {
        expect(pairedVerdict(iv(-i.hi, -i.lo), flip(o))).toBe(pairedVerdict(i, o));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-02 · widening an interval never turns 'no significant difference' into a 'better than' verdict, and never turns a claim into the opposite one", () => {
    fc.assert(
      fc.property(
        interval,
        orientation,
        fc.double({ min: 0, max: 1e6, noNaN: true }),
        fc.double({ min: 0, max: 1e6, noNaN: true }),
        (i, o, dl, dh) => {
          const before = pairedVerdict(i, o);
          const after = pairedVerdict(iv(i.lo - dl, i.hi + dh), o);
          if (before === "none") expect(after).toBe("none");
          if (before === "challenger") expect(after).not.toBe("baseline");
          if (before === "baseline") expect(after).not.toBe("challenger");
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-03 · multiplying both bounds by k in [1e-6, 1e6] leaves the verdict unchanged", () => {
    fc.assert(
      fc.property(interval, orientation, fc.double({ min: 1e-6, max: 1e6, noNaN: true }), (i, o, k) => {
        expect(pairedVerdict(iv(i.lo * k, i.hi * k), o)).toBe(pairedVerdict(i, o));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-03 · the verdict only depends on the signs of the oriented bounds (hand relation)", () => {
    fc.assert(
      fc.property(interval, orientation, (i, o) => {
        const lo = o === H ? i.lo : -i.hi;
        const hi = o === H ? i.hi : -i.lo;
        const expected = lo > 0 ? "challenger" : hi < 0 ? "baseline" : "none";
        expect(pairedVerdict(i, o)).toBe(expected);
      }),
      { numRuns: 200 },
    );
  });
});
