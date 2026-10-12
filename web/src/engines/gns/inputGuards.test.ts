// T-011-019 [red] · FR-011-15: hostile GNS inputs in the web engine `gns` (the Python side is tests/pipeline/test_t_011_019_gns_input_guards.py).
//
// Oracles (independent of the code under test; plan 011 test strategy FR-011-15: "invalid inputs written in the test"): one input per class of the
// requirement, built here by hand: N = 0, lengths other than those of FR-011-01 (positions 2 N, velocities 10 N = N x 5 x 2, particle type N, bounds 4,
// neighbour index 32 N, mask of the index's length), a neighbour index outside [0, N), an unknown particle type, a non-finite value. Each must give
// the message "rollout stopped — <reason>" (the em dash is part of the string fixed by the spec) and return no acceleration; the reason names the
// argument; a valid input gives ok.
//
// Expected API (module `web/src/engines/gns/inputGuards.ts`):
//   interface GnsInputs { n: number; positions: Float32Array; velocities: Float32Array; particleType: Int32Array; bounds: Float32Array;
//                         neighbourIndex: Int32Array; neighbourMask: Uint8Array }
//   validateGnsInputs(inputs: GnsInputs, nParticleTypes: number): { ok: true } | { ok: false; message: string }
//     message = "rollout stopped — " + a reason that names the offending argument (positions, velocities, particleType, bounds,
//     neighbourIndex, neighbourMask; for n <= 0 or a fractional n the reason names `n` or `positions`); never throws, also for arrays of the
//     wrong type or length.
import { describe, expect, it } from "vitest";
import { type GnsInputs, validateGnsInputs } from "./inputGuards";

const N_TYPES = 2;
const PREFIX = "rollout stopped — ";
const N = 12;

function valid(n = N): GnsInputs {
  const index = new Int32Array(32 * n);
  const mask = new Uint8Array(32 * n);
  for (let i = 0; i < n; i++) {
    for (let k = 0; k < Math.min(3, n - 1); k++) {
      index[32 * i + k] = (i + 1 + k) % n;
      mask[32 * i + k] = 1;
    }
  }
  return {
    n,
    positions: Float32Array.from({ length: 2 * n }, (_, i) => 0.001 * i),
    velocities: Float32Array.from({ length: 10 * n }, (_, i) => 0.0005 * ((i % 7) - 3)),
    particleType: Int32Array.from({ length: n }, (_, i) => i % N_TYPES),
    bounds: new Float32Array([0, 0, 1, 1]),
    neighbourIndex: index,
    neighbourMask: mask,
  };
}

function withFields(fields: Partial<GnsInputs>, n = N): GnsInputs {
  return { ...valid(n), ...fields };
}

type ArrayKey = "positions" | "velocities" | "particleType" | "bounds" | "neighbourIndex";

function setAt(key: ArrayKey, index: number, value: number): GnsInputs {
  const x = valid();
  (x[key] as unknown as Record<number, number>)[index] = value;
  return x;
}

const HOSTILE: [string, GnsInputs, RegExp][] = [
  [
    "n zero",
    withFields({
      n: 0,
      positions: new Float32Array(0),
      velocities: new Float32Array(0),
      particleType: new Int32Array(0),
      neighbourIndex: new Int32Array(0),
      neighbourMask: new Uint8Array(0),
    }),
    /positions|\bn\b/,
  ],
  ["n negative", withFields({ n: -3 }), /positions|\bn\b/],
  ["n fractional", withFields({ n: 2.5 }), /positions|\bn\b/],
  ["positions too short", withFields({ positions: new Float32Array(23) }), /positions/],
  ["positions three columns", withFields({ positions: new Float32Array(36) }), /positions/],
  ["velocities four steps", withFields({ velocities: new Float32Array(96) }), /velocities/],
  ["velocities three components", withFields({ velocities: new Float32Array(180) }), /velocities/],
  ["particle type too long", withFields({ particleType: new Int32Array(13) }), /particleType/],
  ["bounds three values", withFields({ bounds: new Float32Array(3) }), /bounds/],
  ["bounds five values", withFields({ bounds: new Float32Array(5) }), /bounds/],
  ["index 31 columns", withFields({ neighbourIndex: new Int32Array(31 * N) }), /neighbourIndex/],
  ["index 33 columns", withFields({ neighbourIndex: new Int32Array(33 * N) }), /neighbourIndex/],
  ["mask other length", withFields({ neighbourMask: new Uint8Array(31 * N) }), /neighbourMask/],
  ["index minus one", setAt("neighbourIndex", 0, -1), /neighbourIndex/],
  ["index equals n", setAt("neighbourIndex", 5, N), /neighbourIndex/],
  ["index far beyond", setAt("neighbourIndex", 383, 2 ** 31 - 1), /neighbourIndex/],
  ["unknown type", setAt("particleType", 2, N_TYPES), /particleType/],
  ["negative type", setAt("particleType", 2, -1), /particleType/],
  ["position nan", setAt("positions", 3, Number.NaN), /positions/],
  ["position infinity", setAt("positions", 0, Number.POSITIVE_INFINITY), /positions/],
  ["velocity nan", setAt("velocities", 17, Number.NaN), /velocities/],
  ["velocity minus infinity", setAt("velocities", 119, Number.NEGATIVE_INFINITY), /velocities/],
  ["bounds nan", setAt("bounds", 2, Number.NaN), /bounds/],
  ["bounds infinity", setAt("bounds", 3, Number.POSITIVE_INFINITY), /bounds/],
];

describe("valid inputs", () => {
  it("FR-011-15 · a well-formed step is accepted", () => {
    expect(validateGnsInputs(valid(), N_TYPES)).toEqual({ ok: true });
  });

  it("FR-011-15 · a single particle with an all-false mask is accepted", () => {
    expect(validateGnsInputs(valid(1), N_TYPES)).toEqual({ ok: true });
  });

  it("FR-011-15 · masked-off index entries that are inside [0, n) are accepted whatever they hold", () => {
    const x = valid();
    for (let i = 0; i < x.neighbourIndex.length; i++)
      if (x.neighbourMask[i] === 0) x.neighbourIndex[i] = (i * 7) % N;
    expect(validateGnsInputs(x, N_TYPES)).toEqual({ ok: true });
  });
});

describe("hostile inputs", () => {
  for (const [label, inputs, name] of HOSTILE) {
    it(`FR-011-15 · ${label}: "rollout stopped — <reason>" naming the argument, no acceleration`, () => {
      const result = validateGnsInputs(inputs, N_TYPES);
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.message.startsWith(PREFIX)).toBe(true);
        expect(result.message.length).toBeGreaterThan(PREFIX.length + 3);
        expect(result.message).toMatch(name);
      }
    });
  }

  it("FR-011-15 · the validator never throws, even for arrays of the wrong type", () => {
    const wrong = withFields({ positions: [1, 2, 3] as unknown as Float32Array });
    expect(() => validateGnsInputs(wrong, N_TYPES)).not.toThrow();
    expect(validateGnsInputs(wrong, N_TYPES).ok).toBe(false);
    expect(() => validateGnsInputs({} as GnsInputs, N_TYPES)).not.toThrow();
    expect(validateGnsInputs({} as GnsInputs, N_TYPES).ok).toBe(false);
  });

  it("FR-011-15 · a failed validation leaves the inputs untouched", () => {
    const x = setAt("positions", 3, Number.NaN);
    const before = Array.from(x.positions).map(String);
    validateGnsInputs(x, N_TYPES);
    expect(Array.from(x.positions).map(String)).toEqual(before);
  });

  it("FR-011-15 · a valid call after a failed one is accepted again", () => {
    expect(validateGnsInputs(setAt("bounds", 0, Number.NaN), N_TYPES).ok).toBe(false);
    expect(validateGnsInputs(valid(), N_TYPES)).toEqual({ ok: true });
  });
});
