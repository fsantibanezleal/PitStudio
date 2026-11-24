// T-018-112 [red] · FR-018-87: when a case's published runs carry chart series, the Charts tab shows no empty placeholder chart for a KPI
// without a result row; those KPIs are listed once, each with "Not yet run", and a KPI named by the `kpi` field of a chart series is not
// listed. A case with no chart series keeps one placeholder per KPI. Oracles: the case registry (E1 KPIs read from it), the example
// corpus of DC-020-05, the FR text.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, waitFor, within } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { ChartsTab } from "./ChartsTab";
import type { CaseEntry } from "./types";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../../specs/020-web-knowledge/contracts/examples");
const example = (name: string) => JSON.parse(readFileSync(join(EXAMPLES, `chart-series.${name}.json`), "utf-8"));
const registry = loadCaseRegistry();
const e1 = registry.cases.E1 as unknown as CaseEntry;
const RUN = "20261124T031351Z-e1-shells";

const record = (id: string) => ({
  id,
  run_id: RUN,
  git_sha: "abcdef0123456789abcdef0123456789abcdef01",
  path: `assets/${RUN}/${id}.json`,
  bytes: 100,
  sha256: "1".repeat(64),
  kind: "chart-series",
  producer: { tool: "pitstudio", stage: { id: "s50_evaluate" } },
  inputs: [],
  cases: ["E1"],
  lane: "static",
  licence_class: "own",
  spdx: "CC-BY-4.0",
});

function serve(charts: Record<string, unknown>) {
  const files: Record<string, unknown> = {
    "assets/manifest.json": { kind: "web-index", artefacts: Object.keys(charts).map(record) },
  };
  for (const [id, doc] of Object.entries(charts)) files[`assets/${RUN}/${id}.json`] = doc;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const key = String(url).replace(/^.*?(assets\/)/, "$1");
      return key in files ? { ok: true, json: async () => files[key] } : { ok: false, json: async () => null };
    }),
  );
}
const cards = () => [...document.querySelectorAll("section[data-kpi-chart]")].map((s) => s.getAttribute("data-kpi-chart"));

afterEach(() => vi.unstubAllGlobals());

describe("FR-018-87 · no empty placeholder beside published chart series", () => {
  it("FR-018-87 · a case with chart series lists its KPIs without a series once, with Not yet run, and draws no empty card", async () => {
    const linked = { ...example("valid-kpi-link"), case: "E1", kpi: e1.kpis[0]?.id };
    serve({ "e1-chart": linked });
    await renderApp(createElement(ChartsTab, { caseId: "E1", registry, rows: [] }));
    await waitFor(() => expect(screen.getByTestId("kpis-not-run")).toBeTruthy());
    expect(cards()).toEqual([]);
    const list = screen.getByTestId("kpis-not-run");
    const names = e1.kpis.slice(1).map((k) => k.name.en);
    for (const n of names) expect(within(list).getByText(new RegExp(n.replace(/[()]/g, "\$&")))).toBeTruthy();
    expect(list.textContent).not.toContain(e1.kpis[0]?.name.en as string);
    expect(list.textContent).toContain("Not yet run");
  });

  it("FR-018-87 · a chart that names no KPI leaves every KPI in the not-run list", async () => {
    serve({ "e1-chart": { ...example("valid-bar-error-bars"), case: "E1" } });
    await renderApp(createElement(ChartsTab, { caseId: "E1", registry, rows: [] }));
    await waitFor(() => expect(screen.getByTestId("kpis-not-run")).toBeTruthy());
    expect(cards()).toEqual([]);
    expect(screen.getByTestId("kpis-not-run").querySelectorAll("li")).toHaveLength(e1.kpis.length);
  });

  it("FR-018-87 · a KPI with a result row keeps its card", async () => {
    serve({ "e1-chart": { ...example("valid-bar-error-bars"), case: "E1" } });
    const first = e1.kpis[0] as CaseEntry["kpis"][number];
    const row = {
      kind: "estimate",
      metric: { id: first.id, name: first.name, unit: first.unit, orientation: first.orientation },
      n: 1,
      system: "x",
      value: 3,
    };
    await renderApp(createElement(ChartsTab, { caseId: "E1", registry, rows: [row as never] }));
    await waitFor(() => expect(screen.getByTestId("kpis-not-run")).toBeTruthy());
    expect(cards()).toEqual([first.id]);
    expect(screen.getByTestId("kpis-not-run").querySelectorAll("li")).toHaveLength(e1.kpis.length - 1);
  });

  it("FR-018-87 · without any chart series every KPI keeps its placeholder card", async () => {
    serve({});
    await renderApp(createElement(ChartsTab, { caseId: "E1", registry, rows: [] }));
    await new Promise((r) => setTimeout(r, 60));
    expect(cards()).toEqual(e1.kpis.map((k) => k.id));
    expect(screen.queryByTestId("kpis-not-run")).toBeNull();
  });

  it("FR-018-87 · the Spanish page says Not yet run in Spanish", async () => {
    serve({ "e1-chart": { ...example("valid-bar-error-bars"), case: "E1" } });
    await renderApp(createElement(ChartsTab, { caseId: "E1", registry, rows: [] }), { lang: "es" });
    await waitFor(() => expect(screen.getByTestId("kpis-not-run")).toBeTruthy());
    expect(screen.getByTestId("kpis-not-run").textContent).toContain("Aún no ejecutado");
  });
});
