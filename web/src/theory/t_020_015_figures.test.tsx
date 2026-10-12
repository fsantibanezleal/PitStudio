// T-020-015 [red] · FR-020-06 (each theory page contains the interactive figure(s) listed for it in spec section 7.1, each driven by the engine named there), FR-020-08 (every chart draws as a labelled marker each feature its engine reports
// for that figure, and the marker label shows the same number, with the same rounding, as the read-out panel) and FR-020-13 (a change of any control changes the plotted data within 100 ms, the SHA-256 digest of the plotted series differing
// between the two settings, for every control of every figure). E2E half (all 15 figures on their pages, timing): web/e2e/t_020_015_figures.spec.ts.
//
// Expected API (web/src/theory/):
//   figures.ts      FIGURES: FigureEntry[]   the figure registry of DC-020-04 (figures.yaml) in the order of spec section 7.1: haulage-speed-grade, fee-force-depth, psd-kuzram-swebrec, inverse-velocity, fos-cohesion, beverloo-discharge,
//                   bond-energy, plume-ground-field, ritter-dam-break, nested-pits, lidar-range-dust, ppo-clip, mcnemar, c2st-auc, paired-ci; each { id, topic, engine: { kind: "engine" | "teaching", id }, controls[], features[] }
//                   with the control kinds of the schema (range: id, unit, min, max, step, default; choice: id, options, default);
//   compute.ts      computeFigure(id: string, values: Record<string, number | string>): { series: Array<{ id: string; x: Float64Array; y: Float64Array }>; features: Record<string, { value: number; unit: string }> }
//                   for the figures driven by a teaching function (beverloo-discharge, ritter-dam-break, lidar-range-dust, ppo-clip, mcnemar, c2st-auc, paired-ci); a missing value takes the control's default;
//                   seriesDigest(series: Float64Array[]): string   the lower-case hex SHA-256 of the concatenation of the little-endian IEEE 754 bytes of the arrays;
//   Figure.tsx      Figure({ id: string; values?: Record<string, number | string> }) rendering `[data-testid="figure"][data-figure][data-digest]` (the digest of the plotted series), one `input[data-control="<id>"]` or
//                   `select[data-control="<id>"]` per control (with data-min, data-max and data-unit for a range), one `[data-testid="chart-marker"][data-feature="<id>"]` per feature of the figure holding the label text, and
//                   `[data-testid="figure-readout"]` with one `[data-feature="<id>"]` item per feature holding the same text as its marker.
// Control and feature ids fixed by this test for the three figures it drives by value (the registry of this task must use them): ppo-clip: clip_epsilon (range 0.05..0.5) and advantage_sign (choice positive, negative); features clip_low, clip_high;
// ritter-dam-break: h0 (m), t (s); features front, dam_depth; beverloo-discharge: D (m), d (mm), C, k, rho_b (kg/m3); features no_flow_diameter, operating_point.
// Oracles: the figure table of spec section 7.1 (ids, topics, engines, number of controls and units, number of marked features, written out below by hand), the closed forms (1 -/+ eps; 2 sqrt(g h0) t and 4 h0 / 9; k d), the SHA-256 of known byte
// strings (node:crypto), hand variations.
import { createHash } from "node:crypto";
import { fireEvent, screen } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { renderApp } from "~/test-support/render";
import { computeFigure, seriesDigest } from "~/theory/compute";
import { Figure } from "~/theory/Figure";
import { FIGURES } from "~/theory/figures";

const TABLE: Array<[string, string, "engine" | "teaching", string, number, number]> = [
  // id, topic, engine kind, engine id, number of controls, number of marked features
  ["haulage-speed-grade", "haulage", "engine", "haulage", 3, 2],
  ["fee-force-depth", "loading-and-terramechanics", "engine", "il2-twin", 3, 1],
  ["psd-kuzram-swebrec", "drill-and-blast", "engine", "blasting", 3, 3],
  ["inverse-velocity", "slopes-and-monitoring", "engine", "geotech", 2, 2],
  ["fos-cohesion", "slopes-and-monitoring", "engine", "geotech", 2, 1],
  ["beverloo-discharge", "bulk-flow-dem-mpm", "teaching", "beverloo", 5, 2],
  ["bond-energy", "comminution", "engine", "comminution", 3, 2],
  ["plume-ground-field", "dust", "engine", "plume", 4, 2],
  ["ritter-dam-break", "tailings", "teaching", "ritter", 2, 2],
  ["nested-pits", "planning", "engine", "mincut", 2, 2],
  ["lidar-range-dust", "rtx-sensor-physics", "teaching", "lidarRange", 3, 1],
  ["ppo-clip", "robot-learning", "teaching", "ppoClip", 2, 2],
  ["mcnemar", "vision-language-reasoning", "teaching", "mcnemar", 2, 2],
  ["c2st-auc", "sim-to-real", "teaching", "gaussianAuc", 1, 1],
  ["paired-ci", "sim-to-real", "teaching", "pairedTCi", 3, 1],
];
const G = 9.80665;

describe("the figure registry against section 7.1 (FR-020-06)", () => {
  it("FR-020-06 · the registry lists the 15 figures of the table, in order", () => {
    expect(FIGURES.map((f) => f.id)).toEqual(TABLE.map((r) => r[0]));
  });

  for (const [id, topic, kind, engine, controls, features] of TABLE) {
    it(`FR-020-06 · ${id}: topic ${topic}, driven by the ${kind} function ${engine}, ${controls} controls, ${features} marked features`, () => {
      const f = FIGURES.find((x) => x.id === id);
      expect(f?.topic).toBe(topic);
      expect(f?.engine).toEqual({ kind, id: engine });
      expect(f?.controls).toHaveLength(controls);
      expect(f?.features).toHaveLength(features);
    });
  }

  it("FR-020-06 · every theory page of the 13 has at least one figure", () => {
    const topics = new Set(FIGURES.map((f) => f.topic));
    expect([...topics].sort()).toEqual([
      "bulk-flow-dem-mpm",
      "comminution",
      "drill-and-blast",
      "dust",
      "haulage",
      "loading-and-terramechanics",
      "planning",
      "robot-learning",
      "rtx-sensor-physics",
      "sim-to-real",
      "slopes-and-monitoring",
      "tailings",
      "vision-language-reasoning",
    ]);
  });

  it("FR-020-06 · the units of the controls are those of the table: the Beverloo figure has m, mm, 1, 1 and kg/m3; the Ritter figure m and s; the PPO figure a dimensionless clip and a choice", () => {
    const units = (id: string) =>
      (FIGURES.find((f) => f.id === id)?.controls ?? [])
        .filter((c) => c.kind === "range")
        .map((c) => (c as { unit: string }).unit)
        .sort();
    expect(units("beverloo-discharge")).toEqual(["kg/m³", "m", "mm", "–", "–"].sort());
    expect(units("ritter-dam-break")).toEqual(["m", "s"]);
    expect(units("ppo-clip")).toEqual(["–"]);
    expect(
      (FIGURES.find((f) => f.id === "ppo-clip")?.controls ?? []).filter((c) => c.kind === "choice"),
    ).toHaveLength(1);
    expect(
      (FIGURES.find((f) => f.id === "haulage-speed-grade")?.controls ?? []).filter(
        (c) => c.kind === "choice",
      )[0],
    ).toMatchObject({ options: expect.arrayContaining(["diesel", "trolley", "battery-electric"]) });
  });

  it("FR-020-06 · the defaults lie inside the range of their control", () => {
    for (const f of FIGURES)
      for (const c of f.controls)
        if (c.kind === "range")
          expect((c as { default: number }).default, `${f.id}.${c.id}`).toBeGreaterThanOrEqual(
            (c as { min: number }).min,
          );
  });
});

describe("the digest of a plot (FR-020-13)", () => {
  it("FR-020-13 · seriesDigest is the SHA-256 of the little-endian float64 bytes: [1, 2] gives the digest of 000000000000f03f 0000000000000040", () => {
    const expected = createHash("sha256")
      .update(Buffer.from("000000000000f03f0000000000000040", "hex"))
      .digest("hex");
    expect(seriesDigest([Float64Array.from([1, 2])])).toBe(expected);
    expect(seriesDigest([Float64Array.from([1]), Float64Array.from([2])])).toBe(expected);
    expect(seriesDigest([])).toBe(createHash("sha256").update(Buffer.alloc(0)).digest("hex"));
  });

  it("FR-020-13 · one different sample, or one more sample, gives a different digest", () => {
    const a = seriesDigest([Float64Array.from([1, 2, 3])]);
    expect(seriesDigest([Float64Array.from([1, 2, 3.0000000000000004])])).not.toBe(a);
    expect(seriesDigest([Float64Array.from([1, 2, 3, 4])])).not.toBe(a);
    expect(a).toMatch(/^[0-9a-f]{64}$/);
  });

  const teaching = TABLE.filter((r) => r[2] === "teaching").map((r) => r[0]);
  for (const id of teaching) {
    it(`FR-020-13 · ${id}: changing any one control to another valid value changes the digest of the plotted series`, () => {
      const f = FIGURES.find((x) => x.id === id);
      const base = computeFigure(id, {});
      const digest = (v: Record<string, number | string>) =>
        seriesDigest(computeFigure(id, v).series.flatMap((s) => [s.x, s.y]));
      const d0 = digest({});
      expect(computeFigure(id, {}).series.length).toBeGreaterThan(0);
      expect(base.series.every((s) => s.x instanceof Float64Array && s.y instanceof Float64Array)).toBe(true);
      for (const c of f?.controls ?? []) {
        let other: number | string;
        if (c.kind === "range") {
          const r = c as { min: number; max: number; default: number; step?: number };
          const half =
            r.max > r.default ? r.default + (r.max - r.default) / 2 : r.min + (r.default - r.min) / 2;
          const snapped = r.step ? Math.round(half / r.step) * r.step : half;
          other = snapped === r.default ? (r.max > r.default ? r.max : r.min) : snapped;
        } else {
          const ch = c as { options: string[]; default: string };
          other = ch.options.find((o) => o !== ch.default) as string;
        }
        expect(digest({ [c.id]: other }), `${id}.${c.id}`).not.toBe(d0);
      }
    });
  }
});

describe("features by closed form (FR-020-08)", () => {
  it("FR-020-08 · PPO: the clip bounds are 1 - eps and 1 + eps (0.8 and 1.2 at eps = 0.2)", () => {
    const f = computeFigure("ppo-clip", { clip_epsilon: 0.2, advantage_sign: "positive" }).features;
    expect(f.clip_low?.value).toBeCloseTo(0.8, 12);
    expect(f.clip_high?.value).toBeCloseTo(1.2, 12);
    const g = computeFigure("ppo-clip", { clip_epsilon: 0.35, advantage_sign: "negative" }).features;
    expect(g.clip_low?.value).toBeCloseTo(0.65, 12);
    expect(g.clip_high?.value).toBeCloseTo(1.35, 12);
  });

  it("FR-020-08 · Ritter: the front is 2 sqrt(g h0) t (26.572143308359603 m at h0 = 2 m, t = 3 s) and the depth at the dam 4 h0 / 9", () => {
    const f = computeFigure("ritter-dam-break", { h0: 2, t: 3 }).features;
    expect(Math.abs((f.front?.value ?? 0) - 26.572143308359603)).toBeLessThan(1e-9);
    expect(f.front?.unit).toBe("m");
    expect(Math.abs((f.dam_depth?.value ?? 0) - 8 / 9)).toBeLessThan(1e-12);
    expect(Math.abs(2 * Math.sqrt(G * 2) * 3 - (f.front?.value ?? 0))).toBeLessThan(1e-9);
  });

  it("FR-020-08 · Beverloo: no flow at D = k d (k d = 1.4 x 5 mm = 0.007 m)", () => {
    const f = computeFigure("beverloo-discharge", { D: 0.1, d: 5, C: 0.58, k: 1.4, rho_b: 1500 }).features;
    expect(Math.abs((f.no_flow_diameter?.value ?? 0) - 0.007)).toBeLessThan(1e-12);
    expect(f.operating_point?.value).toBeGreaterThan(0);
  });
});

describe("markers and read-out show the same text (FR-020-08)", () => {
  const render = (id: string, values: Record<string, number | string> = {}) =>
    renderApp(createElement(Figure, { id, values }));
  const text = (sel: string) => document.querySelector(sel)?.textContent?.trim();

  for (const id of [
    "ppo-clip",
    "ritter-dam-break",
    "beverloo-discharge",
    "lidar-range-dust",
    "mcnemar",
    "c2st-auc",
    "paired-ci",
  ]) {
    it(`FR-020-08 · ${id}: each feature has a labelled marker, and its text equals the read-out panel's text for that feature`, async () => {
      await render(id);
      const expected = TABLE.find((r) => r[0] === id)?.[5] ?? 0;
      const markers = Array.from(document.querySelectorAll('[data-testid="chart-marker"]'));
      expect(markers).toHaveLength(expected);
      for (const m of markers) {
        const feature = m.getAttribute("data-feature") as string;
        const labelled = text(`[data-testid="chart-marker"][data-feature="${feature}"]`);
        const read = text(`[data-testid="figure-readout"] [data-feature="${feature}"]`);
        expect(labelled?.length, feature).toBeGreaterThan(0);
        expect(read, feature).toBe(labelled);
      }
    });
  }

  it("FR-020-08 · the PPO markers read 0.8 and 1.2 at eps = 0.2, in both places", async () => {
    await render("ppo-clip", { clip_epsilon: 0.2, advantage_sign: "positive" });
    for (const id of ["clip_low", "clip_high"]) {
      const m = text(`[data-testid="chart-marker"][data-feature="${id}"]`) ?? "";
      expect(m).toMatch(id === "clip_low" ? /0\.8\b/ : /1\.2\b/);
      expect(text(`[data-testid="figure-readout"] [data-feature="${id}"]`)).toBe(m);
    }
  });
});

describe("a control drives the figure (FR-020-13)", () => {
  it("FR-020-13 · the figure exposes the digest of its plotted series, and a change of a control changes it", async () => {
    await renderApp(createElement(Figure, { id: "ppo-clip" }));
    const fig = screen.getByTestId("figure");
    const before = fig.getAttribute("data-digest");
    expect(before).toMatch(/^[0-9a-f]{64}$/);
    const input = fig.querySelector('input[data-control="clip_epsilon"]') as HTMLInputElement;
    expect(input.getAttribute("data-unit")).toBeTruthy();
    fireEvent.change(input, { target: { value: String(Number(input.getAttribute("data-max")) * 0.9) } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(fig.getAttribute("data-digest")).not.toBe(before);
    expect(fig.getAttribute("data-digest")).toMatch(/^[0-9a-f]{64}$/);
  });

  it("FR-020-13 · a choice control changes the digest too", async () => {
    await renderApp(createElement(Figure, { id: "ppo-clip" }));
    const fig = screen.getByTestId("figure");
    const before = fig.getAttribute("data-digest");
    const select = fig.querySelector('select[data-control="advantage_sign"]') as HTMLSelectElement;
    fireEvent.change(select, {
      target: {
        value: Array.from(select.options)
          .map((o) => o.value)
          .find((v) => v !== select.value),
      },
    });
    expect(fig.getAttribute("data-digest")).not.toBe(before);
  });
});
