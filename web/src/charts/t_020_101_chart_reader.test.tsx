// T-020-101 [red] · FR-020-55, FR-020-56, FR-020-57 (spec 020), DC-020-05: the generic chart reader. A published chart file is read through
// the contract (the corpus of specs/020-web-knowledge/contracts/examples is the oracle: every valid example is read, every hostile one is
// refused), and drawn by chart type with its axes and units, its legend, its colour scale and the producer label of the run under it;
// a value not run shows its reason and draws nothing; nothing is drawn for a chart a run does not carry.
// Oracles: the example corpus (hand-built by the spec author), the units and labels written in those examples, the FR text.
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderApp } from "~/test-support/render";
import { type ChartDoc, readChartSeries } from "./chartSeries";
import { SeriesChart } from "./SeriesChart";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../../specs/020-web-knowledge/contracts/examples");
const read = (name: string): unknown => JSON.parse(readFileSync(join(EXAMPLES, name), "utf-8"));
const index = JSON.parse(readFileSync(join(EXAMPLES, "index-chart-series.json"), "utf-8")) as {
  examples: Array<{ file: string; valid: boolean; class?: string }>;
};
const valid = (name: string): ChartDoc => {
  const doc = readChartSeries(read(`chart-series.valid-${name}.json`));
  if (!doc) throw new Error(`${name} must be read`);
  return doc;
};

describe("FR-020-55 · the reader accepts the contract and nothing else", () => {
  for (const e of index.examples.filter((x) => x.valid)) {
    it(`FR-020-55 · reads the valid example ${e.file}`, () => {
      expect(readChartSeries(read(e.file))).not.toBeNull();
    });
  }
  for (const e of index.examples.filter((x) => !x.valid)) {
    it(`FR-020-55 · refuses the hostile example ${e.file} (${e.class})`, () => {
      expect(readChartSeries(read(e.file))).toBeNull();
    });
  }
  it("FR-020-55 · covers every example file of the corpus", () => {
    const files = readdirSync(EXAMPLES).filter((f) => f.startsWith("chart-series."));
    expect(index.examples.map((e) => e.file).sort()).toEqual(files.sort());
  });
  it("FR-020-55 · refuses what a schema cannot state: a raster of the wrong size, a falling ECDF, a band not around its series", () => {
    const raster = JSON.parse(JSON.stringify(read("chart-series.valid-raster.json")));
    raster.raster.values.pop();
    expect(readChartSeries(raster)).toBeNull();
    const ecdf = JSON.parse(JSON.stringify(read("chart-series.valid-ecdf.json")));
    ecdf.series[0].y = [0.2, 0.4, 0.3, 0.8, 1];
    expect(readChartSeries(ecdf)).toBeNull();
    const band = JSON.parse(JSON.stringify(read("chart-series.valid-line-band.json")));
    band.series[0].lo[2] = 0.5;
    expect(readChartSeries(band)).toBeNull();
    const back = JSON.parse(JSON.stringify(read("chart-series.valid-line-band.json")));
    back.series[0].x = [0, 2, 1, 3, 4];
    expect(readChartSeries(back)).toBeNull();
  });
  it("FR-020-55 · refuses a value that is not an object, a null and an array", () => {
    for (const raw of [null, undefined, 3, "x", [], [{}]]) expect(readChartSeries(raw)).toBeNull();
  });
});

describe("FR-020-56 · every chart shows its axes, units, legend and producer label", () => {
  it("FR-020-56 · a line chart names both axes with their units, its band and the producer of the run", async () => {
    await renderApp(<SeriesChart doc={valid("line-band")} />);
    expect(screen.getByRole("heading", { name: "Example chart" })).toBeTruthy();
    const axes = screen.getByTestId("chart-axes").textContent ?? "";
    expect(axes).toContain("Step (1)");
    expect(axes).toContain("Rollout error (m)");
    expect(document.querySelector('[data-band="error-band"]')?.textContent).toContain(
      "95 % interval, bootstrap",
    );
    const producer = screen.getByTestId("chart-producer").textContent ?? "";
    for (const part of ["warp", "granular DEM", "1.0.0", "fixture of the contract tests, not a result"])
      expect(producer).toContain(part);
  });

  it("FR-020-56 · the data table of a line chart carries the units and both edges of the band", async () => {
    await renderApp(<SeriesChart doc={valid("line-band")} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Show data" })[0] as HTMLElement);
    const heads = [...document.querySelectorAll("th")].map((th) => th.textContent);
    expect(heads).toContain("Step (1)");
    expect(heads).toContain("Mean error (m)");
    expect(heads.some((h) => h?.includes("lower edge") && h.includes("(m)"))).toBe(true);
    expect(heads.some((h) => h?.includes("upper edge") && h.includes("(m)"))).toBe(true);
  });

  it("FR-020-56 · bars carry their error bars, their value unit and a keyboard read-out", async () => {
    await renderApp(<SeriesChart doc={valid("bar-error-bars")} />);
    const bars = document.querySelectorAll("[data-bar]");
    expect(bars).toHaveLength(3);
    expect(document.querySelectorAll("[data-whisker]")).toHaveLength(3);
    expect(screen.getByTestId("series-bar").textContent).toContain("Angle of repose (deg)");
    const widget = screen.getByRole("application", { name: "Example chart" });
    fireEvent.keyDown(widget, { key: "ArrowRight" });
    const out = screen.getByTestId("readout").textContent ?? "";
    expect(out).toContain("Seed 0");
    expect(out).toContain("34.1 deg");
    expect(out).toContain("[33.2, 35]");
    fireEvent.keyDown(widget, { key: "End" });
    expect(screen.getByTestId("readout").textContent).toContain("Seed 2");
  });

  it("FR-020-56 · a scatter and an ECDF go through the interactive chart", async () => {
    await renderApp(
      <>
        <SeriesChart doc={valid("scatter")} />
        <SeriesChart doc={valid("ecdf")} />
      </>,
    );
    expect(document.querySelectorAll('[data-testid="chart"]')).toHaveLength(2);
    expect(document.querySelector('[data-chart-id="example-ecdf"]')).not.toBeNull();
  });

  it("FR-020-56 · a raster shows its colour scale with unit and map, and a cell read-out by keyboard", async () => {
    await renderApp(<SeriesChart doc={valid("raster")} />);
    const scale = screen.getByTestId("colour-scale").textContent ?? "";
    expect(scale).toContain("-2 m");
    expect(scale).toContain("3.25 m");
    expect(scale).toContain("Elevation change");
    expect(scale).toContain("viridis");
    const widget = screen.getByRole("application", { name: "Example chart" });
    fireEvent.keyDown(widget, { key: "ArrowRight" });
    const out = screen.getByTestId("readout").textContent ?? "";
    expect(out).toContain("Easting");
    expect(out).toContain(" m");
  });

  it("FR-020-56 · a section draws its polylines and circles with the legend", async () => {
    await renderApp(<SeriesChart doc={valid("section")} />);
    expect(document.querySelectorAll("[data-polyline]")).toHaveLength(2);
    expect(document.querySelectorAll("[data-circle]")).toHaveLength(1);
    expect(screen.getByTestId("series-section").textContent).toContain("Critical slip circle");
    expect(screen.getByTestId("series-section").textContent).toContain("radius 38.5 m");
  });

  it("FR-020-56 · a table carries its units in the header cells", async () => {
    await renderApp(<SeriesChart doc={valid("table")} />);
    const table = screen.getByTestId("chart-table");
    expect([...table.querySelectorAll("th")].map((th) => th.textContent)).toEqual(["Shell", "Ore (kt)"]);
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("FR-020-56 · the Spanish page shows the Spanish title, labels and producer sentence", async () => {
    await renderApp(<SeriesChart doc={valid("bar-error-bars")} />, { lang: "es" });
    expect(screen.getByRole("heading", { name: "Gráfico de ejemplo" })).toBeTruthy();
    expect(screen.getByTestId("series-bar").textContent).toContain("Ángulo de reposo (deg)");
    expect(screen.getByTestId("chart-producer").textContent).toContain("Producido con warp");
  });

  it("FR-020-56 · no chart source holds a hex colour literal (FR-020-12)", () => {
    for (const f of [
      "BarPlot.tsx",
      "LinePlot.tsx",
      "RasterPlot.tsx",
      "SectionPlot.tsx",
      "SeriesChart.tsx",
      "RunCharts.tsx",
    ]) {
      expect(readFileSync(join(HERE, f), "utf-8")).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    }
  });
});

describe("FR-020-57 · a value not run shows its reason and draws nothing", () => {
  it("FR-020-57 · title, reason and producer label, no axis, no series, no canvas", async () => {
    await renderApp(<SeriesChart doc={valid("not-run")} />);
    expect(screen.getByTestId("chart-not-run").textContent).toContain(
      "The observed signal-to-noise ratio is unavailable.",
    );
    expect(screen.getByTestId("chart-producer")).toBeTruthy();
    expect(document.querySelector("canvas, svg, table")).toBeNull();
    expect(screen.queryByTestId("chart-axes")).toBeNull();
  });

  it("FR-020-57 · the reason is in Spanish on the Spanish page", async () => {
    await renderApp(<SeriesChart doc={valid("not-run")} />, { lang: "es" });
    expect(screen.getByTestId("chart-not-run").textContent).toContain(
      "La relación señal-ruido observada no está disponible.",
    );
  });
});
