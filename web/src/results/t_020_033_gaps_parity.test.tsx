// T-020-033 [red] · FR-020-25 (Sim-to-real tab: the fragmentation TSTR/TRTR IoU ratio against 0.90, the C2ST AUCs with their real-versus-real baseline against 0.60 (tabular and 1-D) or an AUC gap <= 0.10 (images), the sim-to-sim gaps
// (FEE -> MPM fill gap with its 95 % CI, Isaac Lab -> TypeScript twin), "not measured" for equipment and people unless the optional real probe exists, "calibrated synthetic — not validated against real data" for each data type
// without a real reference), FR-020-26 (Parity tab: the parity report of the deployed commit grouped by system class: engine, class, tolerance, maximum observed error, browsers, verdict) and FR-000-09.
//
// Expected API (web/src/results/tabs/):
//   SimToRealTab.tsx   SimToRealTab({ rows: EstimateRow[]; registry: CaseRegistryJson }), `rows` the estimate rows of the published sim-to-real bundles (type of ComparisonRows, kind "estimate", `group` as below, `system` text)
//     hooks: [data-testid="tstr-ratio"] (group "tstr-trtr-iou": value, the threshold "0.9" with its comparator, and `data-met="true|false"`, or "Not yet run" with no number),
//            [data-testid="c2st-row"][data-datatype="tabular|1-d|images"] (groups "c2st-tabular", "c2st-1d", "c2st-images": two rows each, system "synthetic vs real" and "real vs real"): [data-field="auc"], [data-field="baseline"],
//              for tabular and 1-D the criterion "0.6" on the AUC with `data-met`, for images [data-field="gap"] = auc - baseline (computed here, 2 decimals) against "0.1" with `data-met`;
//            [data-testid="sim2sim"][data-group="fee-mpm-fill" | "il-ts-twin"] with the value and, when the row has one, its 95 % interval (lo, hi);
//            [data-testid="not-measured"][data-datatype="equipment" | "people"] reading "not measured" unless a row of group "real-probe-equipment" / "real-probe-people" exists (then its value);
//            [data-testid="synthetic-label"][data-datatype="<synthetic_data label, EN>"] reading "calibrated synthetic — not validated against real data" for every synthetic data type of the case registry whose
//              `validation` is not "validated-against-real", and for none that is.
//   ParityTab.tsx      ParityTab({ report: ParityReport }) (DC-018-05): [data-testid="parity-group"][data-class="<tolerance.class>"] in the order of first appearance, each with tr[data-engine] cells: engine, class, tolerance (the
//     tolerance numbers as text), maximum observed error (the numbers as text, empty for a run that did not happen), browsers (comma separated), verdict: "pass", "fail" or "Not yet run" with its reason for `not_run`.
// Oracles: the valid parity report of DC-018-05 (specs/018-web-cases/contracts/examples/parity-report.valid.json, 7 engines in 7 classes) and the case registry example (DC-018-01) for the synthetic data types, hand-built estimate rows.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ParityTab } from "~/results/tabs/ParityTab";
import { SimToRealTab } from "~/results/tabs/SimToRealTab";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";

const metric = (id: string, unit = "1") => ({
  id,
  name: { en: id, es: id },
  unit,
  orientation: "higher-is-better",
});
const est = (group: string, system: string, value: number, extra: Record<string, unknown> = {}) => ({
  kind: "estimate",
  group,
  metric: metric("m"),
  system,
  n: 5,
  value,
  ...extra,
});
const registry = loadCaseRegistry();
const render = (rows: unknown[]) => renderApp(createElement(SimToRealTab, { rows: rows as never, registry }));
const q = (sel: string) => document.querySelector<HTMLElement>(sel);

describe("Sim-to-real tab (FR-020-25)", () => {
  it("FR-020-25 · the TSTR/TRTR IoU ratio is shown with its value and the 0.90 threshold, met at 0.93 and not met at 0.891", async () => {
    await render([est("tstr-trtr-iou", "U-Net", 0.93, { threshold: { comparator: "ge", value: 0.9 } })]);
    const el = q('[data-testid="tstr-ratio"]');
    expect(el?.textContent).toContain("0.93");
    expect(el?.textContent).toContain("0.9");
    expect(el?.getAttribute("data-met")).toBe("true");
    document.body.innerHTML = "";
    await render([est("tstr-trtr-iou", "U-Net", 0.891, { threshold: { comparator: "ge", value: 0.9 } })]);
    expect(q('[data-testid="tstr-ratio"]')?.getAttribute("data-met")).toBe("false");
    expect(q('[data-testid="tstr-ratio"]')?.textContent).toContain("0.891");
  });

  it("FR-020-25 · without a result the ratio reads 'Not yet run' and shows no number", async () => {
    await render([]);
    const el = q('[data-testid="tstr-ratio"]');
    expect(el?.textContent).toContain("Not yet run");
    expect(el?.textContent?.match(/\d/g) ?? []).toEqual([]);
  });

  it("FR-020-25 · C2ST on tabular and 1-D data: the AUC and its real-versus-real baseline against 0.60", async () => {
    await render([
      est("c2st-tabular", "synthetic vs real", 0.57),
      est("c2st-tabular", "real vs real", 0.5),
      est("c2st-1d", "synthetic vs real", 0.64),
      est("c2st-1d", "real vs real", 0.51),
    ]);
    const tab = q('[data-testid="c2st-row"][data-datatype="tabular"]');
    expect(tab?.querySelector('[data-field="auc"]')?.textContent).toContain("0.57");
    expect(tab?.querySelector('[data-field="baseline"]')?.textContent).toContain("0.5");
    expect(tab?.textContent).toContain("0.6");
    expect(tab?.getAttribute("data-met")).toBe("true");
    expect(q('[data-testid="c2st-row"][data-datatype="1-d"]')?.getAttribute("data-met")).toBe("false");
  });

  it("FR-020-25 · C2ST on images: the gap AUC - baseline is computed and compared with 0.10 (0.68 - 0.55 = 0.13: not met; 0.62 - 0.55 = 0.07: met)", async () => {
    await render([est("c2st-images", "synthetic vs real", 0.68), est("c2st-images", "real vs real", 0.55)]);
    const row = q('[data-testid="c2st-row"][data-datatype="images"]');
    expect(row?.querySelector('[data-field="gap"]')?.textContent).toContain("0.13");
    expect(row?.getAttribute("data-met")).toBe("false");
    document.body.innerHTML = "";
    await render([est("c2st-images", "synthetic vs real", 0.62), est("c2st-images", "real vs real", 0.55)]);
    expect(q('[data-testid="c2st-row"][data-datatype="images"] [data-field="gap"]')?.textContent).toContain(
      "0.07",
    );
    expect(q('[data-testid="c2st-row"][data-datatype="images"]')?.getAttribute("data-met")).toBe("true");
  });

  it("FR-020-25 · a C2ST type with only one of its two rows shows what it has and does not compute a gap", async () => {
    await render([est("c2st-images", "synthetic vs real", 0.68)]);
    expect(
      q('[data-testid="c2st-row"][data-datatype="images"] [data-field="gap"]')?.textContent ?? "",
    ).not.toMatch(/\d/);
  });

  it("FR-020-25 · the sim-to-sim gaps: the FEE -> MPM fill gap with its 95 % CI, and Isaac Lab -> TypeScript twin", async () => {
    await render([
      est("fee-mpm-fill", "FEE vs MPM", 0.04, {
        interval: { lo: 0.01, hi: 0.07, level: 0.95, method: "percentile-bootstrap" },
      }),
      est("il-ts-twin", "Isaac Lab vs twin", 0.02),
    ]);
    const fee = q('[data-testid="sim2sim"][data-group="fee-mpm-fill"]');
    for (const needle of ["0.04", "0.01", "0.07", "95"]) expect(fee?.textContent, needle).toContain(needle);
    expect(q('[data-testid="sim2sim"][data-group="il-ts-twin"]')?.textContent).toContain("0.02");
  });

  it("FR-020-25 · equipment and people read 'not measured' unless the optional real probe exists", async () => {
    await render([]);
    for (const type of ["equipment", "people"])
      expect(q(`[data-testid="not-measured"][data-datatype="${type}"]`)?.textContent, type).toContain(
        "not measured",
      );
    document.body.innerHTML = "";
    await render([est("real-probe-people", "detector on real frames", 0.71)]);
    expect(q('[data-testid="not-measured"][data-datatype="people"]')?.textContent).not.toContain(
      "not measured",
    );
    expect(q('[data-testid="not-measured"][data-datatype="people"]')?.textContent).toContain("0.71");
    expect(q('[data-testid="not-measured"][data-datatype="equipment"]')?.textContent).toContain(
      "not measured",
    );
  });

  it("FR-000-09 · every synthetic data type of the case registry without a real reference is labelled 'calibrated synthetic — not validated against real data', and none that is validated", async () => {
    await render([]);
    const all = Object.values(registry.cases).flatMap((c) => c.synthetic_data);
    const unvalidated = [
      ...new Set(all.filter((s) => s.validation !== "validated-against-real").map((s) => s.label.en)),
    ];
    const validated = [
      ...new Set(all.filter((s) => s.validation === "validated-against-real").map((s) => s.label.en)),
    ].filter((l) => !unvalidated.includes(l));
    expect(unvalidated.length).toBeGreaterThan(0);
    const labelled = Array.from(document.querySelectorAll('[data-testid="synthetic-label"]')).map((e) =>
      e.getAttribute("data-datatype"),
    );
    expect([...labelled].sort()).toEqual([...unvalidated].sort());
    for (const l of unvalidated)
      expect(q(`[data-testid="synthetic-label"][data-datatype="${l}"]`)?.textContent, l).toContain(
        "calibrated synthetic — not validated against real data",
      );
    for (const l of validated)
      expect(q(`[data-testid="synthetic-label"][data-datatype="${l}"]`), l).toBeNull();
  });

  it("FR-020-25 · hostile rows (a NaN value, a system with markup, a group that is not listed) neither crash the tab nor print NaN", async () => {
    await render([
      est("tstr-trtr-iou", "<img src=x onerror=alert(1)>", Number.NaN, {
        threshold: { comparator: "ge", value: 0.9 },
      }),
      est("no-such-group", "x", 1),
      null,
      "x",
    ]);
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN/);
  });
});

describe("Parity tab (FR-020-26)", () => {
  const report = JSON.parse(
    readFileSync(
      resolve(
        dirname(fileURLToPath(import.meta.url)),
        "../../../specs/018-web-cases/contracts/examples/parity-report.valid.json",
      ),
      "utf8",
    ),
  ) as {
    engines: Array<{
      engine: string;
      tolerance: { class: string };
      verdict: string;
      browsers: string[];
      reason?: string;
    }>;
  };

  it("FR-020-26 · one group per system class, in the order of the report, each engine in the group of its class", async () => {
    await renderApp(createElement(ParityTab, { report: report as never }));
    const groups = Array.from(document.querySelectorAll('[data-testid="parity-group"]'));
    expect(groups.map((g) => g.getAttribute("data-class"))).toEqual([
      ...new Set(report.engines.map((e) => e.tolerance.class)),
    ]);
    for (const e of report.engines) {
      const group = document.querySelector(
        `[data-testid="parity-group"][data-class="${e.tolerance.class}"]`,
      ) as HTMLElement;
      expect(
        within(group)
          .getAllByRole("row")
          .some((r) => r.getAttribute("data-engine") === e.engine),
        e.engine,
      ).toBe(true);
    }
  });

  it("FR-020-26 · a row shows the engine, its class, the tolerance numbers, the maximum observed error, the browsers and the verdict", async () => {
    await renderApp(createElement(ParityTab, { report: report as never }));
    const row = (id: string) => document.querySelector<HTMLElement>(`tr[data-engine="${id}"]`) as HTMLElement;
    const blasting = row("blasting").textContent ?? "";
    for (const needle of ["blasting", "analytical-closed-form", "chromium", "firefox", "webkit", "pass"])
      expect(blasting, needle).toContain(needle);
    expect(blasting).toMatch(/1e-9|1\.0e-9|1e-09|10⁻⁹|0\.000000001/);
    expect(blasting).toMatch(/4\.4/);
    expect(row("detector").textContent).toContain("fail");
    expect(row("detector").textContent).toContain("0.71");
    expect(row("detector").textContent).toContain("0.998");
    expect(row("gns").textContent).toContain("pass");
  });

  it("FR-020-26 · a run that did not happen reads 'Not yet run' with its reason, and no browser, no error and no verdict of pass or fail", async () => {
    await renderApp(createElement(ParityTab, { report: report as never }));
    const swe = document.querySelector<HTMLElement>('tr[data-engine="swe"]')?.textContent ?? "";
    expect(swe).toContain("Not yet run");
    expect(swe).toContain("no WebGPU adapter on the CI runner");
    expect(swe).not.toMatch(/\bpass\b|\bfail\b|chromium|firefox|webkit/);
  });

  it("FR-020-26 · an empty report shows no group and does not crash; markup in an engine name is text", async () => {
    await renderApp(createElement(ParityTab, { report: { ...report, engines: [] } as never }));
    expect(document.querySelectorAll('[data-testid="parity-group"]')).toHaveLength(0);
    document.body.innerHTML = "";
    const evil = { ...report, engines: [{ ...report.engines[0], engine: "<img src=x onerror=alert(1)>" }] };
    await renderApp(createElement(ParityTab, { report: evil as never }));
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(screen.getAllByText(/onerror/).length).toBeGreaterThan(0);
  });
});
