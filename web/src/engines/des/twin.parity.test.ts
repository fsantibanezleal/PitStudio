// @vitest-environment node
//
// T-007-021 (1/2) · the TypeScript DES twin is bit-identical to every golden: FR-007-10.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-10 (for every golden scenario the TypeScript DES twin emits an event trace and cyclelog identical to the Python reference: the same number of events;
// for every event the same t (float64 bit pattern), seq, kind, truck and node; the same cyclelog rows, including payload bit patterns; the same executed-event count; and the same scalar results
// (tonnes, cycles, truck wait, per-loader wait, downtime) bit for bit), FR-007-11 (the golden set), P-007-05 (the same (bundle, seed, dispatcher, profile) gives the same trace) and plan.md ("The golden
// traces come from the reference engine, never from the twin").
//
// Oracle: the golden traces committed in tests/fixtures/haulage/goldens/ (written by the Python adapter over the reference engine, test_t_007_020_golden_coverage.py); `Object.is` on every float64 (the
// bit pattern, distinguishing -0 and NaN); the golden bundle bytes as written.
//
// Expected API (module `~/engines/des/twin`; errors in `~/engines/des/errors`):
//   runShift(bundle: unknown, seed: bigint | number, options?: { eventBudget?: number; dilation?: number }): DesTrace
//     a parsed bundle (the twin validates it with the rules of `scenario.ts`), a seed (bigint, or a safe non-negative integer number), returns a trace shaped like the Python one:
//     { schema_version, header, events: {t_s, seq, kind, truck, node}[], cyclelog: {t_s, truck, node, event, payload_t}[], results: {tonnes_t, cycles, truck_wait_s, loader_wait_s: {loader, wait_s}[],
//       events_executed, downtime} }; `header` equals the Python header of the same run except `producer`, which is "typescript-twin"; `eventBudget` defaults to 2,000,000.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { runShift } from "~/engines/des/twin";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
const GOLD = resolve(REPO, "tests/fixtures/haulage/goldens");

type Entry = {
  id: string;
  bundle: string;
  trace: string;
  seed: number;
  dispatcher: string;
  mode: string;
  failures: boolean;
  variate_profile: string;
  features: string[];
};
const index = JSON.parse(readFileSync(resolve(GOLD, "index.json"), "utf-8")) as {
  engine_pin_sha256: string;
  goldens: Entry[];
};
const gz = (name: string) => gunzipSync(readFileSync(resolve(GOLD, name))).toString("utf-8");

type Trace = {
  header: Record<string, unknown>;
  events: { t_s: number; seq: number; kind: string; truck: number | null; node: number | null }[];
  cyclelog: { t_s: number; truck: number; node: number; event: string; payload_t: number }[];
  results: {
    tonnes_t: number;
    cycles: number;
    truck_wait_s: number;
    loader_wait_s: { loader: number; wait_s: number }[];
    events_executed: number;
    downtime: {
      truck_s: { truck: number; downtime_s: number }[];
      loader_s: { loader: number; downtime_s: number }[];
    } | null;
  };
};

function firstDifference(a: Trace, b: Trace): string | null {
  if (a.events.length !== b.events.length) return `event count ${a.events.length} != ${b.events.length}`;
  for (let i = 0; i < a.events.length; i++) {
    const x = a.events[i];
    const y = b.events[i];
    if (!x || !y) return `event ${i} missing`;
    if (
      !Object.is(x.t_s, y.t_s) ||
      x.seq !== y.seq ||
      x.kind !== y.kind ||
      x.truck !== y.truck ||
      x.node !== y.node
    )
      return `event ${i}: ${JSON.stringify(x)} != ${JSON.stringify(y)}`;
  }
  if (a.cyclelog.length !== b.cyclelog.length)
    return `cyclelog length ${a.cyclelog.length} != ${b.cyclelog.length}`;
  for (let i = 0; i < a.cyclelog.length; i++) {
    const x = a.cyclelog[i];
    const y = b.cyclelog[i];
    if (!x || !y) return `cyclelog row ${i} missing`;
    if (
      !Object.is(x.t_s, y.t_s) ||
      x.truck !== y.truck ||
      x.node !== y.node ||
      x.event !== y.event ||
      !Object.is(x.payload_t, y.payload_t)
    )
      return `cyclelog row ${i}: ${JSON.stringify(x)} != ${JSON.stringify(y)}`;
  }
  const r = a.results;
  const s = b.results;
  if (r.events_executed !== s.events_executed)
    return `events_executed ${r.events_executed} != ${s.events_executed}`;
  if (
    !Object.is(r.tonnes_t, s.tonnes_t) ||
    r.cycles !== s.cycles ||
    !Object.is(r.truck_wait_s, s.truck_wait_s)
  )
    return "scalar results differ";
  if (
    r.loader_wait_s.length !== s.loader_wait_s.length ||
    r.loader_wait_s.some(
      (w, i) => w.loader !== s.loader_wait_s[i]?.loader || !Object.is(w.wait_s, s.loader_wait_s[i]?.wait_s),
    )
  )
    return "per-loader waits differ";
  if (JSON.stringify(r.downtime) !== JSON.stringify(s.downtime)) return "downtime differs";
  return null;
}

describe("the golden set", () => {
  it("FR-007-11 · the index lists the 30 goldens of the coverage matrix", () => {
    expect(index.goldens.length).toBe(30);
  });
});

describe("FR-007-10 · the twin reproduces every golden bit for bit", () => {
  for (const e of index.goldens) {
    it(`FR-007-10 · ${e.id}`, () => {
      const golden = JSON.parse(gz(e.trace)) as Trace;
      const bundle = JSON.parse(gz(e.bundle));
      const got = runShift(bundle, BigInt(e.seed)) as unknown as Trace;
      expect(firstDifference(got, golden)).toBeNull();
      expect({ ...got.header, producer: "python-reference" }).toEqual(golden.header);
      expect(got.header.producer).toBe("typescript-twin");
    });
  }
});

describe("P-007-05 · determinism", () => {
  it("P-007-05 · two runs of the same (bundle, seed) in one process give identical traces", () => {
    const e = index.goldens.find((g) => g.id === "sptf-fast-nofail");
    expect(e).toBeDefined();
    const bundle = JSON.parse(gz((e as Entry).bundle));
    const a = JSON.stringify(runShift(bundle, BigInt((e as Entry).seed)));
    const b = JSON.stringify(runShift(JSON.parse(gz((e as Entry).bundle)), BigInt((e as Entry).seed)));
    expect(a).toBe(b);
  });

  it("FR-007-10 · a number seed and the equal bigint seed give the same trace", () => {
    const e = index.goldens.find((g) => g.id === "profile-deterministic") as Entry;
    const bundle = JSON.parse(gz(e.bundle));
    expect(JSON.stringify(runShift(bundle, e.seed))).toBe(JSON.stringify(runShift(bundle, BigInt(e.seed))));
  });
});
