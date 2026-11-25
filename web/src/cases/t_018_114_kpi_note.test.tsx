// T-018-114 [red] · FR-018-85: the note under a Charts-tab chart that plots a different quantity than its KPI says plainly what the
// chart is and what the KPI itself needs. The text "it is not the KPI Forecast error, which needs a run that is not published yet"
// confused a visitor on the live C1 page (review of 2026-11-24); it is replaced in English and Spanish. Oracle: the published D1 row
// web/public/results/d1-unet-trtr-iou.json (the chart plots the real-image IoU while the KPI is the TSTR/TRTR ratio), read by hand.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import type { ComparisonRow } from "~/results/ComparisonRows";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { ChartsTab } from "./ChartsTab";

const HERE = dirname(fileURLToPath(import.meta.url));
const rows = (
  JSON.parse(readFileSync(join(resolve(HERE, "../../public/results"), "d1-unet-trtr-iou.json"), "utf-8")) as {
    rows: ComparisonRow[];
  }
).rows;
const registry = loadCaseRegistry();
const note = () => {
  const s = document.querySelector('section[data-kpi-chart="tstr_trtr_iou"]') as HTMLElement;
  return [...s.querySelectorAll("p")].map((p) => p.textContent ?? "").find((t) => /shows|muestra/.test(t)) ?? "";
};

describe("FR-018-85 · the note of a chart that plots another quantity than its KPI", () => {
  it("FR-018-85 · English: says what the chart shows and that the KPI value comes from a run not published yet", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "D1", registry, rows }));
    const text = note();
    expect(text).toContain("This chart shows Foreground IoU, trained and tested on real images");
    expect(text).toContain("is measured by a run that is not published yet");
    expect(text).not.toContain("is not the KPI");
    expect(text).not.toContain("which needs");
  });

  it("FR-018-85 · Spanish: the same two facts in Spanish", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "D1", registry, rows }), { lang: "es" });
    const text = note();
    expect(text).toContain("Este gráfico muestra IoU de primer plano, entrenado y probado en imágenes reales");
    expect(text).toContain("lo mide una corrida que aún no está publicada");
    expect(text).not.toContain("no es el KPI");
  });
});
