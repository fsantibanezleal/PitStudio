// T-018-072 [red] · FR-018-51 (survey cut/fill volume engine equals its numpy reference, with exactly rounded summation), P-018-52 (additivity and
// prism volume), P-018-53 (antisymmetry), P-018-54 (linearity) for the `volume` engine of spec 018 (spec 017: FR-017-30, FR-017-33, FR-017-47, FR-017-48).
//
// Expected API (module `~/engines/volume`, file web/src/engines/volume/index.ts). `cut_fill(args)` takes the `args` of its DC-018-02 request
// (specs/018-web-cases/contracts/engines/volume.schema.json) except that the two artefact references `before` and `after` are replaced by the
// DEM buffers the host loaded for them: `before` and `after` are row-major arrays of rows x cols heights (Float32Array, Float64Array or number[];
// NaN marks no data), and returns the `result` object, snake_case:
//     cut_fill({ before, after, rows, cols, cell_size_m, origin_m, polygon_m, rmse_before_m, rmse_after_m })
//       -> { fill_m3, cut_m3, net_m3, valid_cells, nodata_cells, nodata_fraction, bound_uncorrelated_m3, bound_correlated_m3 }
//   V_fill = A_c sum max(z1 - z0, 0), V_cut = A_c sum max(z0 - z1, 0), V_net = V_fill - V_cut over the cells whose centre lies in the polygon and
//   whose heights are both valid, summed with exactly rounded summation (FR-017-30: the browser mirrors Python's math.fsum); nodata_cells counts the cells
//   of the polygon with a NaN in either epoch, nodata_fraction = nodata / (valid + nodata); the bounds are A_c sqrt(N) sqrt(s0^2 + s1^2) (uncorrelated) and
//   A_c N sqrt(s0^2 + s1^2) (fully correlated), N = valid_cells (FR-017-33).
//   Grid geometry is an assumption of these tests (flagged in the report): `origin_m` is a corner of the grid and cell centres lie half a cell inside it;
//   the tests that need it use polygons that cover the grid under every reading, or split it with a line a quarter cell off any centre.
//   Errors (FR-017-47, FR-017-48; FR-018-38 typed errors): a polygon with fewer than 3 vertices E_SCHEMA, more than 10^4 vertices E_SIZE, a self-intersecting
//   one, one entirely outside the grid, no valid cell inside it, a cell size <= 0 or a negative RMSE E_RANGE; a buffer whose length is not rows x cols E_SCHEMA;
//   more than 2048 rows or columns E_SIZE.
//
// Oracles (independent of the code under test): hand calculations on dyadic heights below (4 x 4 grid, 2 m cells); the closed forms of FR-017-30 and
// FR-017-33; math.fsum's classical test [1e16, 1, 1] (exact 1e16 + 2, naive summation gives 1e16); the metamorphic relations of spec 018 section 4;
// the parity fixtures of the reference (numpy DEM differencing, spec 017), DC-018-04, through web/src/test-support/parity-fixtures.ts.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as volume from "~/engines/volume";
import { expectAnalyticalParity } from "~/test-support/parity-fixtures";

interface Result {
  fill_m3: number;
  cut_m3: number;
  net_m3: number;
  valid_cells: number;
  nodata_cells: number;
  nodata_fraction: number;
  bound_uncorrelated_m3: number;
  bound_correlated_m3: number;
}
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}
const close = (a: number, b: number, rtol: number) => Math.abs(a - b) <= rtol * Math.abs(b);

/** A square polygon that covers the whole grid whichever corner `origin_m` is and whichever way rows run. */
function coverAll(
  rows: number,
  cols: number,
  cell: number,
  origin: [number, number],
): Array<[number, number]> {
  const L = (Math.max(rows, cols) + 3) * cell;
  const [x0, y0] = origin;
  return [
    [x0 - L, y0 - L],
    [x0 + L, y0 - L],
    [x0 + L, y0 + L],
    [x0 - L, y0 + L],
  ];
}
const run = (
  b: ArrayLike<number>,
  a: ArrayLike<number>,
  rows: number,
  cols: number,
  over: Record<string, unknown> = {},
): Result => {
  const cell = (over.cell_size_m as number | undefined) ?? 2;
  const origin = (over.origin_m as [number, number] | undefined) ?? [0, 0];
  return volume.cut_fill({
    before: b,
    after: a,
    rows,
    cols,
    cell_size_m: cell,
    origin_m: origin,
    polygon_m: coverAll(rows, cols, cell, origin),
    rmse_before_m: 0.05,
    rmse_after_m: 0.12,
    ...over,
  } as never) as Result;
};

describe("hand-calculated volumes (FR-018-51)", () => {
  // 4 x 4 grid, 2 m cells (A_c = 4 m2), before = 100 m, after = 100.5 on the left half (+0.5 m) and 99.75 on the right half (-0.25 m)
  const before = new Float64Array(16).fill(100);
  const after = Float64Array.from({ length: 16 }, (_, i) => (i % 4 < 2 ? 100.5 : 99.75));

  it("FR-018-51 · fill = 4 x 8 x 0.5 = 16 m3, cut = 4 x 8 x 0.25 = 8 m3, net = 8 m3, 16 valid cells and no nodata", () => {
    const r = run(before, after, 4, 4);
    expect(r.fill_m3).toBe(16);
    expect(r.cut_m3).toBe(8);
    expect(r.net_m3).toBe(8);
    expect(r.valid_cells).toBe(16);
    expect(r.nodata_cells).toBe(0);
    expect(r.nodata_fraction).toBe(0);
  });

  it("FR-018-51 · Float32Array buffers, as the host loads them from the DEM assets, give the same exact volumes", () => {
    const r = run(Float32Array.from(before), Float32Array.from(after), 4, 4);
    expect([r.fill_m3, r.cut_m3, r.net_m3]).toEqual([16, 8, 8]);
  });

  it("FR-018-51 · two no-data cells (one per half, in the 'after' epoch) are excluded and counted: fill 14, cut 7, net 7, 14 valid, 2 nodata, fraction 0.125", () => {
    const a = Float64Array.from(after);
    a[0] = Number.NaN;
    a[3] = Number.NaN;
    const r = run(before, a, 4, 4);
    expect([r.fill_m3, r.cut_m3, r.net_m3]).toEqual([14, 7, 7]);
    expect(r.valid_cells).toBe(14);
    expect(r.nodata_cells).toBe(2);
    expect(r.nodata_fraction).toBe(0.125);
  });

  it("FR-018-51 · a no-data cell in the 'before' epoch is excluded the same way", () => {
    const b = Float64Array.from(before);
    b[5] = Number.NaN;
    const r = run(b, after, 4, 4);
    expect(r.valid_cells).toBe(15);
    expect(r.nodata_cells).toBe(1);
    expect(r.fill_m3).toBe(4 * 0.5 * 7); // the NaN cell (row 1, column 1) was a fill cell
    expect(r.cut_m3).toBe(8);
  });

  it("FR-017-33 · the two uncertainty bounds are A_c sqrt(N) sqrt(s0^2 + s1^2) and A_c N sqrt(s0^2 + s1^2) (rtol 1e-12)", () => {
    const r = run(before, after, 4, 4);
    const sigma = Math.sqrt(0.05 ** 2 + 0.12 ** 2);
    expect(close(r.bound_uncorrelated_m3, 4 * Math.sqrt(16) * sigma, 1e-12)).toBe(true);
    expect(close(r.bound_correlated_m3, 4 * 16 * sigma, 1e-12)).toBe(true);
    expect(close(r.bound_uncorrelated_m3, 2.08, 1e-12)).toBe(true);
    expect(close(r.bound_correlated_m3, 8.32, 1e-12)).toBe(true);
    const a = Float64Array.from(after);
    a[0] = Number.NaN;
    a[3] = Number.NaN;
    const r14 = run(before, a, 4, 4);
    expect(close(r14.bound_uncorrelated_m3, 4 * Math.sqrt(14) * sigma, 1e-12)).toBe(true);
    expect(close(r14.bound_correlated_m3, 4 * 14 * sigma, 1e-12)).toBe(true);
  });

  it("FR-017-30 · the sums are exactly rounded (math.fsum): heights 1e16, 1, 1 of fill give 10000000000000002, which naive left-to-right summation misses", () => {
    const r = run([0, 0, 0, 0], [1e16, 1, 1, 0], 2, 2, { cell_size_m: 1 });
    expect(r.fill_m3).toBe(10000000000000002);
    expect(r.cut_m3).toBe(0);
  });

  it("FR-017-30 · the cell size scales the volumes by its square (cell 4 m instead of 2 m gives 4 times the volume)", () => {
    const r = run(before, after, 4, 4, { cell_size_m: 4 });
    expect([r.fill_m3, r.cut_m3, r.net_m3]).toEqual([64, 32, 32]);
  });

  it("FR-017-30 · a polygon covering only the cells that are fill gives no cut: the left half, selected by a line a quarter cell off every centre", () => {
    // cut the grid at x = origin + 2.25 cells; the cells on the left of the line are columns 0..1 under either reading of `origin_m`, up to a half-cell shift
    const polygon: Array<[number, number]> = [
      [-30, -30],
      [2 * 2 + 0.5, -30],
      [2 * 2 + 0.5, 30],
      [-30, 30],
    ];
    const left = volume.cut_fill({
      before,
      after,
      rows: 4,
      cols: 4,
      cell_size_m: 2,
      origin_m: [0, 0],
      polygon_m: polygon,
      rmse_before_m: 0,
      rmse_after_m: 0,
    } as never) as Result;
    expect(left.cut_m3).toBe(0);
    expect(left.fill_m3).toBe(16); // 8 cells x 0.5 m x 4 m2
  });
});

describe("hostile surfaces and polygons (FR-017-47, FR-017-48, FR-018-38)", () => {
  const b = new Float64Array(16).fill(100);
  const a = new Float64Array(16).fill(101);
  const base = {
    before: b,
    after: a,
    rows: 4,
    cols: 4,
    cell_size_m: 2,
    origin_m: [0, 0],
    polygon_m: coverAll(4, 4, 2, [0, 0]),
    rmse_before_m: 0.05,
    rmse_after_m: 0.12,
  };
  const call = (over: Record<string, unknown>) => () => volume.cut_fill({ ...base, ...over } as never);

  it("FR-018-51 · the base call is valid (guard of the hostile cases below)", () => {
    expect(codeOf(call({}))).toBeNull();
  });

  it("FR-017-47 · fewer than 3 vertices is E_SCHEMA, more than 10^4 vertices E_SIZE", () => {
    expect(
      codeOf(
        call({
          polygon_m: [
            [0, 0],
            [1, 1],
          ],
        }),
      ),
    ).toMatch(/E_SCHEMA|E_RANGE/);
    const many = Array.from({ length: 10001 }, (_, i) => [
      Math.cos((2 * Math.PI * i) / 10001) * 20,
      Math.sin((2 * Math.PI * i) / 10001) * 20,
    ]);
    expect(codeOf(call({ polygon_m: many }))).toBe("E_SIZE");
  });

  it("FR-017-47 · a self-intersecting polygon (a bow tie) and a polygon entirely outside the grid are E_RANGE", () => {
    expect(
      codeOf(
        call({
          polygon_m: [
            [-20, -20],
            [20, 20],
            [20, -20],
            [-20, 20],
          ],
        }),
      ),
    ).toBe("E_RANGE");
    expect(
      codeOf(
        call({
          polygon_m: [
            [1000, 1000],
            [1010, 1000],
            [1010, 1010],
            [1000, 1010],
          ],
        }),
      ),
    ).toBe("E_RANGE");
  });

  it("FR-017-47 · a non-finite polygon coordinate is rejected (E_NONFINITE or E_RANGE)", () => {
    expect(
      codeOf(
        call({
          polygon_m: [
            [-20, -20],
            [20, -20],
            [20, Number.NaN],
            [-20, 20],
          ],
        }),
      ),
    ).toMatch(/E_NONFINITE|E_RANGE/);
    expect(
      codeOf(
        call({
          polygon_m: [
            [-20, -20],
            [Number.POSITIVE_INFINITY, -20],
            [20, 20],
            [-20, 20],
          ],
        }),
      ),
    ).toMatch(/E_NONFINITE|E_RANGE/);
  });

  it("FR-017-48 · a cell size <= 0, a negative RMSE and no valid cell inside the polygon are E_RANGE", () => {
    expect(codeOf(call({ cell_size_m: 0 }))).toBe("E_RANGE");
    expect(codeOf(call({ cell_size_m: -2 }))).toBe("E_RANGE");
    expect(codeOf(call({ rmse_after_m: -0.1 }))).toBe("E_RANGE");
    expect(codeOf(call({ after: new Float64Array(16).fill(Number.NaN) }))).toBe("E_RANGE");
  });

  it("FR-017-48 · a buffer that does not match rows x cols (or differs between the epochs) is E_SCHEMA; more than 2048 rows or columns is E_SIZE", () => {
    expect(codeOf(call({ before: new Float64Array(15) }))).toBe("E_SCHEMA");
    expect(codeOf(call({ after: new Float64Array(17) }))).toBe("E_SCHEMA");
    expect(
      codeOf(call({ rows: 2049, cols: 1, before: new Float64Array(2049), after: new Float64Array(2049) })),
    ).toBe("E_SIZE");
  });
});

describe("metamorphic relations (P-018-52, P-018-53, P-018-54)", () => {
  const grid = fc
    .record({
      rows: fc.integer({ min: 2, max: 20 }),
      cols: fc.integer({ min: 2, max: 20 }),
      cell: fc.constantFrom(0.5, 1, 2, 4),
    })
    .chain(({ rows, cols, cell }) =>
      fc.record({
        rows: fc.constant(rows),
        cols: fc.constant(cols),
        cell: fc.constant(cell),
        before: fc.array(
          fc.integer({ min: 0, max: 1600 }).map((k) => 100 + k / 16),
          { minLength: rows * cols, maxLength: rows * cols },
        ),
        after: fc.array(
          fc.integer({ min: 0, max: 1600 }).map((k) => 100 + k / 16),
          { minLength: rows * cols, maxLength: rows * cols },
        ),
      }),
    );

  it("P-018-52 · a constant difference over the polygon gives dz x area: fill = dz N A_c for dz > 0 and cut = |dz| N A_c for dz < 0, with no volume of the other kind", () => {
    fc.assert(
      fc.property(
        grid,
        fc.integer({ min: 1, max: 800 }).map((k) => k / 16),
        fc.boolean(),
        ({ rows, cols, cell, before }, dz, up) => {
          const after = before.map((z) => z + (up ? dz : -dz));
          const r = run(before, after, rows, cols, { cell_size_m: cell });
          const want = dz * rows * cols * cell * cell;
          return (
            close(up ? r.fill_m3 : r.cut_m3, want, 1e-12) &&
            (up ? r.cut_m3 : r.fill_m3) === 0 &&
            r.valid_cells === rows * cols
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-52 · additivity: splitting the polygon by a line a quarter cell off the centres gives V(A u B) = V(A) + V(B) for fill, cut, net and the cell count", () => {
    fc.assert(
      fc.property(grid, fc.nat(), ({ rows, cols, cell, before, after }, k0) => {
        const k = 1 + (k0 % (cols - 1));
        const x0 = 0;
        const L = (Math.max(rows, cols) + 3) * cell;
        const cut = x0 + (k + 0.25) * cell;
        const rect = (xa: number, xb: number): Array<[number, number]> => [
          [xa, -L],
          [xb, -L],
          [xb, L],
          [xa, L],
        ];
        const part = (poly: Array<[number, number]>) =>
          volume.cut_fill({
            before,
            after,
            rows,
            cols,
            cell_size_m: cell,
            origin_m: [x0, 0],
            polygon_m: poly,
            rmse_before_m: 0,
            rmse_after_m: 0,
          } as never) as Result;
        const full = part(rect(-L, L));
        const left = part(rect(-L, cut));
        const right = part(rect(cut, L));
        return (
          full.fill_m3 === left.fill_m3 + right.fill_m3 &&
          full.cut_m3 === left.cut_m3 + right.cut_m3 &&
          close(full.net_m3, left.net_m3 + right.net_m3, 1e-12) &&
          full.valid_cells === left.valid_cells + right.valid_cells
        );
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-53 · swapping the two epochs swaps cut and fill and negates the net volume (exact)", () => {
    fc.assert(
      fc.property(grid, ({ rows, cols, cell, before, after }) => {
        const a = run(before, after, rows, cols, { cell_size_m: cell });
        const b = run(after, before, rows, cols, { cell_size_m: cell });
        return a.cut_m3 === b.fill_m3 && a.fill_m3 === b.cut_m3 && a.net_m3 === -b.net_m3;
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-54 · scaling the difference field by k (0 or 1e-6 to 10; subnormal factors lose precision in any binary64 product) scales cut and fill by k (rtol 1e-12)", () => {
    fc.assert(
      fc.property(
        grid,
        fc.oneof(fc.constant(0), fc.double({ min: 1e-6, max: 10, noNaN: true })),
        ({ rows, cols, cell, before: field }, k) => {
          const zeros = new Array<number>(rows * cols).fill(0);
          const diff = field.map((z) => z - 50); // positive and negative differences
          const one = run(zeros, diff, rows, cols, { cell_size_m: cell });
          const scaled = run(
            zeros,
            diff.map((d) => k * d),
            rows,
            cols,
            { cell_size_m: cell },
          );
          return close(scaled.fill_m3, k * one.fill_m3, 1e-12) && close(scaled.cut_m3, k * one.cut_m3, 1e-12);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-52 · the volumes equal an independent exact sum (BigInt arithmetic on the dyadic heights)", () => {
    fc.assert(
      fc.property(grid, ({ rows, cols, cell, before, after }) => {
        let fill = 0n;
        let cutv = 0n;
        for (let i = 0; i < before.length; i++) {
          const d = BigInt(Math.round(((after[i] as number) - (before[i] as number)) * 16)); // heights are multiples of 1/16
          if (d > 0n) fill += d;
          else cutv -= d;
        }
        const area = cell * cell;
        const r = run(before, after, rows, cols, { cell_size_m: cell });
        return r.fill_m3 === (Number(fill) / 16) * area && r.cut_m3 === (Number(cutv) / 16) * area;
      }),
      { numRuns: 200 },
    );
  });
});

describe("parity with the numpy DEM differencing of spec 017 (FR-018-51)", () => {
  it("FR-018-51 · cut_fill equals the reference on its fixture (>= 200 vectors, both ends of the validity ranges)", () => {
    expectAnalyticalParity("volume", "cut_fill", (args) => volume.cut_fill(args as never));
  });
});
