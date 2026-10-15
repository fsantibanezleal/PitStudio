// @vitest-environment node
//
// T-007-021 (2/2) · metamorphic relations of the twin: order-preserving relabelling, orientation reversal, time dilation by 2: P-007-06, P-007-07, P-007-08.
//
// Spec: specs/007-haulage-dispatch/spec.md P-007-06 (a strictly increasing relabelling of truck ids gives the identical trace with the ids mapped), P-007-07 (in fast mode without direction zones,
// reversing the stored orientation of a two-way segment (swap a and b, negate the grade, reverse the polyline) leaves the trace unchanged) and P-007-08 (twin: multiplying every length, headway distance
// and duration by 2 (segment lengths, headways, pass, spot and dump times, stagger window, failure times, closure windows, retry intervals, horizon) and dividing accelerations by 2 doubles every event
// time exactly; event order and seq stay the same, tonnes stay identical, and t/h halves; exact because the scaling is a power of two).
//
// Oracle: the relations themselves (the baseline run is the reference of its transformed twin). Dilation note (see the report): the loader-class pass and spot times and the accelerations are not
// bundle fields (the bundle's class parameters must equal the engine pin, FR-007-02), so the twin exposes them through the run option `dilation`, which multiplies pass and spot times by the factor and
// divides the accelerations by it; every bundle field of the list above is scaled by this test.
//
// Expected API: `runShift(bundle, seed, { dilation })` of `~/engines/des/twin` (see twin.parity.test.ts) and `computeKpis` of `~/engines/des/kpi`:
//   computeKpis(trace, { fleet: {id, truck_class}[], loaders: {node, n_spots}[], freeFlowCycleS: Record<string, number>, costRates?: {...} | null, timeUnit?: "s" | "h" }) with the table of
//   tests/pipeline/test_t_007_016_kpi.py (camelCase option names, snake_case table keys as in the Python table).

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { computeKpis } from "~/engines/des/kpi";
import { runShift } from "~/engines/des/twin";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const GOLD = resolve(REPO, "tests/fixtures/haulage/goldens");
const gz = (name: string) => gunzipSync(readFileSync(resolve(GOLD, name))).toString("utf-8");

// biome-ignore lint/suspicious/noExplicitAny: bundles are plain JSON here
type Bundle = Record<string, any>;
type Trace = {
  events: { t_s: number; seq: number; kind: string; truck: number | null; node: number }[];
  cyclelog: { t_s: number; truck: number; node: number; event: string; payload_t: number }[];
  // biome-ignore lint/suspicious/noExplicitAny: scalar results of mixed types
  results: Record<string, any>;
};

function mulberry32(a: number) {
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function goldenBundle(id: string): { bundle: Bundle; seed: number } {
  const idx = JSON.parse(readFileSync(resolve(GOLD, "index.json"), "utf-8")) as {
    goldens: { id: string; bundle: string; seed: number }[];
  };
  const e = idx.goldens.find((g) => g.id === id);
  if (!e) throw new Error(`golden ${id} missing`);
  return { bundle: JSON.parse(gz(e.bundle)), seed: e.seed };
}

function busy(n: number, profileFromGolden = true): { bundle: Bundle; seed: number } {
  const { bundle, seed } = goldenBundle(profileFromGolden ? "sptf-fast-nofail" : "profile-deterministic");
  const b = structuredClone(bundle);
  b.fleet = Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    truck_class: "CAT_793F",
    start_loader: b.loaders[i % b.loaders.length].node,
  }));
  b.horizon_s = 2 * 3600;
  b.kpi_window = { warmup_s: 0 };
  b.failures = null;
  return { bundle: b, seed };
}

const run = (b: Bundle, seed: number, options?: { dilation?: number }) =>
  runShift(b, BigInt(seed), options) as unknown as Trace;

describe("P-007-06 · relabelling", () => {
  it("P-007-06 · a strictly increasing relabelling of truck ids gives the identical trace with the ids mapped", () => {
    const rnd = mulberry32(7);
    for (let k = 0; k < 8; k++) {
      const { bundle, seed } = busy(5);
      const map = new Map<number, number>();
      let acc = Math.floor(rnd() * 50);
      for (const t of bundle.fleet as { id: number }[]) {
        acc += 1 + Math.floor(rnd() * 40);
        map.set(t.id, acc);
      }
      const twin = structuredClone(bundle);
      for (const t of twin.fleet as { id: number }[]) t.id = map.get(t.id) as number;
      const a = run(bundle, seed + k);
      const b = run(twin, seed + k);
      expect(b.events).toEqual(
        a.events.map((e) => ({ ...e, truck: e.truck === null ? null : (map.get(e.truck) as number) })),
      );
      expect(b.cyclelog).toEqual(a.cyclelog.map((r) => ({ ...r, truck: map.get(r.truck) as number })));
      expect(b.results).toEqual(a.results);
    }
  });
});

describe("P-007-07 · orientation reversal", () => {
  it("P-007-07 · reversing the stored orientation of two-way segments leaves the trace unchanged (fast mode)", () => {
    const rnd = mulberry32(11);
    for (let k = 0; k < 8; k++) {
      const { bundle, seed } = busy(6);
      expect(bundle.mode).toBe("fast");
      const twin = structuredClone(bundle);
      let changed = 0;
      for (const s of twin.network.segments as Bundle[]) {
        if (!s.one_way && s.zone_id === null && rnd() < 0.6) {
          [s.a, s.b] = [s.b, s.a];
          s.polyline_m = [...s.polyline_m].reverse();
          s.grade_pct = -s.grade_pct;
          changed++;
        }
      }
      expect(changed).toBeGreaterThan(0);
      const a = run(bundle, seed + k);
      const b = run(twin, seed + k);
      expect(b.events).toEqual(a.events);
      expect(b.cyclelog).toEqual(a.cyclelog);
      expect(b.results).toEqual(a.results);
    }
  });
});

function dilate(b: Bundle, f: number): Bundle {
  const d = structuredClone(b);
  for (const s of d.network.segments as Bundle[]) s.length_m *= f;
  for (const j of d.network.junctions as Bundle[]) j.cross_s *= f;
  const c = d.engine_constants as Record<string, number>;
  for (const k of ["stagger_window_s", "dump_mean_s", "closure_retry_s", "headway_m", "headway_s"])
    c[k] = (c[k] as number) * f;
  d.horizon_s *= f;
  d.kpi_window.warmup_s *= f;
  if (d.failures) {
    for (const k of ["truck_mtbf_h", "truck_repair_mean_s", "loader_mtbf_h", "loader_repair_mean_s"])
      d.failures[k] *= f;
    for (const w of d.failures.closures as Bundle[]) {
      w.start_s *= f;
      w.duration_s *= f;
    }
  }
  return d;
}

describe("P-007-08 · time dilation by 2", () => {
  for (const id of ["sptf-fast-nofail", "profile-deterministic", "nearest-fast-fail"]) {
    it(`P-007-08 · ${id}: every event time doubles exactly, order and seq stay, tonnes stay`, () => {
      const { bundle, seed } = goldenBundle(id);
      const a = run(bundle, seed);
      const b = run(dilate(bundle, 2), seed, { dilation: 2 });
      expect(b.events.length).toBe(a.events.length);
      b.events.forEach((e, i) => {
        const x = a.events[i] as Trace["events"][number];
        expect(Object.is(e.t_s, 2 * x.t_s)).toBe(true);
        expect([e.seq, e.kind, e.truck, e.node]).toEqual([x.seq, x.kind, x.truck, x.node]);
      });
      b.cyclelog.forEach((r, i) => {
        const x = a.cyclelog[i] as Trace["cyclelog"][number];
        expect(Object.is(r.t_s, 2 * x.t_s)).toBe(true);
        expect([r.truck, r.node, r.event, r.payload_t]).toEqual([x.truck, x.node, x.event, x.payload_t]);
      });
      expect(b.results.tonnes_t).toBe(a.results.tonnes_t);
      expect(b.results.cycles).toBe(a.results.cycles);
      expect(b.results.events_executed).toBe(a.results.events_executed);
    });
  }

  it("P-007-08 · t/h halves", () => {
    const { bundle, seed } = goldenBundle("sptf-fast-nofail");
    const opts = (b: Bundle) => ({
      fleet: (b.fleet as Bundle[]).map((t) => ({ id: t.id, truck_class: t.truck_class })),
      loaders: (b.loaders as Bundle[]).map((l) => ({ node: l.node, n_spots: l.n_spots })),
      freeFlowCycleS: { CAT_793F: 1500 },
    });
    const a = computeKpis(run(bundle, seed), opts(bundle));
    const d = dilate(bundle, 2);
    const b = computeKpis(run(d, seed, { dilation: 2 }), { ...opts(d), freeFlowCycleS: { CAT_793F: 3000 } });
    expect(b.fleet.production_tph).toBeCloseTo(a.fleet.production_tph / 2, 9);
    expect(b.fleet.tonnes_t).toBe(a.fleet.tonnes_t);
  });
});
