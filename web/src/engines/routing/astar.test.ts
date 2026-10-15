// @vitest-environment node
//
// T-007-064 (1/2) · the TypeScript A* router equals the Python goldens cell for cell and within rtol 1e-12, rejects hostile DEMs and requests as typed results, and routes a 512 x 512 grid in at most 1 s: FR-007-35, FR-007-36,
// FR-007-37, FR-007-39, NFR-007-04.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-35 (least-energy feasible 8-neighbour path; an edge is feasible only if |dz| / L <= g_max; c(e) = (m g / eta) max(0, RR/100 L + dz); heuristic h(n) = (m g / eta) max(0, RR/100 d_xy + (z_goal - z_n));
// ties by (f, g, cell index)), FR-007-36 (a NaN or infinite cell outside the nodata mask, a cell size <= 0 or non-finite, more than 1024 x 1024 cells in the browser, a g_max that is non-finite, <= 0 or > 1, a start or goal outside the grid or on a nodata
// cell: the error names the first offending cell or field and the number of offending cells), FR-007-37 (no feasible path: `NoFeasibleRoute` as a value, each feasible cell expanded at most once), FR-007-39 (the TypeScript ports of the router and the
// route-energy engine equal the Python implementations on the golden vectors: the identical cell sequence, costs within rtol 1e-12) and NFR-007-04 (A* on a 512 x 512 grid <= 1 s on tier T2).
//
// Oracle: tests/fixtures/haulage/routing/astar_goldens.json (written by the test author's independent heapq A* with the spec's tie rule, cross-checked against networkx Dijkstra; the same file the Python test T-007-060 reproduces); hand-built hostile inputs;
// the wall-clock of this run for the benchmark (the reference machine's budget is 1 s; the Vitest benchmark of the spec).
//
// Expected API (module `~/engines/routing/astar`), the same field names as the Python router:
//   type Dem = { z: Float64Array /* row-major */; rows: number; cols: number; cell_m: number; nodata?: Uint8Array | null /* 1 = no data */ }
//   type AstarResult =
//     | { ok: true; kind: "route"; cells: [number, number][]; cost_j: number; expanded: number }
//     | { ok: true; kind: "no-feasible-route"; expanded: number }
//     | { ok: false; kind: "InvalidDEM"; field: "z" | "cell_m" | "nodata" | "shape"; cell: [number, number] | null; count: number }
//     | { ok: false; kind: "InvalidRouteRequest"; field: string; value: unknown }
//   findRoute(dem: Dem, start: [number, number], goal: [number, number], params: { mass_kg: number; rr_pct: number; g_max: number; eta: number; g: number }): AstarResult
//     never throws for hostile input and never returns NaN or Infinity inside an ok result; the browser limit is rows x cols <= 1,048,576 (checked from rows and cols before any element is read); cost_j = (mass_kg g / eta) x the sum of edge costs.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { type Dem, findRoute } from "~/engines/routing/astar";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
type Case = {
  id: string;
  rows: number;
  cols: number;
  cell_m: number;
  z: number[];
  nodata: number[];
  start: [number, number];
  goal: [number, number];
  mass_kg: number;
  rr_pct: number;
  g_max: number;
  eta: number;
  g: number;
  cells: [number, number][] | null;
  cost_j: number;
  expanded: number;
  tie_rule: boolean;
};
const GOLD = (
  JSON.parse(readFileSync(resolve(REPO, "tests/fixtures/haulage/routing/astar_goldens.json"), "utf-8")) as {
    cases: Case[];
  }
).cases;

const OK = { mass_kg: 400000, rr_pct: 3, g_max: 0.1, eta: 0.9, g: 9.80665 };
const flat = (rows = 4, cols = 5, cell_m = 10): Dem => ({
  z: new Float64Array(rows * cols),
  rows,
  cols,
  cell_m,
});

function demOf(c: Case): Dem {
  const nodata = new Uint8Array(c.rows * c.cols);
  for (const i of c.nodata) nodata[i] = 1;
  return {
    z: Float64Array.from(c.z),
    rows: c.rows,
    cols: c.cols,
    cell_m: c.cell_m,
    nodata: c.nodata.length ? nodata : null,
  };
}
const paramsOf = (c: Case) => ({ mass_kg: c.mass_kg, rr_pct: c.rr_pct, g_max: c.g_max, eta: c.eta, g: c.g });

describe("FR-007-39 · the goldens of the Python router", () => {
  for (const c of GOLD) {
    it(`FR-007-39 · ${c.id}${c.tie_rule ? " (tie rule)" : ""}: the identical cell sequence and the cost within rtol 1e-12`, () => {
      const r = findRoute(demOf(c), c.start, c.goal, paramsOf(c));
      if (c.cells === null) {
        expect(r).toMatchObject({ ok: true, kind: "no-feasible-route", expanded: c.expanded });
        return;
      }
      expect(r.ok && r.kind === "route").toBe(true);
      if (!(r.ok && r.kind === "route")) return;
      expect(r.cells).toEqual(c.cells);
      expect(Math.abs(r.cost_j - c.cost_j)).toBeLessThanOrEqual(1e-9 + 1e-12 * Math.abs(c.cost_j));
      expect(r.expanded).toBeLessThanOrEqual(c.rows * c.cols);
    });
  }
});

describe("FR-007-35 · the search itself", () => {
  it("FR-007-35 · the 3 x 3 flat tie goes through the centre (hand derivation: 0 -> 4 -> 8)", () => {
    const r = findRoute(flat(3, 3), [0, 0], [2, 2], {
      mass_kg: 400000,
      rr_pct: 0,
      g_max: 0.1,
      eta: 1,
      g: 9.80665,
    });
    expect(r).toMatchObject({
      ok: true,
      kind: "route",
      cells: [
        [0, 0],
        [1, 1],
        [2, 2],
      ],
      cost_j: 0,
    });
  });
  it("FR-007-35 · start equal to goal is the one-cell route of cost 0", () => {
    expect(findRoute(flat(3, 3), [1, 1], [1, 1], OK)).toMatchObject({
      ok: true,
      kind: "route",
      cells: [[1, 1]],
      cost_j: 0,
    });
  });
  it("FR-007-35 · on a flat DEM the cost is (m g / eta)(RR/100) times the octile distance (closed form, rtol 1e-12)", () => {
    const rows = 9;
    const cols = 14;
    const r = findRoute(flat(rows, cols), [1, 2], [7, 12], OK);
    const dr = 6;
    const dc = 10;
    const octile = Math.max(dr, dc) - Math.min(dr, dc) + Math.SQRT2 * Math.min(dr, dc);
    const want = ((OK.mass_kg * OK.g) / OK.eta) * (OK.rr_pct / 100) * 10 * octile;
    expect(r.ok && r.kind === "route").toBe(true);
    if (r.ok && r.kind === "route") expect(Math.abs(r.cost_j - want)).toBeLessThanOrEqual(1e-12 * want);
  });
  it("FR-007-37 · a steep wall gives NoFeasibleRoute as a value after expanding each feasible cell once", () => {
    const z = new Float64Array(81);
    for (let r = 0; r < 9; r++) z[r * 9 + 4] = 3;
    const wall: Dem = { z, rows: 9, cols: 9, cell_m: 10 };
    expect(findRoute(wall, [4, 0], [4, 8], OK)).toEqual({
      ok: true,
      kind: "no-feasible-route",
      expanded: 36,
    });
    expect(findRoute(wall, [4, 0], [4, 8], { ...OK, g_max: 0.35 })).toMatchObject({
      ok: true,
      kind: "route",
    });
  });
  it("FR-007-35 · the grade limit is inclusive", () => {
    const z = Float64Array.from([0, 1, 1]); // a 1 m step over 10 m: grade exactly 0.1
    const d: Dem = { z, rows: 1, cols: 3, cell_m: 10 };
    expect(findRoute(d, [0, 0], [0, 2], OK)).toMatchObject({ kind: "route" });
    expect(findRoute(d, [0, 0], [0, 2], { ...OK, g_max: 0.0999999999 })).toMatchObject({
      kind: "no-feasible-route",
    });
  });
  it("FR-007-35 · the search is deterministic and leaves the DEM untouched", () => {
    const c = GOLD.find((x) => x.id === "random-32x32") as Case;
    const dem = demOf(c);
    const before = Array.from(dem.z);
    const a = findRoute(dem, c.start, c.goal, paramsOf(c));
    const b = findRoute(dem, c.start, c.goal, paramsOf(c));
    expect(a).toEqual(b);
    expect(Array.from(dem.z)).toEqual(before);
  });
});

describe("FR-007-36 · hostile DEMs", () => {
  const bad: [string, number][] = [
    ["NaN", Number.NaN],
    ["+Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
  ];
  for (const [name, v] of bad) {
    const cases: [number[][], [number, number], number][] = [
      [[[2, 3]], [2, 3], 1],
      [
        [
          [2, 3],
          [1, 4],
        ],
        [1, 4],
        2,
      ],
      [
        [
          [3, 4],
          [0, 2],
          [2, 2],
          [0, 3],
        ],
        [0, 2],
        4,
      ],
    ];
    for (const [cells, first, count] of cases) {
      it(`FR-007-36 · ${name} at ${JSON.stringify(cells)} names the first cell ${JSON.stringify(first)} and the count ${count}`, () => {
        const d = flat();
        for (const [r, c] of cells as [number, number][]) d.z[r * 5 + c] = v;
        expect(findRoute(d, [0, 0], [3, 4], OK)).toEqual({
          ok: false,
          kind: "InvalidDEM",
          field: "z",
          cell: first,
          count,
        });
      });
    }
  }
  it("FR-007-36 · non-finite cells inside the nodata mask are allowed and never entered", () => {
    const d = flat(3, 5);
    d.z[1 * 5 + 2] = Number.NaN;
    d.z[0 * 5 + 2] = Number.POSITIVE_INFINITY;
    d.nodata = new Uint8Array(15);
    d.nodata[1 * 5 + 2] = 1;
    d.nodata[0 * 5 + 2] = 1;
    const r = findRoute(d, [0, 0], [2, 4], OK);
    expect(r.ok && r.kind === "route").toBe(true);
    if (r.ok && r.kind === "route") {
      expect(Number.isFinite(r.cost_j)).toBe(true);
      for (const [row, col] of r.cells) expect(d.nodata[row * 5 + col]).toBe(0);
    }
  });
  const sizes: number[] = [0, -1, -0, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY];
  for (const cell of sizes) {
    it(`FR-007-36 · cell size ${String(cell)} is InvalidDEM (cell_m)`, () => {
      expect(findRoute(flat(4, 5, cell), [0, 0], [1, 1], OK)).toMatchObject({
        ok: false,
        kind: "InvalidDEM",
        field: "cell_m",
      });
    });
  }
  for (const [rows, cols] of [
    [1025, 1025],
    [1, 1_048_577],
    [1_048_577, 1],
    [2048, 513],
  ] as [number, number][]) {
    it(`FR-007-36 · ${rows} x ${cols} cells exceeds the browser limit of 1024 x 1024`, () => {
      const r = findRoute({ z: new Float64Array(rows * cols), rows, cols, cell_m: 10 }, [0, 0], [0, 0], OK);
      expect(r).toMatchObject({ ok: false, kind: "InvalidDEM", field: "shape", count: rows * cols });
    });
  }
  it("FR-007-36 · exactly 1024 x 1024 cells is accepted", () => {
    const d: Dem = { z: new Float64Array(1024 * 1024), rows: 1024, cols: 1024, cell_m: 10 };
    expect(findRoute(d, [5, 5], [5, 5], OK)).toMatchObject({
      ok: true,
      kind: "route",
      cells: [[5, 5]],
      cost_j: 0,
    });
  });
  const malformed: [string, Dem][] = [
    ["a length that is not rows x cols", { z: new Float64Array(19), rows: 4, cols: 5, cell_m: 10 }],
    ["zero rows", { z: new Float64Array(0), rows: 0, cols: 5, cell_m: 10 }],
    ["a fractional row count", { z: new Float64Array(20), rows: 4.5, cols: 5, cell_m: 10 }],
    [
      "a nodata mask of another length",
      { z: new Float64Array(20), rows: 4, cols: 5, cell_m: 10, nodata: new Uint8Array(19) },
    ],
  ];
  for (const [name, d] of malformed) {
    it(`FR-007-36 · ${name} is an InvalidDEM and not an exception`, () => {
      expect(findRoute(d, [0, 0], [0, 0], OK)).toMatchObject({ ok: false, kind: "InvalidDEM" });
    });
  }
});

describe("FR-007-36 · hostile requests", () => {
  const gm = [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, 0, -0.1, 1.000001, 2];
  for (const g_max of gm) {
    it(`FR-007-36 · g_max ${String(g_max)} is InvalidRouteRequest`, () => {
      expect(findRoute(flat(), [0, 0], [1, 1], { ...OK, g_max })).toMatchObject({
        ok: false,
        kind: "InvalidRouteRequest",
        field: "g_max",
      });
    });
  }
  for (const g_max of [1, 0.5, 1e-9]) {
    it(`FR-007-36 · g_max ${String(g_max)} is accepted`, () => {
      expect(findRoute(flat(), [0, 0], [1, 1], { ...OK, g_max })).toMatchObject({ ok: true, kind: "route" });
    });
  }
  const outside: [number, number][] = [
    [-1, 0],
    [0, -1],
    [4, 0],
    [0, 5],
    [4, 5],
    [100, 100],
  ];
  for (const cell of outside) {
    for (const which of ["start", "goal"] as const) {
      it(`FR-007-36 · ${which} ${JSON.stringify(cell)} outside the grid names the field`, () => {
        const s: [number, number] = which === "start" ? cell : [1, 1];
        const g: [number, number] = which === "goal" ? cell : [1, 1];
        expect(findRoute(flat(), s, g, OK)).toMatchObject({
          ok: false,
          kind: "InvalidRouteRequest",
          field: which,
        });
      });
    }
  }
  it("FR-007-36 · an endpoint on a nodata cell is InvalidRouteRequest", () => {
    const d = flat();
    d.nodata = new Uint8Array(20);
    d.nodata[2 * 5 + 3] = 1;
    expect(findRoute(d, [2, 3], [0, 0], OK)).toMatchObject({
      ok: false,
      kind: "InvalidRouteRequest",
      field: "start",
    });
    expect(findRoute(d, [0, 0], [2, 3], OK)).toMatchObject({
      ok: false,
      kind: "InvalidRouteRequest",
      field: "goal",
    });
  });
  const bad: unknown[] = [[0.5, 1], ["0", "0"], [null, null], [0], [0, 0, 0], "00", null, 7, [Number.NaN, 0]];
  for (const b of bad) {
    it(`FR-007-36 · a malformed start ${JSON.stringify(b)} is InvalidRouteRequest`, () => {
      expect(findRoute(flat(), b as [number, number], [1, 1], OK)).toMatchObject({
        ok: false,
        kind: "InvalidRouteRequest",
        field: "start",
      });
    });
  }
  const params: [string, number][] = [
    ["mass_kg", 0],
    ["mass_kg", -1],
    ["mass_kg", Number.NaN],
    ["rr_pct", -0.1],
    ["rr_pct", Number.POSITIVE_INFINITY],
    ["eta", 0],
    ["eta", 1.0000001],
    ["eta", Number.NaN],
    ["g", 0],
    ["g", Number.NaN],
  ];
  for (const [field, v] of params) {
    it(`FR-007-45 · ${field} = ${String(v)} is InvalidRouteRequest naming the field`, () => {
      expect(findRoute(flat(), [0, 0], [1, 1], { ...OK, [field]: v })).toMatchObject({
        ok: false,
        kind: "InvalidRouteRequest",
        field,
      });
    });
  }
  it("FR-007-37 · an unreachable goal is a value, not an error, even next to a nodata wall", () => {
    const d = flat();
    d.nodata = new Uint8Array(20);
    for (let r = 0; r < 4; r++) d.nodata[r * 5 + 2] = 1;
    expect(findRoute(d, [0, 0], [3, 4], OK)).toMatchObject({ ok: true, kind: "no-feasible-route" });
  });
});

describe("NFR-007-04 · A* on a 512 x 512 grid", () => {
  const N = 512;
  const dem = (): Dem => {
    const z = new Float64Array(N * N);
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) z[i * N + j] = ((i * 131 + j * 71) % 509) / 1024; // dyadic, within 0.5 m: grades below 5 % on 10 m cells
    return { z, rows: N, cols: N, cell_m: 10 };
  };
  it("NFR-007-04 · routes corner to corner in at most 1 s with a valid 8-neighbour path", () => {
    findRoute(demWarm(), [0, 0], [15, 15], OK); // warm-up of the JIT on a small grid
    const d = dem();
    const t0 = performance.now();
    const r = findRoute(d, [0, 0], [N - 1, N - 1], { ...OK, g_max: 0.2 });
    const ms = performance.now() - t0;
    expect(r.ok && r.kind === "route").toBe(true);
    if (!(r.ok && r.kind === "route")) return;
    expect(r.cells[0]).toEqual([0, 0]);
    expect(r.cells[r.cells.length - 1]).toEqual([N - 1, N - 1]);
    for (let k = 1; k < r.cells.length; k++) {
      const a = r.cells[k - 1] as [number, number];
      const b = r.cells[k] as [number, number];
      expect(Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]))).toBe(1);
    }
    expect(Number.isFinite(r.cost_j) && r.cost_j > 0).toBe(true);
    expect(r.expanded).toBeLessThanOrEqual(N * N);
    expect(ms).toBeLessThanOrEqual(1000);
  });
  it("NFR-007-04 · an unreachable goal on the same grid is also answered within 1 s", () => {
    const d = dem();
    d.nodata = new Uint8Array(N * N);
    for (let i = 0; i < N; i++) d.nodata[i * N + 256] = 1; // a full wall
    const t0 = performance.now();
    const r = findRoute(d, [0, 0], [N - 1, N - 1], { ...OK, g_max: 0.2 });
    expect(performance.now() - t0).toBeLessThanOrEqual(1000);
    expect(r).toMatchObject({ ok: true, kind: "no-feasible-route" });
    if (r.ok && r.kind === "no-feasible-route") expect(r.expanded).toBeLessThanOrEqual(N * 256);
  });
});

function demWarm(): Dem {
  const z = new Float64Array(256);
  for (let i = 0; i < 256; i++) z[i] = (i % 7) / 1024;
  return { z, rows: 16, cols: 16, cell_m: 10 };
}
