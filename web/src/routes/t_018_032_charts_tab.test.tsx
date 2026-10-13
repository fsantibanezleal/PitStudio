// T-018-032 [red] · FR-018-16 (Charts tab: each KPI with its unit, its baseline, the paired 95 % confidence interval of the difference and the verdict of the decision rule
// FR-020-22; "single real event — no significance test" for the C1 real series; every chart follows FR-020-07..16) and FR-000-05 (a "better" claim needs its interval).
//
// Expected API: `~/cases/ChartsTab` (web/src/cases/ChartsTab.tsx), named export ChartsTab({ caseId: string; registry: CaseRegistryJson; rows: ComparisonRow[] }) where
// `ComparisonRow` is the row type of `~/results/ComparisonRows` (paired, mcnemar, single-event, estimate). For each KPI of the case in the registry (all KPIs, registry order) it renders
//   section[data-kpi-chart="<kpi id>"] with: the KPI name in the active language and its unit symbol, a chart (`[data-testid="chart"]` holding the "Show data" control of FR-020-11),
//   and, when a row with `metric.id` equal to the KPI id is given, its baseline name, the interval text "95 % CI [lo, hi]" with its method (as ComparisonRows writes it) and the
//   verdict derived by `~/results/verdict` (never a stored field); a KPI without a row shows "Not yet run" in place of numbers.
//   A row of kind "single-event" shows "single real event — no significance test" and no interval, no verdict of better or worse.
// Oracles: the decision rule written in FR-020-22 and applied by hand to the intervals below (oriented interval: lo > 0 challenger, hi < 0 baseline, touching 0 no difference;
// lower-is-better flips the orientation); the case registry example (KPIs, units, orientation).
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ChartsTab } from "~/cases/ChartsTab";
import type { ComparisonRow } from "~/results/ComparisonRows";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";

const registry = loadCaseRegistry();
const a1 = registry.cases.A1 as {
  kpis: Array<{ id: string; name: { en: string; es: string }; unit: string; orientation: string }>;
};
const c1 = registry.cases.C1 as typeof a1;

const metric = (k: (typeof a1.kpis)[number]) => ({
  id: k.id,
  name: k.name,
  unit: k.unit,
  orientation: k.orientation,
});
const pairing = { en: "shifts", es: "turnos" };
const paired = (k: (typeof a1.kpis)[number], lo: number, hi: number): ComparisonRow => ({
  kind: "paired",
  metric: metric(k),
  n: 30,
  challenger: "learned dispatcher",
  baseline: "shortest-queue rule",
  pairing_unit: pairing,
  interval: { lo, hi, level: 0.95, method: "paired-t" },
});
const section = (id: string) => document.querySelector(`section[data-kpi-chart="${id}"]`) as HTMLElement;

describe("one section per KPI (FR-018-16)", () => {
  it("FR-018-16 · every KPI of the case has its section, in registry order, with its name and unit symbol", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [] }));
    const ids = Array.from(document.querySelectorAll("section[data-kpi-chart]")).map((s) =>
      s.getAttribute("data-kpi-chart"),
    );
    expect(ids).toEqual(a1.kpis.map((k) => k.id));
    const throughput = a1.kpis.find((k) => k.id === "throughput");
    expect(within(section("throughput")).getByText(throughput?.name.en as string)).toBeTruthy();
    expect(section("throughput").textContent).toContain("t/h");
  });

  it("FR-018-16 · the names follow the active language", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [] }), { lang: "es" });
    expect(within(section("throughput")).getByText(a1.kpis[0]?.name.es as string)).toBeTruthy();
  });

  it("FR-018-16 · a KPI without a result row says 'Not yet run' and shows no interval or verdict", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [] }));
    for (const k of a1.kpis) {
      const text = section(k.id).textContent ?? "";
      expect(text, k.id).toContain("Not yet run");
      expect(text, k.id).not.toMatch(/95 %|better than|no significant difference/);
    }
  });

  it("FR-018-16 · every KPI chart carries the interactive-chart controls: a chart element with its 'Show data' button (FR-020-11)", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [] }));
    for (const k of a1.kpis) {
      const chart = within(section(k.id)).getByTestId("chart");
      expect(within(chart).getByRole("button", { name: /Show data/i })).toBeTruthy();
    }
  });
});

describe("baseline, interval and verdict (FR-018-16, FR-020-22, FR-000-05)", () => {
  const throughput = a1.kpis.find((k) => k.id === "throughput") as (typeof a1.kpis)[number]; // higher is better
  const queue = a1.kpis.find((k) => k.id === "queue_time") as (typeof a1.kpis)[number]; // lower is better

  it("FR-018-16 · a higher-is-better KPI whose 95 % interval lies above 0 shows the baseline, the interval with its method and '<challenger> better than <baseline>'", async () => {
    expect(throughput.orientation).toBe("higher-is-better");
    await renderApp(
      createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(throughput, 2.1, 5.3)] }),
    );
    const text = section("throughput").textContent ?? "";
    expect(text).toContain("shortest-queue rule");
    expect(text).toMatch(/95 %/);
    expect(text).toContain("2.1");
    expect(text).toContain("5.3");
    expect(text).toContain("learned dispatcher better than shortest-queue rule");
    expect(text).not.toContain("Not yet run");
  });

  it("FR-020-22 · an interval that touches 0 reads 'no significant difference', also at the upper end", async () => {
    for (const [lo, hi] of [
      [-0.5, 1],
      [0, 3],
      [-2, 0],
      [-1, 1],
    ] as Array<[number, number]>) {
      const { unmount } = await renderApp(
        createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(throughput, lo, hi)] }),
      );
      expect(section("throughput").textContent, `[${lo}, ${hi}]`).toContain("no significant difference");
      expect(section("throughput").textContent).not.toMatch(/better than/);
      unmount();
    }
  });

  it("FR-020-22 · an interval entirely below 0 on a higher-is-better KPI means the baseline is better", async () => {
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(throughput, -4, -1)] }));
    expect(section("throughput").textContent).toContain("shortest-queue rule better than learned dispatcher");
  });

  it("FR-020-22 · a lower-is-better KPI flips the orientation: an interval below 0 favours the challenger", async () => {
    expect(queue.orientation).toBe("lower-is-better");
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(queue, -4, -1)] }));
    expect(section("queue_time").textContent).toContain("learned dispatcher better than shortest-queue rule");
    const { unmount } = await renderApp(
      createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(queue, 1, 4)] }),
    );
    expect(document.querySelectorAll('section[data-kpi-chart="queue_time"]')[1]?.textContent).toContain(
      "shortest-queue rule better than learned dispatcher",
    );
    unmount();
  });

  it("FR-000-05 · a stored verdict is never shown: a row that claims 'challenger' with an interval touching 0 still reads 'no significant difference'", async () => {
    const lying = { ...paired(throughput, -1, 2), verdict: "challenger-better" } as unknown as ComparisonRow;
    await renderApp(createElement(ChartsTab, { caseId: "A1", registry, rows: [lying] }));
    expect(section("throughput").textContent).toContain("no significant difference");
  });

  it("FR-018-16 · a row for another KPI or another case's KPI id does not leak into this tab", async () => {
    await renderApp(
      createElement(ChartsTab, {
        caseId: "A1",
        registry,
        rows: [paired(c1.kpis[0] as (typeof a1.kpis)[number], 1, 2)],
      }),
    );
    expect(document.querySelector('section[data-kpi-chart="fos"]')).toBeNull();
    for (const k of a1.kpis) expect(section(k.id).textContent).toContain("Not yet run");
  });

  it("FR-018-16 · a malformed interval (NaN, lo above hi) claims nothing: no 'better than'", async () => {
    for (const [lo, hi] of [
      [Number.NaN, 1],
      [3, 2],
      [Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY],
    ] as Array<[number, number]>) {
      const { unmount } = await renderApp(
        createElement(ChartsTab, { caseId: "A1", registry, rows: [paired(throughput, lo, hi)] }),
      );
      expect(section("throughput").textContent).not.toMatch(/better than/);
      unmount();
    }
  });
});

describe("the single real event of C1 (FR-018-16, FR-000-05)", () => {
  const fos = c1.kpis.find((k) => k.id === "fos") as (typeof a1.kpis)[number];

  it("FR-018-16 · the C1 real series shows 'single real event — no significance test', its two values, and no interval or verdict", async () => {
    const row: ComparisonRow = {
      kind: "single-event",
      metric: metric(fos),
      n: 1,
      challenger: "inverse velocity",
      baseline: "forecaster",
      challenger_value: 12.5,
      baseline_value: 9.75,
    };
    await renderApp(createElement(ChartsTab, { caseId: "C1", registry, rows: [row] }));
    const text = section("fos").textContent ?? "";
    expect(text).toContain("single real event — no significance test");
    expect(text).toContain("12.5");
    expect(text).toContain("9.75");
    expect(text).not.toMatch(/95 %|better than|no significant difference/);
  });

  it("FR-018-16 · the Spanish wording of the same note is used in ES", async () => {
    const row: ComparisonRow = {
      kind: "single-event",
      metric: metric(fos),
      n: 1,
      challenger: "a",
      baseline: "b",
      challenger_value: 1,
      baseline_value: 2,
    };
    await renderApp(createElement(ChartsTab, { caseId: "C1", registry, rows: [row] }), { lang: "es" });
    expect(screen.getByText(/evento real único/i)).toBeTruthy();
  });
});
