// @vitest-environment node
//
// T-007-030 (TypeScript half) · the TypeScript M1 port equals the golden vectors within rtol 1e-12, atol 1e-15; hostile inputs return typed results, never NaN or Infinity: FR-007-15, FR-007-16.
//
// Spec: specs/007-haulage-dispatch/spec.md FR-007-15 (the fleet-sizing engine computes the match factor, M/M/1//N (pi_0, U, X), open M/M/c (C, W_q, L_q) and exact MVA; the TypeScript port equals
// `minephys.haulage` on the committed golden vectors within rtol 1e-12, atol 1e-15), FR-007-16 (a non-finite input, N_T or N_L not a positive integer, a rate or time <= 0, or N_T > 400 returns
// `InvalidInput` naming the field; rho >= 1 for open M/M/c returns `Unstable`; never NaN or Infinity), plan.md ("M/M/1//N via a running product (no `pow`), Erlang C, MVA; typed errors").
//
// Oracle: the committed golden file tests/fixtures/haulage/m1_goldens.json (numbers from `minephys.haulage`, themselves checked against closed forms in tests/parity/test_t_007_030_m1_goldens.py; it
// holds the spec section 7 worked examples); the tolerances of the spec.
//
// Expected API (module `~/engines/haulage/queueing`), every function takes the snake_case object of the golden `input` and returns a `Result`:
//   type Result<T> = { ok: true; value: T } | { ok: false; kind: "InvalidInput"; field: string } | { ok: false; kind: "Unstable" }
//   matchFactor(i: {n_trucks, n_loaders, load_time, cycle_time}): Result<number>
//   finiteSourceQueue(i: {n_trucks, travel_rate, service_rate}): Result<{idle_probability, utilisation, throughput, mean_at_loader, mean_time_at_loader}>
//   mmcQueue(i: {arrival_rate, service_rate, servers}): Result<{utilisation, erlang_c, mean_wait, mean_queue_length, mean_time_in_system, mean_in_system}>
//   meanValueAnalysis(i: {population, service_time: number[], visit_ratio: number[], station_type: ("queue" | "delay")[]}): Result<{throughput: number[], residence_time: number[], queue_length: number[], utilisation: number[]}>
//   Arguments are validated in the order of the golden `input` keys; the first failing one is named; `Unstable` is returned after the arguments are valid.

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { finiteSourceQueue, matchFactor, meanValueAnalysis, mmcQueue } from "~/engines/haulage/queueing";

const REPO = resolve(fileURLToPath(new URL(".", import.meta.url)), "../../../..");
// biome-ignore lint/suspicious/noExplicitAny: golden JSON
type Json = Record<string, any>;
const g = JSON.parse(
  readFileSync(resolve(REPO, "tests/fixtures/haulage/m1_goldens.json"), "utf-8"),
) as Record<string, Json[]>;
const RTOL = 1e-12;
const ATOL = 1e-15;
const close = (a: number, b: number) => Math.abs(a - b) <= ATOL + RTOL * Math.abs(b);
const decode = (x: unknown): unknown => {
  if (x === "NaN") return Number.NaN;
  if (x === "Infinity") return Number.POSITIVE_INFINITY;
  if (x === "-Infinity") return Number.NEGATIVE_INFINITY;
  if (Array.isArray(x)) return x.map(decode);
  return x;
};
const decodeInput = (i: Json): Json => Object.fromEntries(Object.entries(i).map(([k, v]) => [k, decode(v)]));

function value<T>(r: { ok: boolean; value?: T }): T {
  expect(r.ok).toBe(true);
  return r.value as T;
}
function finiteDeep(x: unknown): boolean {
  if (typeof x === "number") return Number.isFinite(x);
  if (Array.isArray(x)) return x.every(finiteDeep);
  if (x && typeof x === "object") return Object.values(x).every(finiteDeep);
  return true;
}

describe("the golden vectors", () => {
  it("FR-007-15 · the file has vectors of every model", () => {
    expect(g.match_factor?.length).toBeGreaterThanOrEqual(15);
    expect(g.finite_source?.length).toBeGreaterThanOrEqual(25);
    expect(g.mmc?.length).toBeGreaterThanOrEqual(25);
    expect(g.mva?.length).toBeGreaterThanOrEqual(10);
    expect(g.hostile?.length).toBeGreaterThanOrEqual(40);
  });

  it("FR-007-15 · match factor equals minephys within rtol 1e-12", () => {
    for (const v of g.match_factor as Json[])
      expect(
        close(value<number>(matchFactor(v.input as never)), v.expected as number),
        JSON.stringify(v.input),
      ).toBe(true);
  });

  it("FR-007-15 · M/M/1//N equals minephys within rtol 1e-12", () => {
    for (const v of g.finite_source as Json[]) {
      const got = value<Record<string, number>>(finiteSourceQueue(v.input as never));
      for (const [k, want] of Object.entries(v.expected as Record<string, number>))
        expect(close(got[k] as number, want), `${JSON.stringify(v.input)} ${k}: ${got[k]} vs ${want}`).toBe(
          true,
        );
    }
  });

  it("FR-007-15 · open M/M/c equals minephys within rtol 1e-12", () => {
    for (const v of g.mmc as Json[]) {
      const got = value<Record<string, number>>(mmcQueue(v.input as never));
      for (const [k, want] of Object.entries(v.expected as Record<string, number>))
        expect(close(got[k] as number, want), `${JSON.stringify(v.input)} ${k}: ${got[k]} vs ${want}`).toBe(
          true,
        );
    }
  });

  it("FR-007-15 · exact MVA equals minephys within rtol 1e-12", () => {
    for (const v of g.mva as Json[]) {
      const got = value<Record<string, number[]>>(meanValueAnalysis(v.input as never));
      for (const [k, want] of Object.entries(v.expected as Record<string, number[]>)) {
        const a = got[k] as number[];
        expect(a.length, `${k} length`).toBe(want.length);
        for (const [i, w] of want.entries()) {
          expect(
            close(a[i] as number, w),
            `population ${v.input.population} ${k}[${i}]: ${a[i]} vs ${w}`,
          ).toBe(true);
        }
      }
    }
  });

  it("FR-007-15 · the spec worked examples are reproduced", () => {
    const fs = Object.fromEntries(
      (g.finite_source as Json[])
        .filter((v) => v.source === "spec-007-worked-example")
        .map((v) => [v.input.n_trucks, v]),
    );
    const r8 = value<Record<string, number>>(finiteSourceQueue((fs[8] as Json).input as never));
    expect(r8.idle_probability).toBeCloseTo(0.17882, 5);
    expect(r8.throughput * 3600).toBeCloseTo(16.424, 3);
    const r5 = value<Record<string, number>>(finiteSourceQueue((fs[5] as Json).input as never));
    expect(r5.idle_probability).toBeCloseTo(0.28487, 5);
    expect(r5.throughput * 3600).toBeCloseTo(10.727, 3);
    for (const [n, perHour] of [
      [1, 2.5],
      [3, 7.06],
      [5, 10.727],
      [6, 12.12],
      [8, 13.95],
    ] as [number, number][]) {
      const r = value<{ throughput: number[] }>(
        meanValueAnalysis({
          population: n,
          service_time: [240, 1200],
          visit_ratio: [1, 1],
          station_type: ["queue", "delay"],
        }),
      );
      expect((r.throughput[n - 1] as number) * 3600).toBeCloseTo(perHour, 2);
    }
  });

  it("FR-007-15 · no result of a valid vector contains NaN or Infinity", () => {
    for (const v of g.finite_source as Json[])
      expect(finiteDeep(value(finiteSourceQueue(v.input as never)))).toBe(true);
    for (const v of g.mmc as Json[]) expect(finiteDeep(value(mmcQueue(v.input as never)))).toBe(true);
    for (const v of g.mva as Json[])
      expect(finiteDeep(value(meanValueAnalysis(v.input as never)))).toBe(true);
  });

  it("FR-007-15 · the model is evaluated without Math.pow (a running product): N = 100,000-scale inputs stay finite", () => {
    const r = finiteSourceQueue({ n_trucks: 400, travel_rate: 0.5, service_rate: 0.001 });
    expect(r.ok && finiteDeep(r.value)).toBe(true);
  });
});

describe("hostile inputs (FR-007-16)", () => {
  const fns: Record<string, (i: never) => unknown> = {
    match_factor: matchFactor,
    finite_source: finiteSourceQueue,
    mmc: mmcQueue,
    mva: meanValueAnalysis,
  };
  for (const [idx, h] of (g.hostile as Json[]).entries()) {
    it(`FR-007-16 · #${idx} ${h.fn} ${JSON.stringify(h.input).slice(0, 90)} returns ${JSON.stringify(h.expected)}`, () => {
      const r = (fns[h.fn] as (i: never) => Json)(decodeInput(h.input as Json) as never);
      expect(r.ok).toBe(false);
      expect(r.kind).toBe(h.expected.kind);
      if (h.expected.field) expect(r.field).toBe(h.expected.field);
      expect(JSON.stringify(r)).not.toMatch(/NaN|Infinity/);
    });
  }

  it("FR-007-16 · a typed result, never an exception, for every hostile vector", () => {
    for (const h of g.hostile as Json[])
      expect(() => (fns[h.fn] as (i: never) => unknown)(decodeInput(h.input as Json) as never)).not.toThrow();
  });

  it("FR-007-16 · 400 trucks is valid, 401 is not", () => {
    expect(finiteSourceQueue({ n_trucks: 400, travel_rate: 0.001, service_rate: 0.004 }).ok).toBe(true);
    const r = finiteSourceQueue({ n_trucks: 401, travel_rate: 0.001, service_rate: 0.004 }) as Json;
    expect([r.ok, r.kind, r.field]).toEqual([false, "InvalidInput", "n_trucks"]);
  });
});
