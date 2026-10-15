// T-018-071 [red] · FR-018-53 (min-cut ultimate pit equals the reference: same block set, same objective), P-018-49 (positive scaling),
// P-018-50 (relabelling), P-018-51 (nesting in the revenue factor) for the `mincut` engine of spec 018.
//
// Expected API (module `~/engines/mincut`, file web/src/engines/mincut/index.ts). Every function takes the `args` of its DC-018-02 request
// and returns the `result` object (specs/018-web-cases/contracts/engines/mincut.schema.json), snake_case:
//     ultimate_pit(args)   -> { pit_value_cents, block_count, blocks }          `blocks`: ascending block indices (number[])
//     nested_shells(args)  -> { shells: Array<{ revenue_factor, pit_value_cents, block_count, blocks }> }     one shell per revenue factor, in order
//   Block numbering (an assumption of these tests, flagged in the report: the schema fixes only the shape): C order over (levels, rows, cols),
//   index = (level * rows + row) * cols + col, level 0 at the top. A block at level l >= 1 requires the in-grid blocks one level up (l - 1) at the
//   horizontal offsets {(0,0), (+-1,0), (0,+-1)} for pattern "1-5" or every (dr, dc) with |dr|, |dc| <= 1 for "1-9". Blocks of level 0 require nothing.
//   The pit is the MINIMAL maximum-weight closure: the set of blocks reachable from the source in the residual network of a maximum flow
//   (FR-017-14); a block that adds exactly 0 to the value is not in it. Values are integer cents, sums are exact (binary64 integers).
//   Block value of `nested_shells` (docs/theory/planning.md): v_i(lambda) = max(T_i [lambda g_i r (p - s_r) - c_p] - T_i c_m, -T_i c_m) cents.
//   A violation throws an error with `code` E_RANGE (value out of range, revenue factors not strictly increasing or outside (0, 2]), E_SCHEMA
//   (shape, counts, enum) or E_SIZE (more than 10^5 blocks) (FR-018-38 typed errors).
//
// Oracles (independent of the code under test):
//   - hand-built instances below (their pits and values derived by hand, shown in the comments);
//   - an exhaustive search over every subset of a small grid (closure check, maximum value, intersection of all maximum closures = the minimal one),
//     written in this file, on random instances of up to 12 blocks;
//   - the worked example of docs/theory/planning.md (block d with revenue 6 lambda and cost 1 under three waste blocks of cost 1);
//   - the metamorphic relations of spec 018 section 4 (P-018-49..51) and the closure property P-017-02;
//   - the parity fixtures of the reference (`minephys.planning` min-cut, networkx maximum flow as oracle), DC-018-04, class min-cut.
import fc from "fast-check";
import { describe, expect, it } from "vitest";
import * as mincut from "~/engines/mincut";
import { loadParityFixtures } from "~/test-support/parity-fixtures";

type Shape = { levels: number; rows: number; cols: number };
type Pattern = "1-5" | "1-9";
interface PitResult {
  pit_value_cents: number;
  block_count: number;
  blocks: number[];
}
function codeOf(fn: () => unknown): string | null {
  try {
    fn();
    return null;
  } catch (e) {
    return (e as { code?: string }).code ?? "no-code";
  }
}
const pit = (shape: Shape, values: number[], pattern: Pattern = "1-5") =>
  mincut.ultimate_pit({ shape, block_count: values.length, pattern, values_cents: values }) as PitResult;
const idx = (s: Shape, l: number, r: number, c: number) => (l * s.rows + r) * s.cols + c;

/** The precedence arcs (block, required block) of the regular grid, written out by brute force. */
function arcs(s: Shape, pattern: Pattern): Array<[number, number]> {
  const offsets: Array<[number, number]> =
    pattern === "1-5"
      ? [
          [0, 0],
          [1, 0],
          [-1, 0],
          [0, 1],
          [0, -1],
        ]
      : [-1, 0, 1].flatMap((dr) => [-1, 0, 1].map((dc): [number, number] => [dr, dc]));
  const out: Array<[number, number]> = [];
  for (let l = 1; l < s.levels; l++) {
    for (let r = 0; r < s.rows; r++) {
      for (let c = 0; c < s.cols; c++) {
        for (const [dr, dc] of offsets) {
          if (r + dr >= 0 && r + dr < s.rows && c + dc >= 0 && c + dc < s.cols)
            out.push([idx(s, l, r, c), idx(s, l - 1, r + dr, c + dc)]);
        }
      }
    }
  }
  return out;
}

/** Exhaustive oracle: the intersection of all maximum-value closures (the minimal one) and its value. */
function bruteForce(s: Shape, values: number[], pattern: Pattern): { blocks: number[]; value: number } {
  const n = values.length;
  const req = new Array<number>(n).fill(0); // bitmask of required blocks
  for (const [i, j] of arcs(s, pattern)) req[i] = (req[i] as number) | (1 << j);
  let best = Number.NEGATIVE_INFINITY;
  let inter = (1 << n) - 1;
  for (let mask = 0; mask < 1 << n; mask++) {
    let closed = true;
    let value = 0;
    for (let i = 0; i < n && closed; i++) {
      if (mask & (1 << i)) {
        if (((req[i] as number) & ~mask) !== 0) closed = false;
        value += values[i] as number;
      }
    }
    if (!closed) continue;
    if (value > best) {
      best = value;
      inter = mask;
    } else if (value === best) inter &= mask;
  }
  const blocks: number[] = [];
  for (let i = 0; i < n; i++) if (inter & (1 << i)) blocks.push(i);
  return { blocks, value: best };
}

describe("hand-built pits (FR-018-53)", () => {
  it("FR-018-53 · two blocks in a column, top -1 and bottom +5: the pit is both blocks, value 4 cents", () => {
    const r = pit({ levels: 2, rows: 1, cols: 1 }, [-1, 5]);
    expect(r).toEqual({ pit_value_cents: 4, block_count: 2, blocks: [0, 1] });
  });

  it("FR-018-53 · top -10 and bottom +5: not worth digging, the pit is empty with value 0", () => {
    expect(pit({ levels: 2, rows: 1, cols: 1 }, [-10, 5])).toEqual({
      pit_value_cents: 0,
      block_count: 0,
      blocks: [],
    });
  });

  it("FR-018-53 · a block that adds exactly 0 is excluded (the MINIMAL maximum closure): top -5, bottom +5 gives the empty pit", () => {
    expect(pit({ levels: 2, rows: 1, cols: 1 }, [-5, 5])).toEqual({
      pit_value_cents: 0,
      block_count: 0,
      blocks: [],
    });
  });

  it("FR-018-53 · 3 x 3 grid of two levels, nine waste blocks of -1 on top and +10 under the centre: the 1-5 pattern digs the centre column and its four neighbours (value 10 - 5 = 5)", () => {
    const values = [...new Array(9).fill(-1), 0, 0, 0, 0, 10, 0, 0, 0, 0];
    const r = pit({ levels: 2, rows: 3, cols: 3 }, values, "1-5");
    expect(r.pit_value_cents).toBe(5);
    expect(r.blocks).toEqual([1, 3, 4, 5, 7, 13]); // top centre 4, its N 1, W 3, E 5, S 7, and the ore block 9 + 4 = 13
    expect(r.block_count).toBe(6);
  });

  it("FR-018-53 · the same deposit with the 1-9 pattern needs all nine top blocks (value 10 - 9 = 1)", () => {
    const values = [...new Array(9).fill(-1), 0, 0, 0, 0, 10, 0, 0, 0, 0];
    const r = pit({ levels: 2, rows: 3, cols: 3 }, values, "1-9");
    expect(r.pit_value_cents).toBe(1);
    expect(r.blocks).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 13]);
  });

  it("FR-018-53 · with +8 under the centre the 1-5 pit still pays (8 - 5 = 3) and the 1-9 pit does not (8 - 9 < 0): empty", () => {
    const values = [...new Array(9).fill(-1), 0, 0, 0, 0, 8, 0, 0, 0, 0];
    expect(pit({ levels: 2, rows: 3, cols: 3 }, values, "1-5").pit_value_cents).toBe(3);
    expect(pit({ levels: 2, rows: 3, cols: 3 }, values, "1-9")).toEqual({
      pit_value_cents: 0,
      block_count: 0,
      blocks: [],
    });
  });

  it("FR-018-53 · a single level has no precedence: the pit is the set of positive blocks", () => {
    const r = pit({ levels: 1, rows: 2, cols: 3 }, [3, -4, 0, 7, -1, 2]);
    expect(r).toEqual({ pit_value_cents: 12, block_count: 3, blocks: [0, 3, 5] });
  });

  it("FR-018-53 · the arc counts of the geometry (hand: 3 x 3 x 2 has 33 arcs for 1-5 and 49 for 1-9) agree with the test's own enumeration", () => {
    expect(arcs({ levels: 2, rows: 3, cols: 3 }, "1-5")).toHaveLength(33);
    expect(arcs({ levels: 2, rows: 3, cols: 3 }, "1-9")).toHaveLength(49);
  });
});

describe("agreement with an exhaustive search (FR-018-53)", () => {
  const shapeArb = fc
    .record({
      levels: fc.integer({ min: 1, max: 3 }),
      rows: fc.integer({ min: 1, max: 2 }),
      cols: fc.integer({ min: 1, max: 2 }),
    })
    .filter((s) => s.levels * s.rows * s.cols <= 12);

  it("FR-018-53 · on random grids of up to 12 blocks, both patterns, the pit block set and its value equal the exhaustive minimal maximum closure", () => {
    fc.assert(
      fc.property(
        shapeArb,
        fc.constantFrom<Pattern>("1-5", "1-9"),
        fc.array(fc.integer({ min: -20, max: 20 }), { minLength: 12, maxLength: 12 }),
        (shape, pattern, raw) => {
          const values = raw.slice(0, shape.levels * shape.rows * shape.cols);
          const got = pit(shape, values, pattern);
          const want = bruteForce(shape, values, pattern);
          return (
            got.pit_value_cents === want.value &&
            JSON.stringify([...got.blocks].sort((a, b) => a - b)) === JSON.stringify(want.blocks) &&
            got.block_count === want.blocks.length
          );
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-017-02 · the returned pit is closed and its value is the sum of its blocks, on a 100 x 100 x 10 grid of 10^5 blocks (the size cap)", () => {
    const shape = { levels: 10, rows: 100, cols: 100 };
    let seed = 12345;
    const next = () => {
      seed = (Math.imul(seed, 1103515245) + 12345) >>> 0;
      return seed;
    };
    // deeper blocks are richer: ore under waste, as in a real deposit
    const values = Array.from({ length: 100000 }, (_, i) => {
      const level = Math.floor(i / 10000);
      return (next() % 2001) - 1000 + level * 120;
    });
    const t0 = performance.now();
    const r = pit(shape, values, "1-5");
    const seconds = (performance.now() - t0) / 1000;
    expect(seconds).toBeLessThan(30);
    const inPit = new Set(r.blocks);
    expect(inPit.size).toBe(r.blocks.length);
    expect(r.block_count).toBe(r.blocks.length);
    let sum = 0;
    for (const b of r.blocks) sum += values[b] as number;
    expect(sum).toBe(r.pit_value_cents);
    expect(r.pit_value_cents).toBeGreaterThan(0);
    const violations = arcs(shape, "1-5").filter(([i, j]) => inPit.has(i) && !inPit.has(j));
    expect(violations).toEqual([]);
  }, 120_000);
});

describe("metamorphic relations (P-018-49, P-018-50)", () => {
  const instance = fc
    .record({
      levels: fc.integer({ min: 1, max: 4 }),
      rows: fc.integer({ min: 1, max: 5 }),
      cols: fc.integer({ min: 1, max: 5 }),
    })
    .chain((shape) =>
      fc.record({
        shape: fc.constant(shape),
        pattern: fc.constantFrom<Pattern>("1-5", "1-9"),
        values: fc.array(fc.integer({ min: -1000, max: 1000 }), {
          minLength: shape.levels * shape.rows * shape.cols,
          maxLength: shape.levels * shape.rows * shape.cols,
        }),
      }),
    );

  it("P-018-49 · multiplying every value by a positive integer k leaves the pit unchanged and multiplies its value by k", () => {
    fc.assert(
      fc.property(instance, fc.integer({ min: 1, max: 1000 }), ({ shape, pattern, values }, k) => {
        const a = pit(shape, values, pattern);
        const b = pit(
          shape,
          values.map((v) => v * k),
          pattern,
        );
        return (
          JSON.stringify(a.blocks) === JSON.stringify(b.blocks) && b.pit_value_cents === a.pit_value_cents * k
        );
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-50 · relabelling by a symmetry of the grid (flip rows, flip columns, transpose when square) relabels the pit as a set of positions", () => {
    const position = (s: Shape, i: number): [number, number, number] => [
      Math.floor(i / (s.rows * s.cols)),
      Math.floor((i % (s.rows * s.cols)) / s.cols),
      i % s.cols,
    ];
    fc.assert(
      fc.property(
        instance,
        fc.constantFrom("flip-rows", "flip-cols", "transpose"),
        ({ shape, pattern, values }, sym) => {
          if (sym === "transpose" && shape.rows !== shape.cols) return true;
          const map = (l: number, r: number, c: number): [number, number, number] =>
            sym === "flip-rows"
              ? [l, shape.rows - 1 - r, c]
              : sym === "flip-cols"
                ? [l, r, shape.cols - 1 - c]
                : [l, c, r];
          const moved = new Array<number>(values.length).fill(0);
          values.forEach((v, i) => {
            const [l, r, c] = position(shape, i);
            const [l2, r2, c2] = map(l, r, c);
            moved[idx(shape, l2, r2, c2)] = v;
          });
          const a = pit(shape, values, pattern);
          const b = pit(shape, moved, pattern);
          const mapped = a.blocks
            .map((i) => {
              const [l, r, c] = position(shape, i);
              const [l2, r2, c2] = map(l, r, c);
              return idx(shape, l2, r2, c2);
            })
            .sort((x, y) => x - y);
          return (
            JSON.stringify(mapped) === JSON.stringify(b.blocks) && a.pit_value_cents === b.pit_value_cents
          );
        },
      ),
      { numRuns: 200 },
    );
  });
});

describe("nested shells (FR-018-53, P-018-51)", () => {
  const worked = {
    shape: { levels: 2, rows: 1, cols: 3 },
    block_count: 6,
    pattern: "1-5" as Pattern,
    tonnage_kg: [1000, 1000, 1000, 0, 1000, 0],
    grade: [0, 0, 0, 0, 0.5, 0],
    price_cents_per_kg: 0.012,
    selling_cost_cents_per_kg: 0,
    recovery: 1,
    processing_cost_cents_per_kg: 0,
    mining_cost_cents_per_kg: 0.001,
  };
  type Shells = {
    shells: Array<{ revenue_factor: number; pit_value_cents: number; block_count: number; blocks: number[] }>;
  };

  it("FR-018-53 · the worked example of the planning theory page: waste blocks of -1 over an ore block of 6 lambda - 1; the pit pays from lambda = 2/3 on", () => {
    // lambda 0.5: ore 2 < 3 of overburden -> empty; lambda 1: 5 - 3 = 2; lambda 2: 11 - 3 = 8 (bottom side blocks have no tonnage: value 0, never in the minimal pit)
    const r = mincut.nested_shells({ ...worked, revenue_factors: [0.5, 1, 2] }) as Shells;
    expect(r.shells).toEqual([
      { revenue_factor: 0.5, pit_value_cents: 0, block_count: 0, blocks: [] },
      { revenue_factor: 1, pit_value_cents: 2, block_count: 4, blocks: [0, 1, 2, 4] },
      { revenue_factor: 2, pit_value_cents: 8, block_count: 4, blocks: [0, 1, 2, 4] },
    ]);
  });

  it("P-018-51 · raising the revenue factor yields a pit that contains the previous pit, and the pit value never decreases, on random deposits", () => {
    const deposit = fc
      .record({
        levels: fc.integer({ min: 2, max: 4 }),
        rows: fc.integer({ min: 2, max: 4 }),
        cols: fc.integer({ min: 2, max: 4 }),
      })
      .chain((shape) => {
        const n = shape.levels * shape.rows * shape.cols;
        return fc.record({
          shape: fc.constant(shape),
          pattern: fc.constantFrom<Pattern>("1-5", "1-9"),
          tonnage_kg: fc.array(fc.integer({ min: 0, max: 100000 }), { minLength: n, maxLength: n }),
          grade: fc.array(fc.double({ min: 0, max: 0.05, noNaN: true }), { minLength: n, maxLength: n }),
          price: fc.double({ min: 1, max: 100, noNaN: true }),
          processing: fc.double({ min: 0.001, max: 0.5, noNaN: true }),
          mining: fc.double({ min: 0.0005, max: 0.2, noNaN: true }),
        });
      });
    fc.assert(
      fc.property(deposit, ({ shape, pattern, tonnage_kg, grade, price, processing, mining }) => {
        const r = mincut.nested_shells({
          shape,
          block_count: tonnage_kg.length,
          pattern,
          tonnage_kg,
          grade,
          price_cents_per_kg: price,
          selling_cost_cents_per_kg: 0,
          recovery: 0.9,
          processing_cost_cents_per_kg: processing,
          mining_cost_cents_per_kg: mining,
          revenue_factors: [0.25, 0.5, 0.75, 1, 1.5, 2],
        }) as Shells;
        for (let i = 1; i < r.shells.length; i++) {
          const prev = new Set((r.shells[i - 1] as { blocks: number[] }).blocks);
          const cur = new Set((r.shells[i] as { blocks: number[] }).blocks);
          for (const b of prev) if (!cur.has(b)) return false;
          if (
            (r.shells[i] as { pit_value_cents: number }).pit_value_cents <
            (r.shells[i - 1] as { pit_value_cents: number }).pit_value_cents
          )
            return false;
        }
        return (
          r.shells.length === 6 &&
          r.shells.every(
            (s, i) =>
              s.revenue_factor === [0.25, 0.5, 0.75, 1, 1.5, 2][i] && s.block_count === s.blocks.length,
          )
        );
      }),
      { numRuns: 100 },
    );
  });
});

describe("hostile mincut inputs (FR-018-53, FR-018-38)", () => {
  const ok = {
    shape: { levels: 2, rows: 1, cols: 1 },
    block_count: 2,
    pattern: "1-5",
    values_cents: [-1, 5],
  };
  const run = (over: Record<string, unknown>) => () => mincut.ultimate_pit({ ...ok, ...over } as never);

  it("FR-018-53 · the block count must match the shape and the values; an unknown pattern and non-integer cents are E_SCHEMA", () => {
    expect(codeOf(run({ block_count: 3 }))).toBe("E_SCHEMA");
    expect(codeOf(run({ values_cents: [1, 2, 3] }))).toBe("E_SCHEMA");
    expect(codeOf(run({ pattern: "1-7" }))).toBe("E_SCHEMA");
    expect(codeOf(run({ values_cents: [1.5, 2] }))).toBe("E_SCHEMA");
    expect(codeOf(run({ shape: { levels: 0, rows: 1, cols: 1 } }))).toMatch(/E_SCHEMA|E_RANGE/);
    expect(codeOf(run({ values_cents: [], block_count: 0 }))).toMatch(/E_SCHEMA|E_RANGE/);
  });

  it("FR-018-53 · a value beyond +-2^30 cents is E_RANGE and a model of more than 10^5 blocks is E_SIZE", () => {
    expect(codeOf(run({ values_cents: [2 ** 30 + 1, 2] }))).toBe("E_RANGE");
    expect(codeOf(run({ values_cents: [-(2 ** 30) - 1, 2] }))).toBe("E_RANGE");
    const big = { levels: 11, rows: 100, cols: 100 };
    expect(codeOf(run({ shape: big, block_count: 110000, values_cents: new Array(110000).fill(1) }))).toBe(
      "E_SIZE",
    );
  });

  it("FR-018-53 · nested shells reject revenue factors that are empty, not strictly increasing or outside (0, 2], and negative tonnage, grade above 1 or zero recovery", () => {
    const base = {
      shape: { levels: 1, rows: 1, cols: 2 },
      block_count: 2,
      pattern: "1-5",
      tonnage_kg: [1000, 1000],
      grade: [0.1, 0.1],
      price_cents_per_kg: 5,
      selling_cost_cents_per_kg: 0,
      recovery: 0.9,
      processing_cost_cents_per_kg: 0.1,
      mining_cost_cents_per_kg: 0.01,
      revenue_factors: [0.5, 1],
    };
    const shells = (over: Record<string, unknown>) => () =>
      mincut.nested_shells({ ...base, ...over } as never);
    expect(codeOf(shells({}))).toBeNull();
    expect(codeOf(shells({ revenue_factors: [] }))).toMatch(/E_SCHEMA|E_RANGE/);
    expect(codeOf(shells({ revenue_factors: [1, 0.5] }))).toBe("E_RANGE");
    expect(codeOf(shells({ revenue_factors: [0.5, 0.5] }))).toBe("E_RANGE");
    expect(codeOf(shells({ revenue_factors: [0.5, 2.5] }))).toBe("E_RANGE");
    expect(codeOf(shells({ revenue_factors: [0, 1] }))).toBe("E_RANGE");
    expect(codeOf(shells({ tonnage_kg: [-1, 1000] }))).toBe("E_RANGE");
    expect(codeOf(shells({ grade: [1.1, 0.1] }))).toBe("E_RANGE");
    expect(codeOf(shells({ recovery: 0 }))).toBe("E_RANGE");
  });
});

describe("parity with minephys.planning (FR-018-53)", () => {
  it("FR-018-53 · every golden instance of the fixtures: same pit block set and same objective as the reference", () => {
    const fixtures = loadParityFixtures("mincut").filter((f) => f.function === "ultimate_pit");
    expect(fixtures.length, "a min-cut fixture for mincut.ultimate_pit exists").toBeGreaterThan(0);
    let instances = 0;
    for (const fx of fixtures) {
      expect(fx.tolerance.class).toBe("min-cut");
      for (const [i, v] of fx.cases.entries()) {
        const got = mincut.ultimate_pit(structuredClone(v.input) as never) as PitResult;
        const want = v.output as {
          blocks?: number[];
          pit?: number[];
          pit_value_cents?: number;
          objective_cents?: number;
        };
        const wantBlocks = (want.blocks ?? want.pit ?? []).slice().sort((a, b) => a - b);
        expect(
          [...got.blocks].sort((a, b) => a - b),
          `${fx.file} #${i}: block set`,
        ).toEqual(wantBlocks);
        expect(got.pit_value_cents, `${fx.file} #${i}: objective`).toBe(
          (want.pit_value_cents ?? want.objective_cents) as number,
        );
        instances++;
      }
    }
    expect(instances).toBeGreaterThanOrEqual(3);
  });
});
