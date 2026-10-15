// T-013-030 · FR-013-38 · P-013-15 · SC-013-03 · the TypeScript dust worker against the Python goldens at all 41 slider levels.
//
// Oracle: the golden frames `__fixtures__/dust-golden-{1,2,3}.json`, written by the independent reference in `tests/_sensor_kit/golden_dust.py` (the
// dust rule of FR-013-11 to FR-013-14 from the spec text, the MurmurHash3 reference, a hand-written quantiser and payload packer). Each golden holds a
// baked slider header and payload (schema DC-013-05: 20 bytes per return) and, for every level and for maxReturns 1 and 2, the expected keep/drop
// string, dust-return mask, dust count, r_edge values, uint8 display intensities and (at six levels) the attenuated intensities in full.
// Parity class (spec section 7): decisions, dust-return counts and r_edge values exactly equal; intensities rtol 1e-12; display intensities equal.
//
// Expected API (module `web/src/engines/sensors/dust-slider.ts`, the worker's pure core; no DOM, no global state):
//   loadSliderAsset(header: unknown, payload: Uint8Array): Promise<SliderFrame>     validates the header (DC-013-05) and the payload (byte count
//        20 x returns, SHA-256 equal to header.payload.sha256, finite non-negative tau_unit) and returns the decoded planes; throws SliderAssetError
//   attenuate(frame: SliderFrame, level: number, options?: { maxReturns?: number }): Attenuated      level an integer 0..40, maxReturns default 1
//   SliderFrame:  { header, count: number, tauUnit: Float32Array, rEdge: Float32Array, hash: Uint32Array, intensityCode: Uint8Array, classCode: Uint8Array,
//                   x: Uint16Array, y: Uint16Array, z: Uint16Array }
//   Attenuated:   { kept: Uint8Array (1 = kept, per clean return), emit: Uint8Array (1 = a dust return is added for this return's beam),
//                   dustCount: number, dustREdge: Float64Array (r_edge of each emitted dust return, in return order),
//                   intensity: Float64Array (I0 code x exp(-2 tau) for every return), display: Uint8Array (floor(intensity + 0.5) clipped to 255),
//                   dustDisplay: number (floor(255 x dust_return_intensity + 0.5)) }
//   tau = header.k[level] x tauUnit[i] in float64; u = hash[i] / 2^32; classCode 0 is retro (header.material_codes.retro), any other clean code is diffuse;
//   the rule constants are read from header.rule.

import { describe, expect, it } from "vitest";
import golden1 from "./__fixtures__/dust-golden-1.json";
import golden2 from "./__fixtures__/dust-golden-2.json";
import golden3 from "./__fixtures__/dust-golden-3.json";
import { attenuate, loadSliderAsset } from "./dust-slider";

interface Level {
  level: number;
  kept: string;
  emit: string;
  dust_count: number;
  r_edge: number[];
  display: number[];
  dust_display: number;
  intensity?: number[];
}
interface Golden {
  header: unknown;
  payload_b64: string;
  expected: { max_returns_1: Level[]; max_returns_2: Level[] };
}

const GOLDENS: [string, Golden][] = [
  ["golden 1", golden1 as unknown as Golden],
  ["golden 2", golden2 as unknown as Golden],
  ["golden 3", golden3 as unknown as Golden],
];

const decode = (b64: string): Uint8Array => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const bits = (a: Uint8Array): string => Array.from(a, (v) => (v ? "1" : "0")).join("");

describe("dust slider parity with the Python goldens", () => {
  it("P-013-15 · there are at least three golden frames, each with 41 levels and both max-returns variants", () => {
    expect(GOLDENS.length).toBeGreaterThanOrEqual(3);
    for (const [, g] of GOLDENS) {
      expect(g.expected.max_returns_1).toHaveLength(41);
      expect(g.expected.max_returns_2).toHaveLength(41);
    }
  });

  for (const [name, g] of GOLDENS) {
    for (const maxReturns of [1, 2] as const) {
      it(`P-013-15 · ${name}: keep/drop, dust returns, r_edge and display intensities are identical at all 41 levels (maxReturns ${maxReturns})`, async () => {
        const frame = await loadSliderAsset(g.header, decode(g.payload_b64));
        const expected = maxReturns === 1 ? g.expected.max_returns_1 : g.expected.max_returns_2;
        for (const lv of expected) {
          const out = attenuate(frame, lv.level, { maxReturns });
          expect(bits(out.kept), `kept at level ${lv.level}`).toBe(lv.kept);
          expect(bits(out.emit), `emit at level ${lv.level}`).toBe(lv.emit);
          expect(out.dustCount).toBe(lv.dust_count);
          expect(Array.from(out.dustREdge)).toEqual(lv.r_edge); // float32 values widened: exactly equal
          const shown: number[] = [];
          out.kept.forEach((k, i) => {
            if (k) shown.push(out.display[i] as number);
          });
          expect(shown, `display at level ${lv.level}`).toEqual(lv.display);
          expect(out.dustDisplay).toBe(lv.dust_display);
        }
      });
    }

    it(`FR-013-38 · ${name}: the attenuated intensities equal I0 exp(-2 tau) within rtol 1e-12 at the stored levels`, async () => {
      const frame = await loadSliderAsset(g.header, decode(g.payload_b64));
      let checked = 0;
      for (const lv of g.expected.max_returns_1) {
        if (!lv.intensity) continue;
        const out = attenuate(frame, lv.level);
        const got: number[] = [];
        out.kept.forEach((k, i) => {
          if (k) got.push(out.intensity[i] as number);
        });
        expect(got).toHaveLength(lv.intensity.length);
        got.forEach((v, i) => {
          const want = lv.intensity?.[i] as number;
          expect(Math.abs(v - want)).toBeLessThanOrEqual(1e-12 * Math.max(Math.abs(want), 1e-300));
        });
        checked++;
      }
      expect(checked).toBeGreaterThanOrEqual(5);
    });
  }

  it("FR-013-38 · level 0 (T1 = 1.0) keeps every return with its clean intensity and adds no dust return", async () => {
    const frame = await loadSliderAsset(golden1.header, decode(golden1.payload_b64));
    const out = attenuate(frame, 0, { maxReturns: 2 });
    expect(out.kept.every((k) => k === 1)).toBe(true);
    expect(out.dustCount).toBe(0);
    expect(Array.from(out.display)).toEqual(Array.from(frame.intensityCode));
  });

  it("FR-013-38 · the same level twice gives the same result (a pure function of the frame and the level)", async () => {
    const frame = await loadSliderAsset(golden2.header, decode(golden2.payload_b64));
    const a = attenuate(frame, 33, { maxReturns: 2 });
    attenuate(frame, 12); // an interleaved call does not leak state
    const b = attenuate(frame, 33, { maxReturns: 2 });
    expect(bits(b.kept)).toBe(bits(a.kept));
    expect(Array.from(b.intensity)).toEqual(Array.from(a.intensity));
    expect(Array.from(b.dustREdge)).toEqual(Array.from(a.dustREdge));
  });

  it("FR-013-38 · more dust never keeps a return that a lower level dropped (monotone in the slider)", async () => {
    const frame = await loadSliderAsset(golden3.header, decode(golden3.payload_b64));
    let previous = attenuate(frame, 0).kept;
    for (let level = 1; level <= 40; level++) {
      const now = attenuate(frame, level).kept;
      now.forEach((k, i) => {
        if (k) expect(previous[i]).toBe(1);
      });
      previous = now;
    }
  });
});
