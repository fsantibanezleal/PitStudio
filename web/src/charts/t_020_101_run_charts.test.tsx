// T-020-101 [red] · FR-020-55: the reader draws the chart series of the case's published runs and nothing else. The web manifest lists
// the artefacts of kind chart-series; a file that is missing, invalid or of another case is not drawn; a case with no chart series draws
// nothing. Oracle: the example corpus of DC-020-05 and the artefact record shape of data-model 001 section 2.5.
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderApp } from "~/test-support/render";
import CaseRunCharts from "./RunCharts";
import { chartArtefacts } from "./useChartSeries";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../../specs/020-web-knowledge/contracts/examples");
const example = (name: string) =>
  JSON.parse(readFileSync(join(EXAMPLES, `chart-series.${name}.json`), "utf-8"));

function record(id: string, run: string, cases: string[] | undefined, kind = "chart-series") {
  return {
    id,
    run_id: run,
    git_sha: "abcdef0123456789abcdef0123456789abcdef01",
    path: `assets/${run}/${id}.json`,
    bytes: 100,
    sha256: "1".repeat(64),
    kind,
    producer: { tool: "pitstudio", stage: { id: "s50_evaluate" } },
    inputs: [],
    ...(cases ? { cases } : {}),
    lane: "static",
    licence_class: "own",
    spdx: "CC-BY-4.0",
  };
}

const RUN = "20261124T100000Z-a3-dem-repose-20k";
const OLD = "20261012T061925Z-a3-dem-repose-20k";

function serve(files: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const key = String(url).replace(/^.*?(assets\/)/, "$1");
      return key in files
        ? { ok: true, json: async () => files[key] }
        : { ok: false, json: async () => null };
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("FR-020-55 · which artefacts are charts of the case", () => {
  it("FR-020-55 · only kind chart-series that applies to the case, newest run first, then by id", () => {
    const list = [
      record("b", OLD, ["A3"]),
      record("a", RUN, ["A3"]),
      record("z", RUN, ["A3"]),
      record("c1-chart", RUN, ["C1"]),
      record("all", RUN, undefined),
      record("table", RUN, ["A3"], "table"),
    ] as never[];
    expect(chartArtefacts(list, "A3").map((a) => a.id)).toEqual(["a", "all", "z", "b"]);
  });
});

describe("FR-020-55 · the reader draws the published chart series of the case", () => {
  it("FR-020-55 · draws each valid chart under its run, with the producer label", async () => {
    const bar = example("valid-bar-error-bars");
    const manifest = { kind: "web-index", artefacts: [record("a3-repose-by-seed", RUN, ["A3"])] };
    serve({ "assets/manifest.json": manifest, [`assets/${RUN}/a3-repose-by-seed.json`]: bar });
    await renderApp(<CaseRunCharts caseId="A3" />);
    await waitFor(() => expect(screen.getAllByTestId("chart-series")).toHaveLength(1));
    expect(screen.getByTestId("chart-producer").textContent).toContain("granular DEM");
    expect(document.querySelector(`[data-run-charts="${RUN}"]`)).not.toBeNull();
  });

  it("FR-020-55 · draws nothing for a file that is missing, invalid, or of another case", async () => {
    const bad = { ...example("valid-bar-error-bars"), producer: undefined };
    const other = { ...example("valid-bar-error-bars"), case: "C1" };
    const manifest = {
      kind: "web-index",
      artefacts: [
        record("missing", RUN, ["A3"]),
        record("invalid", RUN, ["A3"]),
        record("other", RUN, ["A3"]),
      ],
    };
    serve({
      "assets/manifest.json": manifest,
      [`assets/${RUN}/invalid.json`]: bad,
      [`assets/${RUN}/other.json`]: other,
    });
    await renderApp(<CaseRunCharts caseId="A3" />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryAllByTestId("chart-series")).toHaveLength(0);
    expect(screen.queryByTestId("run-charts-section")).toBeNull();
  });

  it("FR-020-55 · draws nothing when no run carries a chart series", async () => {
    serve({ "assets/manifest.json": { kind: "web-index", artefacts: [record("t", RUN, ["A3"], "table")] } });
    await renderApp(<CaseRunCharts caseId="A3" />);
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByTestId("run-charts-section")).toBeNull();
  });
});
