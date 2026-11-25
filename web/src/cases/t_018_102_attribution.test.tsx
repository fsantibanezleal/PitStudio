// T-018-102 [red] · FR-018-79: a per-visual attribution line names as used only what a published run produced for that visual, the render
// tools count as used for the render section alone, and a KPI that is not run shows the not-run text with no unit.
// Oracles: the live C1 page text of 2026-11-23 ("Probability of failure: Not yet run %", "Measured with PyTorch, Slope stability LEM,
// Slope forecasting. Used in the published result." while only the forecasters run 20261013T171809Z-c1-slope-forecasters is published),
// the case registry example, the FR text.
import { within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { attributionText, type BuiltItem, deriveBuiltWith, visualAttributionText } from "./builtWith";
import { KpiTable } from "./KpiTable";
import { kpiItems } from "./kpiValues";
import { type PublishedResult, readResult } from "./publishedResults";
import type { ArtefactRecord, CaseEntry } from "./types";
import { usedForVisual } from "./visualUsed";

const registry = loadCaseRegistry();
const c1 = registry.cases.C1 as unknown as CaseEntry;
const RUN = "20261013T171809Z-c1-slope-forecasters";
const tools = [
  { id: "pytorch", name: "PyTorch", version: "2.14.1", licence: "BSD-3-Clause" },
  { id: "onnx-runtime", name: "ONNX Runtime (+Web)", version: "1.30.0", licence: "MIT" },
  { id: "threejs-r3f-3d-tiles", name: "three.js / R3F / 3D Tiles", version: null, licence: "MIT" },
  { id: "openusd", name: "NVIDIA OpenUSD", version: "26.8", licence: "Apache-2.0" },
  { id: "ovrtx", name: "ovrtx", version: "0.5.0", licence: null },
];
const methods = [
  { id: "M13", name: { en: "Slope stability LEM", es: "LEM de estabilidad" }, slug: "m13" },
  { id: "M14", name: { en: "Slope forecasting", es: "Pronostico de taludes" }, slug: "m14" },
  { id: "M23", name: { en: "RTX sensor simulation", es: "Simulacion de sensores RTX" }, slug: "m23" },
];

function artefact(run: string): ArtefactRecord {
  return {
    id: "c1-slope-forecasters-results",
    run_id: run,
    git_sha: "abcdef0123456789abcdef0123456789abcdef01",
    path: `assets/${run}/results-summary.json`,
    bytes: 100,
    sha256: "1".repeat(64),
    kind: "table",
    producer: { tool: "pitstudio", stage: { id: "s50_evaluate" } },
    inputs: [],
    cases: ["C1"],
    lane: "static",
    licence_class: "own",
    spdx: "CC-BY-4.0",
  } as ArtefactRecord;
}
const forecast: PublishedResult = readResult(
  {
    title: "Slope forecasters",
    label: "calibrated synthetic",
    methods: ["M14"],
    verdict: "ok",
    headline: [{ name: "Mean absolute forecast error, TCN", value: 57.54, unit: "h", kpi: "forecast_error" }],
    rows: [],
  },
  { stages: [{ tool: "pytorch" }], notes: [], profile: "imported" },
  RUN,
  artefact(RUN),
) as PublishedResult;

const used = (items: BuiltItem[]) => items.filter((i) => i.status === "used");
const base = { entry: c1, tools, methods, lang: "en" as const, caseId: "C1" };
const words = {
  used: "Used in the published result.",
  planned: "Planned, not yet run.",
  plannedList: (parts: string) => `Planned, not yet run: ${parts}.`,
};

describe("FR-018-79 the attribution line separates used from planned parts", () => {
  it("FR-018-79 · lists the used parts, then the planned ones in a separate sentence", () => {
    const g = deriveBuiltWith({ ...base, usedTools: new Set(["pytorch"]), usedMethods: new Set(["M14"]) });
    const text = attributionText(
      "Measured with",
      [...g.frameworks.filter((i) => i.id === "pytorch")],
      g.methods.filter((m) => m.id !== "M23"),
      words,
    );
    expect(text).toBe(
      "Measured with PyTorch 2.14.1, Slope forecasting. Used in the published result. Planned, not yet run: Slope stability LEM.",
    );
  });

  it("FR-018-79 · a line with no used part never says used", () => {
    const g = deriveBuiltWith({ ...base, usedTools: new Set(), usedMethods: new Set() });
    const text = attributionText("Measured with", g.frameworks.slice(0, 1), g.methods.slice(0, 1), words);
    expect(text).not.toMatch(/used/i);
    expect(text).toMatch(/Planned, not yet run\.$/);
  });
});

describe("FR-018-79 what stands behind each visual of C1 with only the forecasters run published", () => {
  const groups = deriveBuiltWith({
    ...base,
    usedTools: new Set(["pytorch"]),
    usedMethods: new Set(["M14"]),
    renderTools: ["openusd", "ovrtx"],
  });

  it("FR-018-79 · the KPI line names PyTorch and Slope forecasting as used and the LEM as planned, never as used", () => {
    const u = usedForVisual("kpi", [forecast], c1);
    expect([...u.tools]).toEqual(["pytorch"]);
    expect([...u.methods]).toEqual(["M14"]);
    const text = visualAttributionText("kpi", "Measured with", groups, u, words);
    expect(text).toContain("PyTorch");
    expect(text).toMatch(/Used in the published result\./);
    const [usedPart, plannedPart] = text.split("Used in the published result.");
    expect(usedPart).not.toContain("Slope stability LEM");
    expect(plannedPart).toContain("Slope stability LEM");
  });

  it("FR-018-79 · the render tools do not make the scene line used: it is planned until the tileset run is published", () => {
    expect(used(groups.omniverse).map((i) => i.id)).toEqual(["openusd", "ovrtx"]);
    const u = usedForVisual("scene", [forecast], c1);
    expect(u.tools.size).toBe(0);
    const text = visualAttributionText("scene", "Rendered in the browser with", groups, u, words);
    expect(text).not.toMatch(/used/i);
    expect(text).toMatch(/Planned, not yet run\.$/);
  });

  it("FR-018-79 · the scene line becomes used once a published run names the viewer tool", () => {
    const tiles = readResult(
      { title: "Terrain tiles", label: "real data", verdict: "ok", methods: [], headline: [], rows: [] },
      { stages: [{ tool: "threejs-r3f-3d-tiles" }], notes: [] },
      "20261201T100000Z-c1-terrain",
      artefact("20261201T100000Z-c1-terrain"),
    ) as PublishedResult;
    const u = usedForVisual("scene", [tiles], c1);
    expect([...u.tools]).toEqual(["threejs-r3f-3d-tiles"]);
  });

  it("FR-018-79 · a KPI visual with no value fed, a chart without a result and a failed run claim nothing", () => {
    const noKpi = { ...forecast, headline: [] };
    expect(usedForVisual("kpi", [noKpi], c1).tools.size).toBe(0);
    expect(usedForVisual("chart", [], c1).tools.size).toBe(0);
    expect(usedForVisual("chart", [{ ...forecast, verdict: "failed" }], c1).tools.size).toBe(0);
    expect(usedForVisual("chart", [forecast], c1, false).tools.size).toBe(0);
    expect([...usedForVisual("chart", [forecast], c1).tools]).toEqual(["pytorch"]);
  });

  it("FR-018-79 · a visual with no registry entry gives no line", () => {
    const empty = deriveBuiltWith({
      ...base,
      entry: { ...c1, tools: {}, methods: [] },
      usedTools: new Set(),
      usedMethods: new Set(),
    });
    expect(visualAttributionText("kpi", "Measured with", empty, usedForVisual("kpi", [], c1), words)).toBe(
      "",
    );
  });
});

describe("FR-018-79 a KPI that is not run shows the not-run text alone", () => {
  for (const [lang, notRun] of [
    ["en", "Not yet run"],
    ["es", "Aún no ejecutado"],
  ] as const) {
    it(`FR-018-79 · ${lang} · probability of failure and factor of safety carry no unit, forecast error keeps its own`, async () => {
      await renderApp(<KpiTable items={kpiItems(c1, [forecast])} />, { lang });
      const pof = within(document.querySelector('[data-kpi="pof"]') as HTMLElement);
      expect(pof.getByText(notRun)).toBeTruthy();
      expect((document.querySelector('[data-kpi="pof"]') as HTMLElement).textContent).not.toMatch(/%/);
      const fos = document.querySelector('[data-kpi="fos"]') as HTMLElement;
      expect(fos.textContent).not.toMatch(new RegExp(`${notRun}\\s*\\S`));
      const row = document.querySelector('[data-kpi="forecast_error"]') as HTMLElement;
      expect(row.textContent).toMatch(/57[.,]54 h/);
    });
  }
});
