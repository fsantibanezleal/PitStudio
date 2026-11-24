// T-020-113 [red] · FR-020-55 and FR-020-11: the generic chart reader shows every published value readably. Four defects seen on the
// live pages of 2026-11-24: the bar-chart value labels were cut off at the left edge when the numbers are large (the E2 volume bars read
// "00000000"); the zero-reference label of an interval chart ran past the right edge (C1 "no difference"); a table printed the raw
// floats of the file ("174.95999999999995"); the run groups of the Charts tab of E1 and E2 were headed by the run id.
// Oracles: the geometry is checked against the arithmetic of the SVG viewBox (640 wide) and the tick label length at the tick font size
// (7 px per character, a stated upper bound for the tick font); the numbers are the values of the published D2 table; the run
// headings are the facts of the run files (producer method of the charts, the UTC date of the run id).
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "~/test-support/render";
import { BarPlot } from "./BarPlot";
import type { ChartDoc } from "./chartSeries";
import { IntervalPlot } from "./IntervalPlot";
import { runHeading } from "./RunCharts";
import { SeriesChart } from "./SeriesChart";

const L = (en: string, es = en) => ({ en, es });
const CHAR_PX = 7;

function barDoc(values: number[]): ChartDoc {
  return {
    schema_version: "1.0",
    kind: "chart-series",
    id: "e2-volume",
    case: "E2",
    chart_type: "bar",
    status: "ok",
    title: L("Volume change", "Cambio de volumen"),
    y_axis: { label: L("Volume", "Volumen"), unit: "m3" },
    categories: values.map((_, i) => ({ id: `c${i}`, label: L(`cat ${i}`) })),
    series: [{ id: "s", label: L("Cut"), unit: "m3", y: values }],
    producer: { tool: "pitstudio", method: "dem differencing", version: "1", label: "measurement" },
  } as unknown as ChartDoc;
}

const endLabels = (container: HTMLElement) =>
  [...container.querySelectorAll("text")].filter((t) => t.getAttribute("text-anchor") === "end");

describe("FR-020-55 · the value labels of a bar chart fit inside the chart", () => {
  it("FR-020-55 · with values of 546,800,000 the widest tick label starts at or after x = 0", () => {
    const { container } = render(<BarPlot doc={barDoc([546_800_000, 120_000_000])} lang="en" title="t" />);
    const labels = endLabels(container);
    expect(labels.length).toBeGreaterThan(2);
    for (const t of labels) {
      const right = Number(t.getAttribute("x"));
      const width = (t.textContent ?? "").length * CHAR_PX;
      expect(right - width, `label "${t.textContent}"`).toBeGreaterThanOrEqual(0);
    }
  });

  it("FR-020-55 · the plot area keeps more than half of the chart width", () => {
    const { container } = render(<BarPlot doc={barDoc([546_800_000])} lang="en" title="t" />);
    const left = Math.max(...endLabels(container).map((t) => Number(t.getAttribute("x"))));
    expect(640 - left).toBeGreaterThan(320);
  });

  it("FR-020-55 · small values keep the existing margin (labels stay where they were)", () => {
    const { container } = render(<BarPlot doc={barDoc([1, 2, 3])} lang="en" title="t" />);
    expect(Math.max(...endLabels(container).map((t) => Number(t.getAttribute("x"))))).toBe(54);
  });
});

describe("FR-020-55 · the zero-reference label of an interval chart stays inside the chart", () => {
  const entries = [{ id: "r", label: "TCN against inverse velocity", lo: -227, hi: -131 }];

  it("FR-020-55 · with the zero line near the right edge the label is anchored to the left of the line", () => {
    const { container } = render(
      <IntervalPlot id="i" title="t" unit="h" intervals={entries} zero level={0.95} lang="en" />,
    );
    const label = container.querySelector("[data-zero-reference] text") as SVGTextElement;
    const line = container.querySelector("[data-zero-reference] line") as SVGLineElement;
    expect(label.getAttribute("text-anchor")).toBe("end");
    expect(Number(label.getAttribute("x"))).toBeLessThan(Number(line.getAttribute("x1")));
  });

  it("FR-020-55 · with the zero line in the middle the label stays to the right of the line", () => {
    const { container } = render(
      <IntervalPlot
        id="i"
        title="t"
        unit="h"
        intervals={[{ id: "r", label: "x", lo: -50, hi: 60 }]}
        zero
        level={0.95}
        lang="en"
      />,
    );
    const label = container.querySelector("[data-zero-reference] text") as SVGTextElement;
    const line = container.querySelector("[data-zero-reference] line") as SVGLineElement;
    expect(label.getAttribute("text-anchor") ?? "start").toBe("start");
    expect(Number(label.getAttribute("x"))).toBeGreaterThan(Number(line.getAttribute("x1")));
  });
});

describe("FR-020-55 · a table of a chart series prints numbers readably, in both languages", () => {
  const doc = {
    schema_version: "1.0",
    kind: "chart-series",
    id: "d2-chain-stages",
    case: "D2",
    chart_type: "table",
    status: "ok",
    title: L("Chain stages", "Etapas de la cadena"),
    table: {
      columns: [
        { id: "stage", label: L("Stage", "Etapa") },
        { id: "value", label: L("Value", "Valor"), unit: "kWh/t" },
      ],
      rows: [
        ["Blast", 174.95999999999995],
        ["Mill", 0.32512851718952396],
        ["Cost", 12],
        ["Big", 1234567.891],
        ["None", null],
      ],
    },
    producer: { tool: "minephys", method: "chain", version: "1", label: "calibrated synthetic" },
  } as unknown as ChartDoc;
  const cells = () => [...document.querySelectorAll("tbody td")].map((td) => td.textContent);

  it("FR-020-55 · English: at most five significant digits, whole numbers unchanged, null as not available", async () => {
    await renderApp(<SeriesChart doc={doc} />);
    expect(cells()).toContain("175");
    expect(cells()).toContain("0.32513");
    expect(cells()).toContain("12");
    expect(cells()).toContain("1234600");
    expect(cells().join(" ")).not.toContain("999995");
  });

  it("FR-020-55 · Spanish: the same digits with the Spanish decimal comma", async () => {
    await renderApp(<SeriesChart doc={doc} />, { lang: "es" });
    expect(cells()).toContain("175");
    expect(cells()).toContain("0,32513");
  });
});

describe("FR-020-55 · a run group of the Charts tab has a readable heading", () => {
  const runId = "20261124T121159Z-e2-coarse";
  const charts = [
    {
      runId,
      doc: {
        producer: {
          tool: "pitstudio",
          method: "DEM differencing, SRTM GL1 against 3DEP 2018",
          version: "1",
          label: "measurement",
        },
      },
    },
  ] as never;

  it("FR-020-55 · the title of the published result wins", () => {
    expect(runHeading(runId, charts, [{ runId, title: "Pit volume" }] as never, "en")).toBe("Pit volume");
  });

  it("FR-020-55 · with no result the heading is the producer method and the run date, never the run id", () => {
    const h = runHeading(runId, charts, [], "en");
    expect(h).toContain("DEM differencing, SRTM GL1 against 3DEP 2018");
    expect(h).toContain("2026-11-24");
    expect(h).not.toContain("20261124T121159Z");
    expect(h).not.toContain("e2-coarse");
  });

  it("FR-020-55 · the Spanish heading names the run and the date in Spanish words", () => {
    const h = runHeading(runId, charts, [], "es");
    expect(h).toContain("2026-11-24");
    expect(h).toMatch(/corrida/i);
  });
});
