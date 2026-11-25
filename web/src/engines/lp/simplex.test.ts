// @vitest-environment node
//
// T-007-041 · the TypeScript simplex equals the HiGHS fixtures, typed statuses, metamorphic relations, at most 50 ms for up to 64 paths: FR-007-20, FR-007-21, P-007-11, NFR-007-04.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-20 (when the LP status is optimal the TypeScript simplex equals HiGHS on every golden instance: optimum within rtol 1e-7; on non-degenerate instances,
// f_p and the dual values within atol 1e-6), FR-007-21 (an infeasible or unbounded LP, a non-finite coefficient, a negative capacity, T_p <= 0 or no path gives the typed status `infeasible`, `unbounded` or
// `invalid-input` within 1 s), P-007-11 (the four relations: relaxing a capacity never lowers the optimum; scaling every capacity and N_T by k scales it by k; removing a path never raises it; minutes and rates per
// minute divide it by 60), NFR-007-04 (the A1 LP of <= 64 paths in <= 50 ms on tier T2; the Vitest benchmark of the reference machine) and plan.md ("a dense two-phase simplex with Bland's rule").
//
// Oracle: tests/fixtures/haulage/lp_goldens.json: 38 dispatch LPs (the worked example of spec section 7, an infeasible blend floor, 30 random and 4 large instances of up to 48 paths, a degenerate instance) solved by
// `scipy.optimize.linprog(method="highs")` (HiGHS, the reference solver); the hand-calculated worked example (19.5 at (12, 7.5), duals 0.375 / 1.25; 19.2 at (12, 7.2), duals 1.6 / 4); Beale's cycling example
// (optimum 1/20 at (1/25, 0, 1, 0), published in Beale 1955, which a simplex without an anti-cycling rule can loop on); LP duality checks written out below.
//
// Expected API (module `~/engines/lp/simplex`), the same shapes as the Python `pitstudio_pipeline.haulage.lp` (test_t_007_040_lp_highs.py):
//   solveLp(c: number[], aUb: number[][], bUb: number[]): { status: "optimal" | "infeasible" | "unbounded" | "invalid-input"; optimum: number | null; x: number[] | null; duals: number[] | null }
//   solveDispatchLp(i: { paths: {id, loader, dump, margin, trip_time_h}[]; loader_caps: Record<string, number>; dump_caps: Record<string, number>; n_trucks: number; blend_floors?: {terms: {loader, coef}[]; min}[] }):
//     { status; optimum: number | null; flows: Record<string, number> | null; duals: Record<string, number> | null }   dual keys "loader:<node>", "dump:<node>", "fleet", "blend:<k>"
//   Never throws for hostile numbers: the typed status is returned.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { solveDispatchLp, solveLp } from "~/engines/lp/simplex";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
// biome-ignore lint/suspicious/noExplicitAny: fixture JSON
type Json = Record<string, any>;
const gold = JSON.parse(readFileSync(resolve(REPO, "tests/fixtures/haulage/lp_goldens.json"), "utf-8")) as {
  instances: Json[];
};
const input = (i: Json) => ({
  paths: i.paths,
  loader_caps: i.loader_caps,
  dump_caps: i.dump_caps,
  n_trucks: i.n_trucks,
  blend_floors: i.blend_floors,
});
const near = (a: number, b: number, rtol: number, atol = 0) => Math.abs(a - b) <= atol + rtol * Math.abs(b);

describe("FR-007-20 · the HiGHS fixtures", () => {
  it("FR-007-20 · the fixture holds the worked example, large and degenerate instances", () => {
    const ids = gold.instances.map((i) => i.id);
    expect(ids).toContain("worked-example");
    expect(ids).toContain("worked-example-blend");
    expect(Math.max(...gold.instances.map((i) => i.n_paths))).toBeGreaterThanOrEqual(40);
    expect(gold.instances.some((i) => i.expected.degenerate)).toBe(true);
    expect(
      gold.instances.filter((i) => i.expected.status === "optimal" && !i.expected.degenerate).length,
    ).toBeGreaterThanOrEqual(25);
  });

  for (const inst of gold.instances.filter((i) => i.expected.status === "optimal")) {
    it(`FR-007-20 · ${inst.id}: optimum within rtol 1e-7${inst.expected.degenerate ? "" : ", flows and duals within atol 1e-6"}`, () => {
      const r = solveDispatchLp(input(inst));
      const want = inst.expected as Json;
      expect(r.status).toBe("optimal");
      expect(near(r.optimum as number, want.optimum, 1e-7, 1e-9), `${r.optimum} vs ${want.optimum}`).toBe(
        true,
      );
      if (want.degenerate) return;
      for (const [id, f] of Object.entries(want.flows as Record<string, number>))
        expect(
          Math.abs(((r.flows as Record<string, number>)[id] as number) - f),
          `flow ${id}`,
        ).toBeLessThanOrEqual(1e-6);
      for (const [k, y] of Object.entries(want.duals as Record<string, number>))
        expect(
          Math.abs(((r.duals as Record<string, number>)[k] as number) - y),
          `dual ${k}`,
        ).toBeLessThanOrEqual(1e-6);
      expect(Object.keys(r.duals as object).sort()).toEqual(Object.keys(want.duals).sort());
    });
  }

  it("FR-007-21 · the infeasible fixture is the typed status infeasible", () => {
    const inst = gold.instances.find((i) => i.expected.status === "infeasible") as Json;
    const r = solveDispatchLp(input(inst));
    expect(r).toEqual({ status: "infeasible", optimum: null, flows: null, duals: null });
  });
});

describe("the worked example by hand", () => {
  const base = {
    paths: [
      { id: 1, loader: 1, dump: 9, margin: 1, trip_time_h: 0.5 },
      { id: 2, loader: 2, dump: 9, margin: 1, trip_time_h: 0.8 },
    ],
    loader_caps: { 1: 12, 2: 10 },
    dump_caps: { 9: 30 },
    n_trucks: 12,
  };

  it("FR-007-20 · without a blend floor: 19.5 loads/h at (12, 7.5), duals 0.375 (loader 1) and 1.25 (fleet)", () => {
    const r = solveDispatchLp(base);
    expect(r.optimum).toBeCloseTo(19.5, 9);
    expect((r.flows as Record<string, number>)["1"]).toBeCloseTo(12, 9);
    expect((r.flows as Record<string, number>)["2"]).toBeCloseTo(7.5, 9);
    expect((r.duals as Record<string, number>)["loader:1"]).toBeCloseTo(0.375, 9);
    expect((r.duals as Record<string, number>).fleet).toBeCloseTo(1.25, 9);
    expect((r.duals as Record<string, number>)["loader:2"]).toBeCloseTo(0, 9);
    expect((r.duals as Record<string, number>)["dump:9"]).toBeCloseTo(0, 9);
  });

  it("FR-007-20 · with the blend floor 0.15 x1 - 0.25 x2 >= 0: 19.2 at (12, 7.2), duals 1.6 (loader 1) and 4 (blend)", () => {
    const r = solveDispatchLp({
      ...base,
      blend_floors: [
        {
          terms: [
            { loader: 1, coef: 0.15 },
            { loader: 2, coef: -0.25 },
          ],
          min: 0,
        },
      ],
    });
    expect(r.optimum).toBeCloseTo(19.2, 9);
    expect((r.flows as Record<string, number>)["2"]).toBeCloseTo(7.2, 9);
    expect((r.duals as Record<string, number>)["loader:1"]).toBeCloseTo(1.6, 9);
    expect((r.duals as Record<string, number>)["blend:0"]).toBeCloseTo(4, 9);
    expect((r.duals as Record<string, number>).fleet).toBeCloseTo(0, 9);
  });

  it("FR-007-19 · a textbook LP and Beale's cycling example (Bland's rule terminates)", () => {
    const t = solveLp(
      [3, 2],
      [
        [1, 1],
        [1, 3],
        [1, 0],
      ],
      [4, 7, 3],
    );
    expect(t.status).toBe("optimal");
    expect(t.optimum).toBeCloseTo(11, 9);
    for (const [i, y] of [2, 0, 1].entries()) expect(t.duals?.[i]).toBeCloseTo(y, 9);
    const b = solveLp(
      [0.75, -150, 0.02, -6],
      [
        [0.25, -60, -0.04, 9],
        [0.5, -90, -0.02, 3],
        [0, 0, 1, 0],
      ],
      [0, 0, 1],
    );
    expect(b.status).toBe("optimal");
    expect(b.optimum).toBeCloseTo(0.05, 9);
    expect(b.x?.[0]).toBeCloseTo(0.04, 9);
    expect(b.x?.[2]).toBeCloseTo(1, 9);
  });
});

describe("FR-007-21 · typed statuses", () => {
  it("FR-007-21 · infeasible and unbounded generic LPs", () => {
    expect(solveLp([1], [[1]], [-1])).toEqual({ status: "infeasible", optimum: null, x: null, duals: null });
    const u = solveLp([1, 0], [[-1, 1]], [1]);
    expect(u.status).toBe("unbounded");
    expect(u.optimum).toBeNull();
  });

  const base = {
    paths: [
      { id: 1, loader: 1, dump: 9, margin: 1, trip_time_h: 0.5 },
      { id: 2, loader: 2, dump: 9, margin: 1, trip_time_h: 0.8 },
    ],
    loader_caps: { 1: 12, 2: 10 },
    dump_caps: { 9: 30 },
    n_trucks: 12,
  } as Json;
  const p0 = base.paths[0];
  const hostile: [string, Json][] = [
    ["no path", { paths: [] }],
    ["NaN margin", { paths: [{ ...p0, margin: Number.NaN }] }],
    ["infinite margin", { paths: [{ ...p0, margin: Number.POSITIVE_INFINITY }] }],
    ["T = 0", { paths: [{ ...p0, trip_time_h: 0 }] }],
    ["T < 0", { paths: [{ ...p0, trip_time_h: -0.5 }] }],
    ["T NaN", { paths: [{ ...p0, trip_time_h: Number.NaN }] }],
    ["duplicate path id", { paths: [p0, { ...base.paths[1], id: 1 }] }],
    ["loader without capacity", { paths: [{ ...p0, loader: 7 }] }],
    ["dump without capacity", { paths: [{ ...p0, dump: 7 }] }],
    ["negative loader capacity", { loader_caps: { 1: -1, 2: 10 } }],
    ["NaN loader capacity", { loader_caps: { 1: Number.NaN, 2: 10 } }],
    ["negative dump capacity", { dump_caps: { 9: -5 } }],
    ["infinite dump capacity", { dump_caps: { 9: Number.POSITIVE_INFINITY } }],
    ["negative fleet", { n_trucks: -1 }],
    ["NaN fleet", { n_trucks: Number.NaN }],
    ["infinite fleet", { n_trucks: Number.POSITIVE_INFINITY }],
    ["NaN blend coefficient", { blend_floors: [{ terms: [{ loader: 1, coef: Number.NaN }], min: 0 }] }],
    [
      "infinite blend floor",
      { blend_floors: [{ terms: [{ loader: 1, coef: 1 }], min: Number.POSITIVE_INFINITY }] },
    ],
  ];
  for (const [name, patch] of hostile) {
    it(`FR-007-21 · ${name} gives invalid-input within one second, without throwing`, () => {
      const t0 = performance.now();
      const r = solveDispatchLp({ ...base, ...patch } as never);
      expect(r).toEqual({ status: "invalid-input", optimum: null, flows: null, duals: null });
      expect(performance.now() - t0).toBeLessThan(1000);
    });
  }

  it("FR-007-21 · hostile generic inputs give invalid-input", () => {
    for (const a of [
      [[], [], []],
      [[1], [[1, 2]], [1]],
      [[1], [[1]], [Number.NaN]],
      [[Number.POSITIVE_INFINITY], [[1]], [1]],
      [[1], [[Number.NaN]], [1]],
    ] as [number[], number[][], number[]][]) {
      const r = solveLp(...a);
      expect(r.status).toBe("invalid-input");
      expect(r.optimum).toBeNull();
    }
  });

  it("FR-007-21 · a capacity of zero is valid and forces a zero flow", () => {
    const r = solveDispatchLp({ ...base, loader_caps: { 1: 0, 2: 10 } } as never);
    expect(r.status).toBe("optimal");
    expect((r.flows as Record<string, number>)["1"]).toBeCloseTo(0, 12);
    expect(r.optimum).toBeCloseTo(10, 9);
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// P-007-11 on seeded random instances, and duality
// ---------------------------------------------------------------------------------------------------------------------
function mulberry32(a: number) {
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const randInt = (r: () => number, lo: number, hi: number) => lo + Math.floor(r() * (hi - lo + 1));

function randomInstance(r: () => number): Json {
  const nL = randInt(r, 1, 4);
  const nD = randInt(r, 1, 3);
  const paths: Json[] = [];
  let id = 0;
  for (let ld = 1; ld <= nL; ld++) {
    const dumps = new Set<number>([randInt(r, 1, nD)]);
    if (r() < 0.5) dumps.add(randInt(r, 1, nD));
    for (const dp of dumps)
      paths.push({
        id: ++id,
        loader: ld,
        dump: 100 + dp,
        margin: randInt(r, 2, 12) / 4,
        trip_time_h: randInt(r, 2, 30) / 20,
      });
  }
  const loader_caps: Record<string, number> = {};
  for (let ld = 1; ld <= nL; ld++) loader_caps[String(ld)] = randInt(r, 5, 40);
  const dump_caps: Record<string, number> = {};
  for (let dp = 1; dp <= nD; dp++) dump_caps[String(100 + dp)] = randInt(r, 10, 80);
  const blend_floors =
    nL >= 2 && r() < 0.5
      ? [
          {
            terms: [
              { loader: 1, coef: randInt(r, 1, 6) / 20 },
              { loader: 2, coef: -randInt(r, 1, 6) / 20 },
            ],
            min: 0,
          },
        ]
      : [];
  return { paths, loader_caps, dump_caps, n_trucks: randInt(r, 3, 40), blend_floors };
}
const opt = (i: Json) => {
  const r = solveDispatchLp(i as never);
  expect(r.status).toBe("optimal");
  return r.optimum as number;
};

describe("P-007-11 · metamorphic relations (60 seeded instances each)", () => {
  it("P-007-11 · relaxing a capacity never lowers the optimum", () => {
    const r = mulberry32(1);
    for (let k = 0; k < 60; k++) {
      const inst = randomInstance(r);
      const base = opt(inst);
      const d = r() * 20;
      const which = randInt(r, 0, 2);
      const relaxed = structuredClone(inst);
      if (which === 0) relaxed.loader_caps[String(randInt(r, 1, Object.keys(inst.loader_caps).length))] += d;
      else if (which === 1) relaxed.dump_caps[Object.keys(inst.dump_caps)[0] as string] += d;
      else relaxed.n_trucks += d;
      expect(opt(relaxed)).toBeGreaterThanOrEqual(base - 1e-9);
    }
  });

  it("P-007-11 · scaling every capacity and N_T by k in {0.5, 2, 3} scales the optimum by k", () => {
    const r = mulberry32(2);
    for (let k = 0; k < 60; k++) {
      const inst = randomInstance(r);
      const f = [0.5, 2, 3][k % 3] as number;
      const s = structuredClone(inst);
      for (const key of Object.keys(s.loader_caps)) s.loader_caps[key] *= f;
      for (const key of Object.keys(s.dump_caps)) s.dump_caps[key] *= f;
      s.n_trucks *= f;
      expect(near(opt(s), f * opt(inst), 1e-7, 1e-9)).toBe(true);
    }
  });

  it("P-007-11 · removing a path never raises the optimum (without blend floors)", () => {
    const r = mulberry32(3);
    for (let k = 0; k < 60; k++) {
      const inst = { ...randomInstance(r), blend_floors: [] };
      if (inst.paths.length < 2) continue;
      const drop = (inst.paths as Json[])[randInt(r, 0, inst.paths.length - 1)]?.id;
      const smaller = { ...inst, paths: (inst.paths as Json[]).filter((p) => p.id !== drop) };
      expect(opt(smaller)).toBeLessThanOrEqual(opt(inst) + 1e-9);
    }
  });

  it("P-007-11 · times in minutes and rates per minute divide the optimum by 60", () => {
    const r = mulberry32(4);
    for (let k = 0; k < 60; k++) {
      const inst = randomInstance(r);
      const m = structuredClone(inst);
      for (const p of m.paths as Json[]) p.trip_time_h *= 60;
      for (const key of Object.keys(m.loader_caps)) m.loader_caps[key] /= 60;
      for (const key of Object.keys(m.dump_caps)) m.dump_caps[key] /= 60;
      expect(near(opt(m), opt(inst) / 60, 1e-7, 1e-12)).toBe(true);
    }
  });

  it("FR-007-19 · the duals of random instances are dual feasible, complementary and give strong duality", () => {
    const r = mulberry32(5);
    for (let k = 0; k < 40; k++) {
      const inst = randomInstance(r);
      const res = solveDispatchLp(inst as never);
      expect(res.status).toBe("optimal");
      const paths = inst.paths as Json[];
      const f = paths.map((p) => (res.flows as Record<string, number>)[String(p.id)] as number);
      const rows: { name: string; a: number[]; b: number }[] = [];
      for (const [ld, cap] of Object.entries(inst.loader_caps as Record<string, number>))
        rows.push({ name: `loader:${ld}`, a: paths.map((p) => (p.loader === Number(ld) ? 1 : 0)), b: cap });
      for (const [dp, cap] of Object.entries(inst.dump_caps as Record<string, number>))
        rows.push({ name: `dump:${dp}`, a: paths.map((p) => (p.dump === Number(dp) ? 1 : 0)), b: cap });
      rows.push({ name: "fleet", a: paths.map((p) => p.trip_time_h), b: inst.n_trucks });
      (inst.blend_floors as Json[]).forEach((bf, i) => {
        const coef = new Map<number, number>((bf.terms as Json[]).map((t) => [t.loader, t.coef]));
        rows.push({ name: `blend:${i}`, a: paths.map((p) => -(coef.get(p.loader) ?? 0)), b: -bf.min });
      });
      let dualObj = 0;
      for (const row of rows) {
        const y = (res.duals as Record<string, number>)[row.name] as number;
        expect(y).toBeGreaterThanOrEqual(-1e-9);
        const use = row.a.reduce((s, a, i) => s + a * (f[i] as number), 0);
        expect(use).toBeLessThanOrEqual(row.b + 1e-7);
        expect(Math.abs(y * (row.b - use))).toBeLessThanOrEqual(1e-6);
        dualObj += y * row.b;
      }
      paths.forEach((p, i) => {
        const reduced =
          p.margin -
          rows.reduce(
            (s, row) =>
              s + ((res.duals as Record<string, number>)[row.name] as number) * (row.a[i] as number),
            0,
          );
        expect(reduced).toBeLessThanOrEqual(1e-7);
        expect(Math.abs((f[i] as number) * reduced)).toBeLessThanOrEqual(1e-6);
      });
      expect(near(dualObj, res.optimum as number, 1e-6, 1e-7)).toBe(true);
    }
  });
});

describe("NFR-007-04 · speed", () => {
  it("NFR-007-04 · the A1 LP with up to 64 paths takes at most 50 ms (median of 9 runs)", () => {
    const r = mulberry32(6);
    const paths: Json[] = [];
    const loader_caps: Record<string, number> = {};
    const dump_caps: Record<string, number> = {};
    for (let ld = 1; ld <= 16; ld++) {
      loader_caps[String(ld)] = randInt(r, 5, 40);
      for (let dp = 1; dp <= 4; dp++) {
        dump_caps[String(100 + dp)] = randInt(r, 60, 200);
        paths.push({
          id: paths.length + 1,
          loader: ld,
          dump: 100 + dp,
          margin: randInt(r, 2, 12) / 4,
          trip_time_h: randInt(r, 2, 30) / 20,
        });
      }
    }
    expect(paths.length).toBe(64);
    const inst = { paths, loader_caps, dump_caps, n_trucks: 60, blend_floors: [] };
    solveDispatchLp(inst as never); // warm up
    const times: number[] = [];
    for (let i = 0; i < 9; i++) {
      const t0 = performance.now();
      const res = solveDispatchLp(inst as never);
      times.push(performance.now() - t0);
      expect(res.status).toBe("optimal");
    }
    times.sort((a, b) => a - b);
    expect(times[4] as number).toBeLessThanOrEqual(50);
  });
});
