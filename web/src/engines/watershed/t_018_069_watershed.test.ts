// T-018-069 [red] · FR-018-59 (the TypeScript watershed returns the label map of the Python baseline, and x50 and x80 within rtol 1e-9),
// P-018-46 (invariance under a strictly increasing transform of the elevation), P-018-47 (flip equivariance), P-018-48 (pixel-size scaling)
// for the `watershed` engine of spec 018.
//
// Expected API (module `~/engines/watershed`, file web/src/engines/watershed/index.ts). `segment(args)` takes the `args` of its DC-018-02 request
// (specs/018-web-cases/contracts/engines/watershed.schema.json) except that the three buffer descriptors are replaced by the buffers themselves and
// the shape by `rows` and `cols`:
//     segment({ elevation: Float32Array, markers: Int32Array, mask?: Uint8Array, rows, cols, connectivity?: 1 | 2, min_area_px?, pixel_size_m })
//       -> { labels: Int32Array, instance_count, status: "fit" | "no-fit", x50_m?, x80_m? }
//   Row-major rows x cols buffers. Marker-controlled watershed by priority flooding on the elevation (scikit-image `watershed(elevation, markers, mask,
//   connectivity)` semantics: connectivity 1 = 4 neighbours, 2 = 8; default 1): a pixel takes the label of the neighbour that reached it first from the
//   lowest elevation, markers keep their label, pixels outside the mask (mask 0) and unreachable pixels stay 0. `instance_count` is the number of distinct
//   non-zero labels. `status` is "no-fit" (and x50_m, x80_m are absent) when there are fewer than 3 instances (FR-012-25), otherwise "fit" with the fragment
//   size quantiles x50_m and x80_m in metres (they scale linearly with `pixel_size_m`).
//   Errors (FR-018-38 typed errors): a buffer whose length is not rows x cols E_SCHEMA; rows or columns above 1024 E_SIZE, below 16 or a
//   connectivity other than 1 or 2 E_SCHEMA; a NaN or infinite elevation, a negative marker, a non-positive pixel size E_RANGE.
//
// Oracles (independent of the code under test):
//   - scikit-image 0.26.0 `skimage.segmentation.watershed`, called directly on 2026-10-11 on the hand images below (the reference semantics of the
//     Python baseline): the four-basin image gives four 8 x 8 quadrants (identical to the nearest-centre rule), the two-basin ridge image gives columns
//     0-7 to label 1, 9-15 to label 2 and the crest column 8 to label 1;
//   - the metamorphic relations of spec 018 section 4 (P-018-46..48) on tie-free random images (random permutations of distinct integers);
//   - the parity fixtures of the Python watershed baseline (spec 012), DC-018-04, class label-map-exact.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as watershed from "~/engines/watershed";
import { loadParityFixtures } from "~/test-support/parity-fixtures";

interface Seg {
  labels: Int32Array;
  instance_count: number;
  status: "fit" | "no-fit";
  x50_m?: number;
  x80_m?: number;
}
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}
const seg = (
  elevation: Float32Array,
  markers: Int32Array,
  rows: number,
  cols: number,
  over: Record<string, unknown> = {},
) => watershed.segment({ elevation, markers, rows, cols, pixel_size_m: 0.01, ...over } as never) as Seg;

// four basins, centres (3,3) (3,12) (12,3) (12,12): elevation = squared distance to the nearest centre
const N = 16;
const CENTRES: Array<[number, number]> = [
  [3, 3],
  [3, 12],
  [12, 3],
  [12, 12],
];
const fourBasins = () => {
  const e = new Float32Array(N * N);
  const m = new Int32Array(N * N);
  for (let r = 0; r < N; r++)
    for (let c = 0; c < N; c++)
      e[r * N + c] = Math.min(...CENTRES.map(([a, b]) => (r - a) ** 2 + (c - b) ** 2));
  CENTRES.forEach(([r, c], i) => {
    m[r * N + c] = i + 1;
  });
  return { e, m };
};

describe("hand images against scikit-image (FR-018-59)", () => {
  it("FR-018-59 · the four-basin image gives four 8 x 8 quadrants labelled 1 (top left), 2 (top right), 3 (bottom left), 4 (bottom right)", () => {
    const { e, m } = fourBasins();
    const r = seg(e, m, N, N);
    expect(r.labels).toBeInstanceOf(Int32Array);
    expect(r.labels).toHaveLength(N * N);
    for (let row = 0; row < N; row++) {
      for (let c = 0; c < N; c++) {
        const want = (row < 8 ? 0 : 2) + (c < 8 ? 1 : 2);
        expect(r.labels[row * N + c], `(${row},${c})`).toBe(want);
      }
    }
    expect(r.instance_count).toBe(4);
    expect(r.status).toBe("fit");
    expect(r.x50_m).toBeGreaterThan(0);
    expect(r.x80_m as number).toBeGreaterThanOrEqual(r.x50_m as number);
  });

  it("FR-018-59 · 8-connectivity gives the same quadrants on this image (as scikit-image does)", () => {
    const { e, m } = fourBasins();
    expect(Array.from(seg(e, m, N, N, { connectivity: 2 }).labels)).toEqual(
      Array.from(seg(e, m, N, N, { connectivity: 1 }).labels),
    );
  });

  it("FR-018-59 · the two-basin ridge image: columns 0-7 are label 1, columns 9-15 are label 2, the crest column 8 is 1 or 2; fewer than 3 instances is no-fit with no sizes", () => {
    const e = new Float32Array(N * N);
    for (let r = 0; r < N; r++)
      for (let c = 0; c < N; c++) e[r * N + c] = c <= 8 ? (c - 3) ** 2 : (13 - c) ** 2;
    const m = new Int32Array(N * N);
    m[8 * N + 3] = 1;
    m[8 * N + 13] = 2;
    const r = seg(e, m, N, N);
    for (let row = 0; row < N; row++) {
      for (let c = 0; c < N; c++) {
        const v = r.labels[row * N + c] as number;
        if (c <= 7) expect(v, `(${row},${c})`).toBe(1);
        else if (c >= 9) expect(v, `(${row},${c})`).toBe(2);
        else expect([1, 2]).toContain(v);
      }
    }
    expect(r.instance_count).toBe(2);
    expect(r.status).toBe("no-fit");
    expect("x50_m" in r).toBe(false);
    expect("x80_m" in r).toBe(false);
  });

  it("FR-018-59 · the mask keeps pixels outside it at label 0 (here the left half) and the other basins unchanged", () => {
    const { e, m } = fourBasins();
    const mask = new Uint8Array(N * N).fill(1);
    for (let r = 0; r < N; r++) for (let c = 0; c < 8; c++) mask[r * N + c] = 0;
    m[3 * N + 3] = 0;
    m[12 * N + 3] = 0;
    const r = seg(e, m, N, N, { mask });
    for (let row = 0; row < N; row++) {
      for (let c = 0; c < N; c++) {
        const v = r.labels[row * N + c] as number;
        if (c < 8) expect(v).toBe(0);
        else expect(v).toBe(row < 8 ? 2 : 4);
      }
    }
    expect(r.instance_count).toBe(2);
  });

  it("FR-018-59 · without markers nothing is labelled: all zeros, no instance, no-fit", () => {
    const { e } = fourBasins();
    const r = seg(e, new Int32Array(N * N), N, N);
    expect(Array.from(r.labels).every((v) => v === 0)).toBe(true);
    expect(r.instance_count).toBe(0);
    expect(r.status).toBe("no-fit");
  });

  it("FR-018-59 · the input buffers are not modified", () => {
    const { e, m } = fourBasins();
    const e0 = Float32Array.from(e);
    const m0 = Int32Array.from(m);
    seg(e, m, N, N);
    expect(e).toEqual(e0);
    expect(m).toEqual(m0);
  });
});

describe("hostile watershed inputs (FR-018-59, FR-018-38)", () => {
  const { e, m } = fourBasins();
  it("FR-018-59 · buffers of the wrong length are E_SCHEMA; a NaN or infinite elevation, a negative marker and a non-positive pixel size are E_RANGE", () => {
    expect(codeOf(() => seg(e.slice(0, 255), m, N, N))).toBe("E_SCHEMA");
    expect(codeOf(() => seg(e, m.slice(0, 255), N, N))).toBe("E_SCHEMA");
    const nan = Float32Array.from(e);
    nan[5] = Number.NaN;
    expect(codeOf(() => seg(nan, m, N, N))).toBe("E_RANGE");
    const inf = Float32Array.from(e);
    inf[5] = Number.POSITIVE_INFINITY;
    expect(codeOf(() => seg(inf, m, N, N))).toBe("E_RANGE");
    const neg = Int32Array.from(m);
    neg[0] = -1;
    expect(codeOf(() => seg(e, neg, N, N))).toBe("E_RANGE");
    expect(codeOf(() => seg(e, m, N, N, { pixel_size_m: 0 }))).toBe("E_RANGE");
    expect(codeOf(() => seg(e, m, N, N, { pixel_size_m: -1 }))).toBe("E_RANGE");
  });

  it("FR-018-59 · an image above 1024 x 1024 is E_SIZE; below 16 or an unknown connectivity is E_SCHEMA", () => {
    expect(codeOf(() => seg(new Float32Array(1025 * 16), new Int32Array(1025 * 16), 1025, 16))).toBe(
      "E_SIZE",
    );
    expect(codeOf(() => seg(new Float32Array(8 * 8), new Int32Array(8 * 8), 8, 8))).toMatch(
      /E_SCHEMA|E_RANGE/,
    );
    expect(codeOf(() => seg(e, m, N, N, { connectivity: 3 }))).toBe("E_SCHEMA");
  });
});

describe("metamorphic relations (P-018-46, P-018-47, P-018-48)", () => {
  /** A tie-free elevation (a random permutation of 0..n-1) and 3-12 markers on distinct pixels, from fast-check. */
  const image = fc.record({ size: fc.constantFrom(16, 24, 32, 64) }).chain(({ size }) =>
    fc.record({
      size: fc.constant(size),
      perm: fc.shuffledSubarray(
        Array.from({ length: size * size }, (_, i) => i),
        { minLength: size * size, maxLength: size * size },
      ),
      marks: fc.uniqueArray(fc.integer({ min: 0, max: size * size - 1 }), { minLength: 3, maxLength: 12 }),
    }),
  );
  const build = (size: number, perm: number[], marks: number[]) => {
    const e = Float32Array.from(perm);
    const m = new Int32Array(size * size);
    marks.forEach((p, i) => {
      m[p] = i + 1;
    });
    return { e, m };
  };

  it("P-018-46 · a strictly increasing transform of the elevation (2x + 1, x^2, x + 1000) leaves the label map unchanged (exact)", () => {
    fc.assert(
      fc.property(image, ({ size, perm, marks }) => {
        const { e, m } = build(size, perm, marks);
        const base = Array.from(seg(e, m, size, size).labels);
        const t1 = Array.from(
          seg(
            e.map((x) => 2 * x + 1),
            m,
            size,
            size,
          ).labels,
        );
        const t2 = Array.from(
          seg(
            e.map((x) => x * x),
            m,
            size,
            size,
          ).labels,
        );
        const t3 = Array.from(
          seg(
            e.map((x) => x + 1000),
            m,
            size,
            size,
          ).labels,
        );
        return (
          JSON.stringify(base) === JSON.stringify(t1) &&
          JSON.stringify(base) === JSON.stringify(t2) &&
          JSON.stringify(base) === JSON.stringify(t3)
        );
      }),
      { numRuns: 100 },
    );
  });

  it("P-018-47 · flipping the elevation and the markers (left-right or up-down) flips the label map (exact, tie-free images)", () => {
    fc.assert(
      fc.property(image, fc.constantFrom("lr", "ud"), ({ size, perm, marks }, axis) => {
        const { e, m } = build(size, perm, marks);
        const flip = <T extends Float32Array | Int32Array>(a: T): T => {
          const out = a.slice() as T;
          for (let r = 0; r < size; r++)
            for (let c = 0; c < size; c++)
              out[r * size + c] = a[
                axis === "lr" ? r * size + (size - 1 - c) : (size - 1 - r) * size + c
              ] as number;
          return out;
        };
        const a = seg(e, m, size, size).labels;
        const b = seg(flip(e), flip(m), size, size).labels;
        return JSON.stringify(Array.from(flip(a))) === JSON.stringify(Array.from(b));
      }),
      { numRuns: 100 },
    );
  });

  it("P-018-48 · changing the pixel size by k scales x50 and x80 by k (rtol 1e-12) and leaves the label map alone", () => {
    const { e, m } = fourBasins();
    fc.assert(
      fc.property(fc.double({ min: 0.1, max: 10, noNaN: true }), (k) => {
        const a = seg(e, m, N, N, { pixel_size_m: 0.05 });
        const b = seg(e, m, N, N, { pixel_size_m: 0.05 * k });
        return (
          a.status === "fit" &&
          b.status === "fit" &&
          Math.abs((b.x50_m as number) - k * (a.x50_m as number)) <= 1e-12 * k * (a.x50_m as number) &&
          Math.abs((b.x80_m as number) - k * (a.x80_m as number)) <= 1e-12 * k * (a.x80_m as number) &&
          JSON.stringify(Array.from(a.labels)) === JSON.stringify(Array.from(b.labels))
        );
      }),
      { numRuns: 200 },
    );
  });
});

describe("parity with the Python watershed baseline (FR-018-59)", () => {
  it("FR-018-59 · on every fixture the label map is identical and x50, x80 equal the reference within rtol 1e-9", () => {
    const fixtures = loadParityFixtures("watershed").filter((f) => f.function === "segment");
    expect(fixtures.length, "a label-map-exact fixture for watershed.segment exists").toBeGreaterThan(0);
    let vectors = 0;
    for (const fx of fixtures) {
      expect(fx.tolerance.class).toBe("label-map-exact");
      for (const [i, v] of fx.cases.entries()) {
        const got = watershed.segment(structuredClone(v.input) as never) as Seg;
        const want = v.output as {
          labels: number[];
          instance_count: number;
          status: string;
          x50_m?: number;
          x80_m?: number;
        };
        expect(Array.from(got.labels), `${fx.file} #${i}: labels`).toEqual(Array.from(want.labels));
        expect(got.instance_count).toBe(want.instance_count);
        expect(got.status).toBe(want.status);
        for (const key of ["x50_m", "x80_m"] as const) {
          if (want[key] !== undefined)
            expect(
              Math.abs((got[key] as number) - (want[key] as number)),
              `${fx.file} #${i} ${key}`,
            ).toBeLessThanOrEqual(1e-9 * Math.abs(want[key] as number));
        }
        vectors++;
      }
    }
    expect(vectors).toBeGreaterThanOrEqual(3);
  });
});
