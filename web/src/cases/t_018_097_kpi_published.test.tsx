// T-018-097 [red] · FR-018-74: the KPI table shows each published value of a case KPI with its provenance chip. A published
// summary names the KPI in an explicit `kpi` field of a headline entry; nothing is mapped by name or by unit alone.
// Oracles: the summary shape written by `studio import-run` (tests/unit/test_import_summaries_kpi.py), the C1 headline of the published run
// 20261013T171809Z-c1-slope-forecasters (57.54 h, read by hand from its summary), the FR text.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { KpiTable } from "./KpiTable";
import { kpiItems } from "./kpiValues";
import { type PublishedResult, readResult } from "./publishedResults";
import type { ArtefactRecord, CaseEntry } from "./types";

const registry = loadCaseRegistry();
const c1 = registry.cases.C1 as unknown as CaseEntry;
const RUN = "20261013T171809Z-c1-slope-forecasters";
const NEWER = "20261120T101500Z-c1-slope-forecasters";

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

function raw(headline: unknown[], over: Record<string, unknown> = {}) {
  return {
    title: "Slope forecasters",
    label: "calibrated synthetic",
    methods: ["M14"],
    verdict: "ok",
    headline,
    rows: [],
    ...over,
  };
}
const tcn = {
  name: "Mean absolute forecast error, TCN",
  value: 57.54,
  unit: "h",
  note: "best of the six methods",
  kpi: "forecast_error",
};
const baseline = { name: "Mean absolute forecast error, inverse velocity", value: 237.28, unit: "h" };

function result(
  run: string,
  headline: unknown[],
  notes: string[] = [],
  over: Record<string, unknown> = {},
): PublishedResult {
  const r = readResult(raw(headline, over), { stages: [], notes, profile: "imported" }, run, artefact(run));
  expect(r).not.toBeNull();
  return r as PublishedResult;
}

describe("FR-018-74 reading the kpi field of a headline", () => {
  it("FR-018-74 · keeps the kpi id of a headline entry and the artefact record the summary came from", () => {
    const r = result(RUN, [tcn, baseline]);
    expect(r.headline.map((h) => h.kpi ?? null)).toEqual(["forecast_error", null]);
    expect(r.artefact?.id).toBe("c1-slope-forecasters-results");
  });

  it("FR-018-74 · ignores a kpi field that is not a non-empty string", () => {
    const r = result(RUN, [
      { ...tcn, kpi: 7 },
      { ...baseline, kpi: "" },
    ]);
    expect(r.headline.map((h) => h.kpi ?? null)).toEqual([null, null]);
  });
});

describe("FR-018-74 which value feeds which KPI", () => {
  it("FR-018-74 · gives C1 forecast error the published 57.54 h with its artefact, and every other KPI of C1 no value", () => {
    const items = kpiItems(c1, [result(RUN, [tcn, baseline])]);
    expect(items.map((i) => i.kpi.id)).toEqual(["fos", "pof", "forecast_error"]);
    const fe = items.find((i) => i.kpi.id === "forecast_error");
    expect(fe?.value).toBe(57.54);
    expect(fe?.artefact?.run_id).toBe(RUN);
    for (const i of items.filter((x) => x.kpi.id !== "forecast_error")) {
      expect(i.value).toBeNull();
      expect(i.artefact).toBeNull();
    }
  });

  it("FR-018-74 · never maps by name or unit: a headline without a kpi field feeds nothing, even with the KPI's own name and unit", () => {
    const lookalike = { name: "Forecast error", value: 12, unit: "h" };
    const items = kpiItems(c1, [result(RUN, [lookalike, baseline])]);
    expect(items.every((i) => i.value === null)).toBe(true);
  });

  it("FR-018-74 · refuses a kpi id the case does not have and a unit that differs from the KPI unit", () => {
    expect(kpiItems(c1, [result(RUN, [{ ...tcn, kpi: "p80" }])]).every((i) => i.value === null)).toBe(true);
    expect(kpiItems(c1, [result(RUN, [{ ...tcn, unit: "min" }])]).every((i) => i.value === null)).toBe(true);
  });

  it("FR-018-74 · takes the newest run when two published runs name the same KPI, and ignores a failed evaluation", () => {
    const older = result(RUN, [tcn]);
    const newer = result(NEWER, [{ ...tcn, value: 41.2 }]);
    expect(kpiItems(c1, [older, newer]).find((i) => i.kpi.id === "forecast_error")?.value).toBe(41.2);
    const failed = result(NEWER, [{ ...tcn, value: 1 }], [], { verdict: "failed" });
    expect(kpiItems(c1, [older, failed]).find((i) => i.kpi.id === "forecast_error")?.value).toBe(57.54);
  });

  it("FR-018-74 · with no published run every headline KPI stays 'Not yet run'", () => {
    const items = kpiItems(c1, []);
    expect(items.map((i) => i.kpi.id)).toEqual(["fos", "pof", "forecast_error"]);
    expect(items.every((i) => i.value === null && i.artefact === null)).toBe(true);
  });

  it("FR-018-74 · also lists a KPI that is not a headline KPI once a published value feeds it", () => {
    const lead = { name: "Lead time", value: 30, unit: "h", kpi: "lead_time" };
    const ids = kpiItems(c1, [result(RUN, [lead])]).map((i) => i.kpi.id);
    expect(ids).toEqual(["fos", "pof", "forecast_error", "lead_time"]);
  });
});

describe("FR-018-74 the KPI table of a published value", () => {
  it("FR-018-74 · shows 57.54 h, the lane badge, a chip with the run id linking to the run record, and no 'Not yet run' on that row", async () => {
    const items = kpiItems(c1, [result(RUN, [tcn, baseline])]);
    const { container } = await renderApp(<KpiTable items={items} />);
    const row = container.querySelector('[data-kpi="forecast_error"]') as HTMLElement;
    expect(row.textContent).toContain("57.54");
    expect(row.textContent).toContain("h");
    expect(row.textContent).toContain("STATIC");
    expect(row.textContent).toContain(RUN);
    expect(row.textContent).not.toContain("Not yet run");
    expect(row.querySelector(`a[href="/studio/runs/${RUN}/"]`)).not.toBeNull();
    expect(container.querySelector('[data-kpi="fos"]')?.textContent).toContain("Not yet run");
  });

  it("FR-018-74 · keeps the partial label next to a value that comes from a run noted partial", async () => {
    const items = kpiItems(c1, [result(RUN, [tcn], ["partial: recipe cases/c1.yaml changed"])]);
    const { container } = await renderApp(<KpiTable items={items} />);
    const row = container.querySelector('[data-kpi="forecast_error"]') as HTMLElement;
    expect(row.textContent).toContain("Partial provenance");
    expect(screen.queryAllByText(/Partial provenance/)).toHaveLength(1);
  });

  it("FR-018-74 · writes the partial mark in Spanish", async () => {
    const items = kpiItems(c1, [result(RUN, [tcn], ["partial: x"])]);
    const { container } = await renderApp(<KpiTable items={items} />, { lang: "es" });
    expect(container.querySelector('[data-kpi="forecast_error"]')?.textContent).toContain(
      "Procedencia parcial",
    );
  });
});
