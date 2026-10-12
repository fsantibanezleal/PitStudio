// T-011-011 [red] · FR-011-02, FR-011-13, P-011-04: the TypeScript twin of the radius graph (the `gns` worker builds it in the browser).
//
// Oracles (independent of the code under test; plan 011 test strategy FR-011-02 / FR-011-13): the same fixtures as the Python test
// tests/property/test_t_011_011_radius_graph.py, written out by hand, and a brute-force O(N^2) reference written in this file:
//   - integer lattice, spacing 1, R = 2.5 (index = 5 * row + col, coordinates (col, row)): the centre particle of a 5 x 5 lattice has 20
//     neighbours, listed by distance then index: 1, sqrt 2, 2, sqrt 5 shells -> [7, 11, 13, 17, 6, 8, 16, 18, 2, 10, 14, 22, 1, 3, 5, 9, 15,
//     19, 21, 23]; the corner (0, 0) has [1, 5, 6, 2, 10, 7, 11];
//   - a pair exactly R apart is not connected, a pair 2.5 - 2^-10 apart is (both coordinates exact in binary32);
//   - 41 particles inside a disc of radius 0.5 (R = 2.5) have 40 neighbours each: overflow count 41, 32 nearest kept;
//   - relations of P-011-04: symmetry (no overflow), no self edge, distance < R, order by (distance, index), permutation relabelling,
//     translation by a dyadic vector and scaling by 2 (exact on dyadic coordinates).
// Cross-language identity (P-011-04): the 5 x 5 lattice lists above are asserted byte for byte here and in the Python test.
//
// Expected API (module `web/src/engines/gns/radiusGraph.ts`, used by the `gns` worker; errors in `web/src/engines/gns/errors.ts`):
//   buildRadiusGraph(positions: Float32Array, radius: number, kMax = 32): { n: number; index: Int32Array; mask: Uint8Array; overflowCount: number }
//     positions = flat [x0, y0, x1, y1, ...] (metres, binary32); squared distances in binary64 from the binary32 values; neighbour of i iff j != i and
//     d2 < R^2, ordered by (d2, j), the first kMax kept, `index` and `mask` have n * kMax entries (row i at i * kMax), masked-off entries hold an
//     index in [0, n), `overflowCount` counts the particles with more than kMax neighbours.
//     Throws InvalidGraphError (name "InvalidGraphError") for n = 0, an odd length, a non-finite coordinate, or a radius that is not a positive finite number.
import { describe, expect, it } from "vitest";
import { InvalidGraphError } from "./errors";
import { buildRadiusGraph } from "./radiusGraph";

const K = 32;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function lattice(nx: number, ny: number): Float32Array {
  const out = new Float32Array(nx * ny * 2);
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      out[2 * (r * nx + c)] = c;
      out[2 * (r * nx + c) + 1] = r;
    }
  }
  return out;
}

function listed(g: { index: Int32Array; mask: Uint8Array }, i: number): number[] {
  const out: number[] = [];
  for (let k = 0; k < K; k++) if (g.mask[i * K + k] !== 0) out.push(g.index[i * K + k] as number);
  return out;
}

/** Brute force: all neighbours (before the K cut) of every particle, and the overflow count. */
function reference(pos: Float32Array, radius: number): { lists: number[][]; overflow: number } {
  const n = pos.length / 2;
  const lists: number[][] = [];
  let overflow = 0;
  for (let i = 0; i < n; i++) {
    const cand: { d2: number; j: number }[] = [];
    for (let j = 0; j < n; j++) {
      if (j === i) continue;
      const dx = (pos[2 * i] as number) - (pos[2 * j] as number);
      const dy = (pos[2 * i + 1] as number) - (pos[2 * j + 1] as number);
      const d2 = dx * dx + dy * dy; // Float32Array reads give binary64 numbers: the arithmetic is binary64
      if (d2 < radius * radius) cand.push({ d2, j });
    }
    cand.sort((a, b) => a.d2 - b.d2 || a.j - b.j);
    if (cand.length > K) overflow++;
    lists.push(cand.map((c) => c.j));
  }
  return { lists, overflow };
}

function randomPacking(seed: number, n: number, density: number): Float32Array {
  const rnd = mulberry32(seed);
  const side = Math.sqrt(n / density);
  const out = new Float32Array(2 * n);
  for (let i = 0; i < out.length; i++) out[i] = rnd() * side;
  return out;
}

describe("hand-counted fixtures (FR-011-02)", () => {
  it("FR-011-02 · the lattice centre has the twenty hand-counted neighbours in distance then index order", () => {
    const g = buildRadiusGraph(lattice(5, 5), 2.5);
    expect(listed(g, 12)).toEqual([7, 11, 13, 17, 6, 8, 16, 18, 2, 10, 14, 22, 1, 3, 5, 9, 15, 19, 21, 23]);
    expect(g.index.length).toBe(25 * K);
    expect(g.mask.length).toBe(25 * K);
    expect(g.overflowCount).toBe(0);
    expect(g.n).toBe(25);
  });

  it("FR-011-02 · the lattice corner has seven neighbours", () => {
    expect(listed(buildRadiusGraph(lattice(5, 5), 2.5), 0)).toEqual([1, 5, 6, 2, 10, 7, 11]);
  });

  it("FR-011-02 · no self edge and every padded index lies inside [0, n)", () => {
    const g = buildRadiusGraph(lattice(4, 3), 2.5);
    for (let i = 0; i < 12; i++) expect(listed(g, i)).not.toContain(i);
    expect(Math.min(...g.index)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...g.index)).toBeLessThan(12);
  });

  it("FR-011-02 · a pair exactly R apart is not connected and a pair just inside is", () => {
    const atR = new Float32Array([0, 0, 2.5, 0]);
    const inside = new Float32Array([0, 0, 2.4990234375, 0]);
    expect(listed(buildRadiusGraph(atR, 2.5), 0)).toEqual([]);
    expect(listed(buildRadiusGraph(inside, 2.5), 0)).toEqual([1]);
    expect(listed(buildRadiusGraph(inside, 2.5), 1)).toEqual([0]);
  });

  it("FR-011-02 · squared distances use binary64 on the binary32 coordinates", () => {
    const pos = new Float32Array([Math.fround(0.1), 0, Math.fround(Math.fround(0.1) + Math.fround(2.4)), 0]);
    const dRef = (pos[2] as number) - (pos[0] as number);
    for (const radius of [dRef - 1e-9, dRef + 1e-9]) {
      expect(listed(buildRadiusGraph(pos, radius), 0).length === 1).toBe(dRef * dRef < radius * radius);
    }
  });
});

describe("overflow (FR-011-13)", () => {
  it("FR-011-13 · 41 particles within R of each other overflow: all 41 counted and the 32 nearest kept", () => {
    const rnd = mulberry32(7);
    const pos = new Float32Array(82);
    for (let i = 0; i < 82; i++) pos[i] = rnd() - 0.5;
    const ref = reference(pos, 2.5);
    const g = buildRadiusGraph(pos, 2.5);
    expect(ref.overflow).toBe(41);
    expect(g.overflowCount).toBe(41);
    for (let i = 0; i < 41; i++) {
      expect(listed(g, i)).toEqual((ref.lists[i] as number[]).slice(0, K));
      expect(listed(g, i).length).toBe(K);
    }
  });

  it("FR-011-13 · exactly 32 neighbours is the limit, not an overflow", () => {
    const rnd = mulberry32(11);
    const pos = new Float32Array(66);
    for (let i = 0; i < 66; i++) pos[i] = rnd() - 0.5;
    const g = buildRadiusGraph(pos, 2.5);
    expect(g.overflowCount).toBe(0);
    expect(g.mask.every((m) => m === 1)).toBe(true);
  });
});

describe("properties (P-011-04)", () => {
  it("P-011-04 · equals the brute force reference with symmetry, distance bound and order on 60 random packings", () => {
    for (let seed = 1; seed <= 60; seed++) {
      const n = 2 + ((seed * 37) % 160);
      const density = 0.3 + ((seed * 13) % 100) / 100;
      const pos = randomPacking(seed, n, density);
      const ref = reference(pos, 2.5);
      const g = buildRadiusGraph(pos, 2.5);
      expect(g.overflowCount).toBe(ref.overflow);
      for (let i = 0; i < n; i++) {
        const got = listed(g, i);
        expect(got).toEqual((ref.lists[i] as number[]).slice(0, K));
        expect(got).not.toContain(i);
      }
      if (ref.overflow === 0) {
        const edges = new Set<string>();
        for (let i = 0; i < n; i++) for (const j of listed(g, i)) edges.add(`${i},${j}`);
        for (const e of edges) {
          const [i, j] = e.split(",");
          expect(edges.has(`${j},${i}`)).toBe(true);
        }
      }
    }
  });

  it("P-011-04 · permuting the particles relabels the neighbour sets", () => {
    for (let seed = 1; seed <= 25; seed++) {
      const n = 10 + seed * 4;
      const pos = randomPacking(seed + 100, n, 0.6);
      const rnd = mulberry32(seed + 7);
      const perm = Array.from({ length: n }, (_, i) => i).sort(() => rnd() - 0.5);
      const inv = new Array<number>(n);
      perm.forEach((old, k) => {
        inv[old] = k;
      });
      const moved = new Float32Array(2 * n);
      perm.forEach((old, k) => {
        moved[2 * k] = pos[2 * old] as number;
        moved[2 * k + 1] = pos[2 * old + 1] as number;
      });
      const g0 = buildRadiusGraph(pos, 2.5);
      const g1 = buildRadiusGraph(moved, 2.5);
      expect(g1.overflowCount).toBe(g0.overflowCount);
      if (g0.overflowCount === 0) {
        perm.forEach((old, k) => {
          expect(new Set(listed(g0, old).map((j) => inv[j]))).toEqual(new Set(listed(g1, k)));
        });
      }
    }
  });

  it("P-011-04 · translating by a dyadic vector and doubling positions and radius leave the graph unchanged", () => {
    for (let seed = 1; seed <= 25; seed++) {
      const rnd = mulberry32(seed + 500);
      const n = 5 + seed * 3;
      const pos = new Float32Array(2 * n);
      for (let i = 0; i < pos.length; i++) pos[i] = Math.round(rnd() * 12 * 256) / 256; // multiples of 2^-8: ties are likely
      const shift = new Float32Array([
        Math.round((rnd() - 0.5) * 8192) / 16,
        Math.round((rnd() - 0.5) * 8192) / 16,
      ]);
      const moved = pos.map((v, i) => v + (shift[i % 2] as number));
      const doubled = pos.map((v) => v * 2);
      const base = buildRadiusGraph(pos, 2.5);
      for (const other of [buildRadiusGraph(moved, 2.5), buildRadiusGraph(doubled, 5.0)]) {
        expect(other.overflowCount).toBe(base.overflowCount);
        expect(Array.from(other.mask)).toEqual(Array.from(base.mask));
        for (let i = 0; i < n; i++) expect(listed(other, i)).toEqual(listed(base, i));
      }
    }
  });
});

describe("hostile input", () => {
  const bad: [string, Float32Array][] = [
    ["empty", new Float32Array(0)],
    ["odd length", new Float32Array([0, 0, 1])],
    ["nan", new Float32Array([0, Number.NaN, 1, 1])],
    ["infinity", new Float32Array([Number.POSITIVE_INFINITY, 0, 1, 1])],
    ["minus infinity", new Float32Array([0, Number.NEGATIVE_INFINITY, 1, 1])],
  ];
  for (const [label, pos] of bad) {
    it(`FR-011-15 · ${label} positions throw InvalidGraphError and return no graph`, () => {
      expect(() => buildRadiusGraph(pos, 2.5)).toThrowError(InvalidGraphError);
    });
  }
  for (const radius of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    it(`FR-011-15 · radius ${radius} throws InvalidGraphError`, () => {
      expect(() => buildRadiusGraph(lattice(3, 3), radius)).toThrowError(InvalidGraphError);
    });
  }
  it("FR-011-15 · the error is a named InvalidGraphError carrying a message", () => {
    try {
      buildRadiusGraph(new Float32Array(0), 2.5);
      throw new Error("did not throw");
    } catch (e) {
      expect((e as Error).name).toBe("InvalidGraphError");
      expect((e as Error).message.length).toBeGreaterThan(0);
    }
  });
});
