// T-020-010 [red] · the numerical half of the chart component: FR-020-15 (compute on the full data, draw a min/max-per-pixel-column decimation, series in typed arrays), FR-020-12 (no hex colour literal in the chart sources),
// P-020-04, P-020-05, P-020-06 (decimation) and P-020-07, P-020-08, P-020-09 (view transform: zoom about the cursor, zoom out and in, read-out round trip). The browser half (zoom, pan, read-out, keys, data table, theme,
// WebGL contexts) is web/e2e/t_020_010_chart.spec.ts.
//
// Expected API (web/src/charts/):
//   decimate.ts       decimate(y: ArrayLike<number>, columns: number): Uint32Array
//                     the indices of the samples to draw: the series is cut into `columns` consecutive index ranges, range j = [floor(j n / columns), floor((j + 1) n / columns)); when n <= 2 columns every index is kept (the output
//                     equals the input); otherwise each range keeps the index of its minimum and the index of its maximum (the lowest index among equal values), NaN samples are ignored when choosing (a range that is all NaN keeps its
//                     first index); the result is strictly increasing; RangeError naming `columns` unless it is an integer >= 1.
//   viewTransform.ts  makeView({ x: { min, max, scale }, y: { min, max, scale }, width, height }): View, with scale "linear" | "log" (log needs min > 0) and the size in CSS pixels of the plot area (the screen y axis points down);
//                     toData(view, px, py): { x, y }; toScreen(view, x, y): { px, py }; zoomAt(view, factor, px, py): View (factor > 1 zooms in about the screen point, the range of an axis is divided by factor, in log space for a log axis);
//                     pan(view, dpx, dpy): View (the content follows the pointer); a View has the fields of its argument: x and y { min, max, scale }, width and height; RangeError naming the argument for a factor that is not finite and > 0, a non-finite size, a log axis with min <= 0, min >= max.
//   series.ts         makeSeries(x: ArrayLike<number>, y: ArrayLike<number>): { x: Float64Array; y: Float64Array; n: number } (copies into Float64Array; x finite and non-decreasing; y may hold NaN for a gap; equal lengths, n >= 1),
//                     nearestIndex(series, x): number, the index of the sample whose x is nearest (the lower index on a tie) found on the FULL data by binary search.
// Oracles: the definition of the decimation written out by hand (a reference loop in this file), the algebra of the view transform (affine in the plotted coordinate), hand-calculated screen positions, regular-expression scan of
// the sources for FR-020-12.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import { decimate } from "~/charts/decimate";
import { makeSeries, nearestIndex } from "~/charts/series";
import { makeView, pan, toData, toScreen, zoomAt } from "~/charts/viewTransform";

/** The definition of FR-020-15 and P-020-04, written out by hand: per range, the lowest index of the minimum and of the maximum. */
function reference(y: ArrayLike<number>, columns: number): number[] {
  const n = y.length;
  if (n <= 2 * columns) return Array.from({ length: n }, (_, i) => i);
  const out = new Set<number>();
  for (let j = 0; j < columns; j++) {
    const a = Math.floor((j * n) / columns);
    const b = Math.floor(((j + 1) * n) / columns);
    let lo = -1;
    let hi = -1;
    for (let i = a; i < b; i++) {
      const v = y[i] as number;
      if (Number.isNaN(v)) continue;
      if (lo < 0 || v < (y[lo] as number)) lo = i;
      if (hi < 0 || v > (y[hi] as number)) hi = i;
    }
    if (lo < 0) out.add(a);
    else {
      out.add(lo);
      out.add(hi);
    }
  }
  return [...out].sort((p, q) => p - q);
}

const arrays = (maxLen: number) =>
  fc.array(
    fc.oneof(
      fc.integer({ min: -1000, max: 1000 }),
      fc.double({ min: -1e6, max: 1e6, noNaN: true }),
      fc.constantFrom(1e300, -1e300, 0, -0),
    ),
    { minLength: 1, maxLength: maxLen },
  );

describe("decimation (FR-020-15)", () => {
  it("FR-020-15 · hand case: 8 samples in 2 columns keep the extremes of each half: [1, 5, 2, 0 | 3, 9, 9, 4] gives indices 1, 3, 4, 5", () => {
    // n = 8 > 2 * 2 = 4; column 0 = indices 0..3 (min 0 at 3, max 5 at 1), column 1 = indices 4..7 (min 3 at 4, max 9 first at 5)
    const y = Float64Array.from([1, 5, 2, 0, 3, 9, 9, 4]);
    expect(Array.from(decimate(y, 2))).toEqual([1, 3, 4, 5]);
  });

  it("FR-020-15 · a series of at most 2 x columns is returned whole, equal values included", () => {
    expect(Array.from(decimate(Float64Array.from([3, 3, 3, 3]), 2))).toEqual([0, 1, 2, 3]);
    expect(Array.from(decimate(Float64Array.from([7]), 5))).toEqual([0]);
    expect(Array.from(decimate(new Float64Array(0), 5))).toEqual([]);
  });

  it("FR-020-15 · the result is a Uint32Array of strictly increasing indices, and its length is at most 2 x columns", () => {
    const y = Float64Array.from({ length: 10_000 }, (_, i) => Math.sin(i / 7) * 100);
    const out = decimate(y, 100);
    expect(out).toBeInstanceOf(Uint32Array);
    expect(out.length).toBeLessThanOrEqual(200);
    for (let i = 1; i < out.length; i++) expect(out[i] as number).toBeGreaterThan(out[i - 1] as number);
  });

  it("FR-020-15 · one million samples decimate to at most 2 x 4096 indices and keep the global extremes (a needle in the middle survives)", () => {
    const n = 1_000_000;
    const y = new Float64Array(n);
    let s = 12345;
    for (let i = 0; i < n; i++) {
      s = (s * 1103515245 + 12345) % 2147483648;
      y[i] = (s / 2147483648) * 2 - 1;
    }
    y[433_333] = 1e300;
    y[777_777] = -1e300;
    const out = decimate(y, 4096);
    expect(out.length).toBeLessThanOrEqual(8192);
    expect(Array.from(out)).toContain(433_333);
    expect(Array.from(out)).toContain(777_777);
  });

  it("FR-020-15 · NaN samples (gaps) are never chosen as an extreme, and a column that is all NaN keeps its first index", () => {
    const y = Float64Array.from({ length: 40 }, (_, i) => (i >= 10 && i < 20 ? Number.NaN : i % 7));
    const out = Array.from(decimate(y, 4));
    for (const i of out) if (!(i >= 10 && i < 20)) expect(Number.isNaN(y[i] as number)).toBe(false);
    expect(
      Array.from(
        decimate(
          Float64Array.from([Number.NaN, Number.NaN, Number.NaN, Number.NaN, Number.NaN, Number.NaN]),
          1,
        ),
      ),
    ).toEqual([0]);
  });

  for (const bad of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY, "4" as never]) {
    it(`FR-020-15 · columns = ${String(bad)} throws a RangeError naming columns`, () => {
      expect(() => decimate(Float64Array.from([1, 2, 3]), bad as number)).toThrow(RangeError);
      expect(() => decimate(Float64Array.from([1, 2, 3]), bad as number)).toThrow(/columns/);
    });
  }

  it("P-020-04 · decimation keeps extremes: for every column its minimum and maximum, and the global ones, appear in the output exactly", () => {
    fc.assert(
      fc.property(arrays(20_000), fc.integer({ min: 1, max: 4096 }), (values, columns) => {
        const y = Float64Array.from(values);
        const out = Array.from(decimate(y, columns));
        expect(out).toEqual(reference(y, columns));
        const n = y.length;
        if (n > 2 * columns) {
          for (let j = 0; j < columns; j++) {
            const a = Math.floor((j * n) / columns);
            const b = Math.floor(((j + 1) * n) / columns);
            let mn = Number.POSITIVE_INFINITY;
            let mx = Number.NEGATIVE_INFINITY;
            for (let i = a; i < b; i++) {
              mn = Math.min(mn, y[i] as number);
              mx = Math.max(mx, y[i] as number);
            }
            const kept = out.filter((i) => i >= a && i < b).map((i) => y[i] as number);
            expect(kept).toContain(mn);
            expect(kept).toContain(mx);
          }
        }
        expect(out.map((i) => y[i] as number)).toContain(Math.min(...y));
        expect(out.map((i) => y[i] as number)).toContain(Math.max(...y));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-05 · idempotence: with n <= 2 x columns the output equals the input, and decimating an output again changes nothing", () => {
    fc.assert(
      fc.property(arrays(20_000), fc.integer({ min: 1, max: 4096 }), (values, columns) => {
        const y = Float64Array.from(values);
        const once = decimate(y, columns);
        if (y.length <= 2 * columns) expect(Array.from(once)).toEqual(Array.from(y, (_, i) => i));
        const picked = Float64Array.from(Array.from(once, (i) => y[i] as number));
        expect(Array.from(decimate(picked, columns))).toEqual(Array.from(picked, (_, i) => i));
      }),
      { numRuns: 200 },
    );
  });

  it("P-020-06 · affine equivariance: decimate(a y + c) selects the same indices as decimate(y) for a > 0, and the indices are strictly increasing", () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: -1000, max: 1000 }), { minLength: 1, maxLength: 5000 }),
        fc.integer({ min: 1, max: 512 }),
        fc.integer({ min: 1, max: 1000 }),
        fc.integer({ min: -1_000_000, max: 1_000_000 }),
        (values, columns, a, c) => {
          const y = Float64Array.from(values);
          const z = Float64Array.from(values, (v) => a * v + c);
          const iy = Array.from(decimate(y, columns));
          expect(Array.from(decimate(z, columns))).toEqual(iy);
          for (let i = 1; i < iy.length; i++) expect(iy[i] as number).toBeGreaterThan(iy[i - 1] as number);
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("series in typed arrays, nearest sample on the full data (FR-020-15)", () => {
  it("FR-020-15 · plain arrays and Float32Array are copied into Float64Array", () => {
    const s = makeSeries([0, 1, 2], new Float32Array([1.5, 2.5, 3.5]));
    expect(s.x).toBeInstanceOf(Float64Array);
    expect(s.y).toBeInstanceOf(Float64Array);
    expect(s.n).toBe(3);
    expect(Array.from(s.y)).toEqual([1.5, 2.5, 3.5]);
    const source = [0, 1, 2];
    const t = makeSeries(source, [1, 2, 3]);
    source[1] = 99;
    expect(t.x[1]).toBe(1);
  });

  it("FR-020-15 · mismatched lengths, empty series, non-finite or decreasing x are rejected with a RangeError naming the argument", () => {
    expect(() => makeSeries([0, 1], [1])).toThrow(RangeError);
    expect(() => makeSeries([], [])).toThrow(RangeError);
    expect(() => makeSeries([0, Number.NaN], [1, 2])).toThrow(/\bx\b/);
    expect(() => makeSeries([0, Number.POSITIVE_INFINITY], [1, 2])).toThrow(/\bx\b/);
    expect(() => makeSeries([0, 2, 1], [1, 2, 3])).toThrow(/\bx\b/);
    expect(makeSeries([0, 1, 2], [1, Number.NaN, 3]).n).toBe(3);
  });

  it("FR-020-15 · nearestIndex searches the full data: x = [0, 2, 4]: 2.9 -> 1, a tie at 3 -> the lower index 1, below the range -> 0, above -> 2", () => {
    const s = makeSeries([0, 2, 4], [10, 20, 30]);
    expect(nearestIndex(s, 2.9)).toBe(1);
    expect(nearestIndex(s, 3)).toBe(1);
    expect(nearestIndex(s, 3.1)).toBe(2);
    expect(nearestIndex(s, -100)).toBe(0);
    expect(nearestIndex(s, 100)).toBe(2);
    expect(nearestIndex(s, 0)).toBe(0);
  });

  it("FR-020-15 · on a million samples the nearest index is exact (it does not use the decimated points)", () => {
    const n = 1_000_000;
    const x = Float64Array.from({ length: n }, (_, i) => i * 0.001);
    const s = makeSeries(x, new Float64Array(n));
    for (const i of [0, 1, 123_456, 654_321, 999_999]) expect(nearestIndex(s, i * 0.001 + 0.0004)).toBe(i);
  });
});

describe("view transform (P-020-07, P-020-08, P-020-09)", () => {
  const linear = () =>
    makeView({
      x: { min: 0, max: 10, scale: "linear" },
      y: { min: 0, max: 100, scale: "linear" },
      width: 500,
      height: 200,
    });
  const logx = () =>
    makeView({
      x: { min: 1, max: 1000, scale: "log" },
      y: { min: 0.1, max: 10, scale: "log" },
      width: 300,
      height: 200,
    });

  it("FR-020-07 · hand case, linear: x in [0, 10] over 500 px and y in [0, 100] over 200 px (screen y down): (250, 100) is (5, 50), (0, 0) is (0, 100), (500, 200) is (10, 0)", () => {
    const v = linear();
    expect(toData(v, 250, 100)).toEqual({ x: 5, y: 50 });
    expect(toData(v, 0, 0)).toEqual({ x: 0, y: 100 });
    expect(toData(v, 500, 200)).toEqual({ x: 10, y: 0 });
    expect(toScreen(v, 2.5, 25)).toEqual({ px: 125, py: 150 });
  });

  it("FR-020-07 · hand case, logarithmic: x in [1, 1000] over 300 px puts 10 at 100 px and 100 at 200 px; y in [0.1, 10] over 200 px puts 1 at py = 100", () => {
    const v = logx();
    const a = toData(v, 100, 100);
    expect(a.x).toBeCloseTo(10, 9);
    expect(a.y).toBeCloseTo(1, 9);
    expect(toData(v, 200, 100).x).toBeCloseTo(100, 8);
    expect(toScreen(v, 10, 1).px).toBeCloseTo(100, 9);
  });

  it("FR-020-07 · zooming in by 2 about the centre halves both ranges; about a corner keeps that corner", () => {
    const v = zoomAt(linear(), 2, 250, 100);
    expect(toData(v, 0, 0)).toEqual({ x: 2.5, y: 75 });
    expect(toData(v, 500, 200)).toEqual({ x: 7.5, y: 25 });
    const c = zoomAt(linear(), 2, 0, 200);
    expect(toData(c, 0, 200)).toEqual({ x: 0, y: 0 });
    expect(toData(c, 500, 0)).toEqual({ x: 5, y: 50 });
  });

  it("FR-020-07 · panning by 50 px to the right moves the content with the pointer: the range shifts by -1 (10 / 500 x 50)", () => {
    const v = pan(linear(), 50, 0);
    expect(toData(v, 0, 0).x).toBeCloseTo(-1, 12);
    expect(toData(v, 500, 0).x).toBeCloseTo(9, 12);
  });

  it("FR-020-07 · invalid factors and views are RangeErrors naming the argument", () => {
    for (const f of [0, -2, Number.NaN, Number.POSITIVE_INFINITY])
      expect(() => zoomAt(linear(), f, 10, 10)).toThrow(/factor/);
    expect(() =>
      makeView({
        x: { min: 0, max: 10, scale: "log" },
        y: { min: 0, max: 1, scale: "linear" },
        width: 10,
        height: 10,
      }),
    ).toThrow(RangeError);
    expect(() =>
      makeView({
        x: { min: 5, max: 5, scale: "linear" },
        y: { min: 0, max: 1, scale: "linear" },
        width: 10,
        height: 10,
      }),
    ).toThrow(RangeError);
    expect(() =>
      makeView({
        x: { min: 0, max: 1, scale: "linear" },
        y: { min: 0, max: 1, scale: "linear" },
        width: Number.NaN,
        height: 10,
      }),
    ).toThrow(/width/);
  });

  const axis = fc.record({
    scale: fc.constantFrom("linear" as const, "log" as const),
    a: fc.double({ min: 1e-3, max: 1e3, noNaN: true }),
    span: fc.double({ min: 1.5, max: 1e3, noNaN: true }),
    offset: fc.double({ min: -1e3, max: 1e3, noNaN: true }),
  });
  const view = fc
    .tuple(axis, axis, fc.integer({ min: 50, max: 2000 }), fc.integer({ min: 50, max: 1200 }))
    .map(([x, y, width, height]) => {
      const mk = (ax: typeof x) =>
        ax.scale === "log"
          ? { min: ax.a, max: ax.a * ax.span, scale: ax.scale }
          : { min: ax.offset, max: ax.offset + ax.span * Math.max(ax.a, 1e-3), scale: ax.scale };
      return makeView({ x: mk(x), y: mk(y), width, height });
    });
  const factor = fc.double({ min: 0.1, max: 10, noNaN: true });

  it("P-020-07 · zooming about the cursor keeps the data point under the cursor at the same screen position (well within 0.5 px)", () => {
    fc.assert(
      fc.property(
        view,
        factor,
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (v, f, u, w) => {
          const px = u * v.width;
          const py = w * v.height;
          const d = toData(v, px, py);
          const s = toScreen(zoomAt(v, f, px, py), d.x, d.y);
          expect(Math.abs(s.px - px)).toBeLessThanOrEqual(1e-6);
          expect(Math.abs(s.py - py)).toBeLessThanOrEqual(1e-6);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-08 · zooming in and then out by the same factor about the same point restores the view (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        view,
        factor,
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (v, f, u, w) => {
          const px = u * v.width;
          const py = w * v.height;
          const back = zoomAt(zoomAt(v, f, px, py), 1 / f, px, py);
          for (const key of ["x", "y"] as const) {
            for (const bound of ["min", "max"] as const) {
              const a = back[key][bound];
              const b = v[key][bound];
              expect(Math.abs(a - b)).toBeLessThanOrEqual(
                1e-12 * Math.max(Math.abs(b), Math.abs(v[key].max - v[key].min), 1e-300),
              );
            }
          }
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-09 · screen to data to screen returns the cursor position, on linear and log axes (well within 0.5 px)", () => {
    fc.assert(
      fc.property(
        view,
        fc.double({ min: 0, max: 1, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (v, u, w) => {
          const px = u * v.width;
          const py = w * v.height;
          const d = toData(v, px, py);
          const s = toScreen(v, d.x, d.y);
          expect(Math.abs(s.px - px)).toBeLessThanOrEqual(1e-6);
          expect(Math.abs(s.py - py)).toBeLessThanOrEqual(1e-6);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-020-07 · panning is undone by panning back", () => {
    fc.assert(
      fc.property(
        view,
        fc.double({ min: -500, max: 500, noNaN: true }),
        fc.double({ min: -500, max: 500, noNaN: true }),
        (v, dx, dy) => {
          const back = pan(pan(v, dx, dy), -dx, -dy);
          for (const key of ["x", "y"] as const) {
            expect(Math.abs(back[key].min - v[key].min)).toBeLessThanOrEqual(
              1e-9 * Math.max(Math.abs(v[key].min), Math.abs(v[key].max - v[key].min)),
            );
            expect(Math.abs(back[key].max - v[key].max)).toBeLessThanOrEqual(
              1e-9 * Math.max(Math.abs(v[key].max), Math.abs(v[key].max - v[key].min)),
            );
          }
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("no hex colour literal in the chart sources (FR-020-12)", () => {
  const dir = resolve(dirname(fileURLToPath(import.meta.url)));
  const sources = (): string[] => {
    const out: string[] = [];
    const walk = (d: string) => {
      for (const name of readdirSync(d)) {
        const p = join(d, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.(ts|tsx|css)$/.test(name) && !/\.test\.|\.spec\./.test(name)) out.push(p);
      }
    };
    walk(dir);
    return out;
  };

  it("FR-020-12 · the chart module has sources (Chart.tsx, decimate.ts, viewTransform.ts, series.ts, colormaps.ts, DataTable.tsx) and none holds a hex colour literal", () => {
    const files = sources();
    const names = files.map((f) => f.slice(dir.length + 1).replace(/\\/g, "/"));
    for (const expected of [
      "Chart.tsx",
      "decimate.ts",
      "viewTransform.ts",
      "series.ts",
      "colormaps.ts",
      "DataTable.tsx",
    ])
      expect(names, expected).toContain(expected);
    for (const f of files) {
      const text = readFileSync(f, "utf8")
        .replace(/\/\/.*$/gm, "")
        .replace(/\/\*[\s\S]*?\*\//g, "");
      const hit = /(^|[^\w&])#[0-9a-fA-F]{3,8}\b/.exec(text);
      expect(hit, `${f} holds the colour literal ${hit?.[0]}`).toBeNull();
    }
  });
});
