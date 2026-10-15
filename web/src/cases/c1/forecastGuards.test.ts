// T-010-028 [red] · FR-010-29: hostile forecaster contexts in the C1 tab (the Python side is tests/pipeline/test_t_010_028_window_guards.py).
//
// Oracles (independent of the code under test): one context per class of the requirement, built by hand from DC-010-05 (the
// forecaster IO description: input `context` float32 shape [1, 2, 128], channel 0 the scaled inverse velocity, channel 1 the mask): a
// length other than 128, a shape other than [1, 2, 128], a dtype other than float32, a non-finite value, and a context with no
// positive velocity at all (a mask channel that is all zero: every block is masked). Each must give the message
// "no forecast — <reason>" (the em dash is part of the string of the spec) and no TTF; the reason names the offending property
// (length, shape, dtype, non-finite, positive velocity). A valid context gives ok. Nothing is thrown, whatever the input.
//
// Expected API (module `web/src/cases/c1/forecastGuards.ts`):
//   interface ForecastContext { data: ArrayLike<number>; shape: number[]; dtype: string }
//   validateForecastContext(ctx: ForecastContext): { ok: true } | { ok: false; message: string }
//     message = "no forecast — " + reason; the reason contains one of "length", "shape", "dtype", "non-finite" or "positive velocity".
import { describe, expect, it } from "vitest";
import { type ForecastContext, validateForecastContext } from "./forecastGuards";

const PREFIX = "no forecast — ";

function valid(): ForecastContext {
  const data = new Float32Array(2 * 128);
  for (let i = 0; i < 128; i++) {
    data[i] = 1 + 0.001 * i; // channel 0: scaled inverse velocity
    data[128 + i] = 1; // channel 1: mask, every block has data
  }
  return { data, shape: [1, 2, 128], dtype: "float32" };
}

function reasonOf(result: { ok: boolean; message?: string }): string {
  expect(result.ok).toBe(false);
  expect(result.message?.startsWith(PREFIX)).toBe(true);
  return (result.message ?? "").slice(PREFIX.length);
}

describe("C1 forecaster context guards", () => {
  it("FR-010-29 · a valid [1, 2, 128] float32 context is accepted", () => {
    expect(validateForecastContext(valid())).toEqual({ ok: true });
  });

  it.each([127, 129, 0, 256, 1])(
    "FR-010-29 · a context length of %i (not 128) gives no forecast naming the length",
    (n) => {
      const ctx = { data: new Float32Array(2 * n), shape: [1, 2, n], dtype: "float32" };
      expect(reasonOf(validateForecastContext(ctx))).toMatch(/length/);
    },
  );

  it.each([[[2, 128]], [[1, 128]], [[1, 3, 128]], [[2, 2, 128]], [[1, 2, 128, 1]], [[]]])(
    "FR-010-29 · the shape %j differs from the IO description",
    (shape) => {
      const ctx = { ...valid(), shape: shape as number[] };
      expect(reasonOf(validateForecastContext(ctx))).toMatch(/shape|length/);
    },
  );

  it("FR-010-29 · a data array whose size does not match the shape is refused", () => {
    expect(reasonOf(validateForecastContext({ ...valid(), data: new Float32Array(2 * 128 - 1) }))).toMatch(
      /length|shape/,
    );
  });

  it.each(["float64", "int32", "uint8", "float16", "", "string"])(
    "FR-010-29 · the dtype %s is not float32",
    (dtype) => {
      expect(reasonOf(validateForecastContext({ ...valid(), dtype }))).toMatch(/dtype/);
    },
  );

  it.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
    "FR-010-29 · a non-finite value (%s) is refused",
    (bad) => {
      const ctx = valid();
      (ctx.data as Float32Array)[37] = bad;
      expect(reasonOf(validateForecastContext(ctx))).toMatch(/non-finite/);
      const inMask = valid();
      (inMask.data as Float32Array)[128 + 5] = bad;
      expect(reasonOf(validateForecastContext(inMask))).toMatch(/non-finite/);
    },
  );

  it("FR-010-29 · a context with no positive velocity at all (mask channel all zero) gives no forecast", () => {
    const ctx = valid();
    (ctx.data as Float32Array).fill(0, 128); // every block masked
    expect(reasonOf(validateForecastContext(ctx))).toMatch(/positive velocity/);
  });

  it("FR-010-29 · one valid block is enough to forecast", () => {
    const ctx = valid();
    const d = ctx.data as Float32Array;
    d.fill(0, 128);
    d[128 + 60] = 1;
    expect(validateForecastContext(ctx)).toEqual({ ok: true });
  });

  it("FR-010-29 · the guard never throws, whatever it is given", () => {
    const weird = [
      { data: [], shape: [], dtype: "float32" },
      { data: [1, 2, 3], shape: [1, 2, 128], dtype: "float32" },
      { data: null as unknown as number[], shape: [1, 2, 128], dtype: "float32" },
      { data: new Float32Array(256), shape: null as unknown as number[], dtype: "float32" },
    ];
    for (const ctx of weird) {
      const r = validateForecastContext(ctx as ForecastContext);
      expect(r.ok).toBe(false);
    }
  });
});
