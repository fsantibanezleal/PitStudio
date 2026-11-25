// T-018-110 [red] · FR-018-85: the paired interval of a difference is drawn as an interval (end caps, zero reference), never as a
// line between its end points; a chart is titled with the quantity it plots (the D1 chart named "TSTR/TRTR IoU ratio" plotted the
// real-image IoU). Oracles: the published rows web/public/results/c1-slope-forecasters.json (TCN and PatchTST against inverse
// velocity: [-227.512, -131.959] and [-218.236, -122.738] h, read by hand from the file) and d1-unet-trtr-iou.json (0.89093 with
// [0.88311, 0.89875]); the live page screenshots of the review of 2026-11-23 (C1-charts, D1-charts).
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import type { ComparisonRow } from "~/results/ComparisonRows";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { ChartsTab } from "./ChartsTab";

const HERE = dirname(fileURLToPath(import.meta.url));
const PUBLIC = resolve(HERE, "../../public/results");
const rowsOf = (file: string) =>
  (JSON.parse(readFileSync(join(PUBLIC, file), "utf-8")) as { rows: ComparisonRow[] }).rows;
const registry = loadCaseRegistry();
const section = (id: string) => document.querySelector(`section[data-kpi-chart="${id}"]`) as HTMLElement;

describe("FR-018-85 · the C1 forecast-error interval", () => {
  it("FR-018-85 · each paired interval is an interval with its two end points, plus the zero reference", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "C1", registry, rows: rowsOf("c1-slope-forecasters.json") }));
    const s = section("forecast_error");
    const intervals = [...s.querySelectorAll("[data-interval]")];
    expect(intervals).toHaveLength(2);
    expect(intervals.map((i) => [Number(i.getAttribute("data-lo")), Number(i.getAttribute("data-hi"))])).toEqual([
      [-227.512, -131.959],
      [-218.236, -122.738],
    ]);
    expect(s.querySelector("[data-zero-reference]")).not.toBeNull();
    expect(within(s).getByTestId("chart").getAttribute("data-chart-kind")).toBe("interval");
    expect(s.querySelector("canvas")).toBeNull();
  });

  it("FR-018-85 · both challengers are named with their interval text and verdict, the unit is on the axis", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "C1", registry, rows: rowsOf("c1-slope-forecasters.json") }));
    const text = section("forecast_error").textContent ?? "";
    expect(text).toContain("TCN");
    expect(text).toContain("PatchTST");
    expect(text).toContain("-227.5");
    expect(text).toContain("-122.7");
    expect(text).toMatch(/TCN better than Inverse velocity/);
    expect(text).toContain("95 %");
    expect(screen.getAllByText(/value in h/).length).toBeGreaterThan(0);
  });

  it("FR-018-85 · the data table lists the end points with their unit", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "C1", registry, rows: rowsOf("c1-slope-forecasters.json") }));
    const chart = within(section("forecast_error")).getByTestId("chart");
    (within(chart).getByRole("button", { name: /Show data/ }) as HTMLButtonElement).click();
    const table = await within(chart).findByTestId("chart-table");
    const heads = [...table.querySelectorAll("th")].map((th) => th.textContent);
    expect(heads).toContain("lower edge (h)");
    expect(heads).toContain("upper edge (h)");
    expect([...table.querySelectorAll("tbody tr")]).toHaveLength(2);
  });
});

describe("FR-018-85 · the D1 chart is titled with what it plots", () => {
  it("FR-018-85 · the real-image IoU is not called a ratio", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "D1", registry, rows: rowsOf("d1-unet-trtr-iou.json") }));
    const s = section("tstr_trtr_iou");
    expect(within(s).getByRole("heading", { level: 3 }).textContent).toContain(
      "Foreground IoU, trained and tested on real images",
    );
    expect(within(s).getByRole("heading", { level: 3 }).textContent).not.toContain("ratio");
    expect(s.textContent).toContain("is measured by a run that is not published yet");
  });

  it("FR-018-85 · the estimate is drawn with its point and its interval and no zero reference", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "D1", registry, rows: rowsOf("d1-unet-trtr-iou.json") }));
    const s = section("tstr_trtr_iou");
    const [one] = [...s.querySelectorAll("[data-interval]")];
    expect([Number(one?.getAttribute("data-lo")), Number(one?.getAttribute("data-hi"))]).toEqual([0.88311, 0.89875]);
    expect(one?.querySelector("circle")).not.toBeNull();
    expect(s.querySelector("[data-zero-reference]")).toBeNull();
  });

  it("FR-018-85 · the Spanish page says the same in Spanish", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "D1", registry, rows: rowsOf("d1-unet-trtr-iou.json") }), {
      lang: "es",
    });
    const s = section("tstr_trtr_iou");
    expect(s.textContent).toContain("IoU de primer plano, entrenado y probado en imágenes reales");
    expect(s.textContent).toContain("lo mide una corrida que aún no está publicada");
  });
});
