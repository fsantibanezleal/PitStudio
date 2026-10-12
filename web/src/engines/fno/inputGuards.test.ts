// T-011-055 [red] · FR-011-40: hostile FNO inputs in the web engine `fno` (the Python side is tests/pipeline/test_t_011_055_fno_input_guards.py).
//
// Oracles (independent of the code under test; plan 011 test strategy FR-011-40: "invalid inputs written in the test"): one input per class of the
// requirement, built here by hand against the DC-011-02 description of the tailings model (`surrogate-io.valid-fno.json`): input shape [1, 5, 64, 64],
// channel order bed_elevation, release_depth, yield_stress, plastic_viscosity, density; a non-finite value; a patch id that is not in the list of the
// published patches. Each must give the message "field not computed — <reason>" (the em dash is part of the string fixed by the spec) and return no
// field; the reason names the offending argument (shape, channels, x, patchId); a valid input gives ok.
//
// Expected API (module `web/src/engines/fno/inputGuards.ts`):
//   interface FnoInputs { x: Float32Array; shape: number[]; channels: string[]; patchId: string }
//   interface FnoDescription { channels: string[]; knownPatches: ReadonlySet<string> }
//   validateFnoInputs(inputs: FnoInputs, io: FnoDescription): { ok: true } | { ok: false; message: string }
//     message = "field not computed — " + a reason naming `shape`, `channels`, `x` (non-finite value) or `patchId`; never throws.
import { describe, expect, it } from "vitest";
import { type FnoDescription, type FnoInputs, validateFnoInputs } from "./inputGuards";

const CHANNELS = ["bed_elevation", "release_depth", "yield_stress", "plastic_viscosity", "density"];
const IO: FnoDescription = { channels: CHANNELS, knownPatches: new Set(["p00", "p07", "p63"]) };
const PREFIX = "field not computed — ";
const SIZE = 5 * 64 * 64;

function valid(): FnoInputs {
  return {
    x: Float32Array.from({ length: SIZE }, (_, i) => Math.sin(i) * 0.5),
    shape: [1, 5, 64, 64],
    channels: [...CHANNELS],
    patchId: "p07",
  };
}

function withFields(fields: Partial<FnoInputs>): FnoInputs {
  return { ...valid(), ...fields };
}

function setAt(index: number, value: number): FnoInputs {
  const x = valid();
  x.x[index] = value;
  return x;
}

const HOSTILE: [string, FnoInputs, string][] = [
  ["batch of two", withFields({ shape: [2, 5, 64, 64] }), "shape"],
  ["four channels", withFields({ shape: [1, 4, 64, 64] }), "shape"],
  ["six channels", withFields({ shape: [1, 6, 64, 64] }), "shape"],
  ["width 32", withFields({ shape: [1, 5, 64, 32] }), "shape"],
  ["grid 128", withFields({ shape: [1, 5, 128, 128] }), "shape"],
  ["no batch axis", withFields({ shape: [5, 64, 64] }), "shape"],
  ["extra axis", withFields({ shape: [1, 5, 64, 64, 1] }), "shape"],
  ["empty shape", withFields({ shape: [] }), "shape"],
  ["fractional dimension", withFields({ shape: [1, 5, 64, 64.5] }), "shape"],
  ["data shorter than the shape", withFields({ x: new Float32Array(SIZE - 1) }), "shape"],
  ["data longer than the shape", withFields({ x: new Float32Array(SIZE + 1) }), "shape"],
  ["empty data", withFields({ x: new Float32Array(0) }), "shape"],
  [
    "swapped channels",
    withFields({ channels: [CHANNELS[1] as string, CHANNELS[0] as string, ...CHANNELS.slice(2)] }),
    "channels",
  ],
  ["reversed channels", withFields({ channels: [...CHANNELS].reverse() }), "channels"],
  ["missing channel", withFields({ channels: CHANNELS.slice(0, 4) }), "channels"],
  ["extra channel", withFields({ channels: [...CHANNELS, "wind_speed"] }), "channels"],
  ["unknown channel", withFields({ channels: [...CHANNELS.slice(0, 4), "pressure"] }), "channels"],
  ["upper case channel", withFields({ channels: ["Bed_elevation", ...CHANNELS.slice(1)] }), "channels"],
  ["no channel names", withFields({ channels: [] }), "channels"],
  ["nan", setAt(1234, Number.NaN), "x"],
  ["infinity", setAt(0, Number.POSITIVE_INFINITY), "x"],
  ["minus infinity", setAt(SIZE - 1, Number.NEGATIVE_INFINITY), "x"],
  ["unknown patch", withFields({ patchId: "p99" }), "patchId"],
  ["empty patch", withFields({ patchId: "" }), "patchId"],
  ["unicode patch", withFields({ patchId: "pátch-ñ" }), "patchId"],
  ["upper case patch", withFields({ patchId: "P07" }), "patchId"],
  ["injection patch", withFields({ patchId: "p07; rm -rf /" }), "patchId"],
  ["prototype patch", withFields({ patchId: "__proto__" }), "patchId"],
];

describe("valid inputs", () => {
  it("FR-011-40 · a well-formed field is accepted", () => {
    expect(validateFnoInputs(valid(), IO)).toEqual({ ok: true });
  });

  for (const patch of IO.knownPatches) {
    it(`FR-011-40 · the published patch ${patch} is accepted`, () => {
      expect(validateFnoInputs(withFields({ patchId: patch }), IO)).toEqual({ ok: true });
    });
  }
});

describe("hostile inputs", () => {
  for (const [label, inputs, name] of HOSTILE) {
    it(`FR-011-40 · ${label}: "field not computed — <reason>" naming ${name}, no field`, () => {
      const result = validateFnoInputs(inputs, IO);
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.message.startsWith(PREFIX)).toBe(true);
        expect(result.message.length).toBeGreaterThan(PREFIX.length + 3);
        expect(result.message).toContain(name);
      }
    });
  }

  it("FR-011-40 · the validator never throws, even for malformed objects", () => {
    expect(() => validateFnoInputs({} as FnoInputs, IO)).not.toThrow();
    expect(validateFnoInputs({} as FnoInputs, IO).ok).toBe(false);
    const wrong = withFields({ x: [1, 2, 3] as unknown as Float32Array });
    expect(() => validateFnoInputs(wrong, IO)).not.toThrow();
    expect(validateFnoInputs(wrong, IO).ok).toBe(false);
  });

  it("FR-011-40 · a failed validation leaves the inputs untouched and the next valid one is accepted", () => {
    const bad = setAt(7, Number.NaN);
    const before = Array.from(bad.x).map(String);
    expect(validateFnoInputs(bad, IO).ok).toBe(false);
    expect(Array.from(bad.x).map(String)).toEqual(before);
    expect(validateFnoInputs(valid(), IO)).toEqual({ ok: true });
  });
});
