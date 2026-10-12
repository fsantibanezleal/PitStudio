// T-018-022 [red] · FR-018-05 (unit half; tasks.md lists only the E2E file for T-018-022, the spec says "unit + E2E").
//
// Expected component API:
//   module  ~/cases/KpiTable        export  function KpiTable(props: { items: KpiItem[] })
//     KpiItem = {
//       kpi:      { id; name: {en, es}; unit /* DC-018-01 kpi_unit id, e.g. "t/h", "km2" */; orientation; headline };
//       value:    number | null;           // null = no published artefact for this KPI
//       artefact: ArtefactRecord | null;   // the web-manifest record (data-model 001 section 2.5) the value comes from
//     }
//   DOM contract: one `[data-kpi="<kpi id>"]` row per item, in the given order, containing
//     - the KPI name in the active language and the display symbol of its unit (km2 -> "km²", ug/m3 -> "µg/m³", ...);
//     - with a value: the number (up to four significant figures, plain decimal), the lane badge text LIVE / REPLAY / STATIC
//       (from `artefact.lane`) and the provenance chip: producer tool id, run id and the 7-hex commit of the artefact;
//     - without a value (value null, or artefact null, or a non-finite number): the text "Not yet run" in place of the value,
//       no lane badge, no provenance chip, and never the text NaN, Infinity, null or undefined (FR-018-05).
// Oracles: hand-written KPI values and manifest records; display symbols from docs/cases/README.md.
import { describe, expect, it } from "vitest";
import { KpiTable } from "~/cases/KpiTable";
import { GIT_SHA, loadCaseRegistry, makeArtefact, RUN_ID } from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const registry = loadCaseRegistry();
const a1 = registry.cases.A1?.kpis ?? [];
const c2 = registry.cases.C2?.kpis ?? [];
const c3 = registry.cases.C3?.kpis ?? [];

function row(container: HTMLElement, id: string): HTMLElement {
  const el = container.querySelector<HTMLElement>(`[data-kpi="${id}"]`);
  if (!el) throw new Error(`no row for KPI ${id}`);
  return el;
}

describe("KPI table (FR-018-05)", () => {
  it("FR-018-05 · shows value, unit, lane badge and provenance chip for a KPI with a published artefact", async () => {
    const throughput = a1.find((k) => k.id === "throughput");
    const artefact = makeArtefact({
      id: "a1-kpis",
      lane: "live",
      producer: { tool: "minehaulsim", stage: { id: "s40_infer" } },
    });
    const { container } = await renderApp(
      <KpiTable items={props([{ kpi: throughput, value: 142.5, artefact }])} />,
    );
    const r = row(container, "throughput");
    const text = r.textContent ?? "";
    expect(text).toContain(throughput?.name.en);
    expect(text).toContain("142.5");
    expect(text).toContain("t/h");
    expect(text).toContain("LIVE");
    expect(text).toContain("minehaulsim");
    expect(text).toContain(RUN_ID);
    expect(text).toContain(GIT_SHA.slice(0, 7));
    expect(text).not.toContain("Not yet run");
  });

  it("FR-018-05 · the lane badge follows the artefact: REPLAY and STATIC", async () => {
    const [k1, k2] = a1;
    const replay = makeArtefact({ lane: "replay" });
    const stat = makeArtefact({ lane: "static", kind: "table", budget_class: "own-code" });
    const { container } = await renderApp(
      <KpiTable
        items={props([
          { kpi: k1, value: 10, artefact: replay },
          { kpi: k2, value: 2.5, artefact: stat },
        ])}
      />,
    );
    expect(row(container, k1?.id as string).textContent).toContain("REPLAY");
    expect(row(container, k2?.id as string).textContent).toContain("STATIC");
    expect(row(container, k1?.id as string).textContent).not.toContain("STATIC");
  });

  it("FR-018-05 · shows 'Not yet run' in place of the value for a KPI without a published artefact", async () => {
    const { container } = await renderApp(
      <KpiTable items={props(a1.map((kpi) => ({ kpi, value: null, artefact: null })))} />,
    );
    for (const kpi of a1) {
      const text = row(container, kpi.id).textContent ?? "";
      expect(text).toContain("Not yet run");
      expect(text).toContain(kpi.name.en);
      expect(text).not.toMatch(/LIVE|REPLAY|STATIC/);
      expect(text).not.toContain(RUN_ID);
      expect(text).not.toMatch(/NaN|Infinity|undefined|null/);
    }
  });

  it("FR-018-05 · mixes published and unpublished KPIs of one case, each by its own artefact", async () => {
    const [k1, k2, k3] = a1;
    const { container } = await renderApp(
      <KpiTable
        items={props([
          { kpi: k1, value: 142.5, artefact: makeArtefact({ lane: "live" }) },
          { kpi: k2, value: null, artefact: null },
          { kpi: k3, value: 7.8, artefact: makeArtefact({ lane: "replay" }) },
        ])}
      />,
    );
    expect(row(container, k1?.id as string).textContent).toContain("142.5");
    expect(row(container, k2?.id as string).textContent).toContain("Not yet run");
    expect(row(container, k3?.id as string).textContent).toContain("7.8");
    expect(container.querySelectorAll("[data-kpi]")).toHaveLength(3);
    expect(container.textContent?.match(/Not yet run/g)).toHaveLength(1);
  });

  it("FR-018-05 · writes unit ids as display symbols (km2 -> km², ug/m3 -> µg/m³, L/(t.km) -> L/(t·km))", async () => {
    const area = c2.find((k) => k.unit === "km2");
    const conc = c3.find((k) => k.unit === "ug/m3");
    const fuel = (registry.cases.A2?.kpis ?? []).find((k) => k.unit === "L/(t.km)");
    const { container } = await renderApp(
      <KpiTable
        items={props([
          { kpi: area, value: 1.2, artefact: makeArtefact() },
          { kpi: conc, value: 35.4, artefact: makeArtefact() },
          { kpi: fuel, value: 0.45, artefact: makeArtefact() },
        ])}
      />,
    );
    expect(row(container, area?.id as string).textContent).toContain("km²");
    expect(row(container, conc?.id as string).textContent).toContain("µg/m³");
    expect(row(container, fuel?.id as string).textContent).toContain("L/(t·km)");
  });

  it("FR-018-05 · names follow the active language (ES)", async () => {
    const kpi = a1[0];
    const { container } = await renderApp(
      <KpiTable items={props([{ kpi, value: 5, artefact: makeArtefact() }])} />,
      { lang: "es" },
    );
    expect(row(container, kpi?.id as string).textContent).toContain(kpi?.name.es);
  });

  it("FR-018-05 · never prints a non-finite number: NaN, Infinity and -Infinity are shown as 'Not yet run'", async () => {
    const [k1, k2, k3] = a1;
    const { container } = await renderApp(
      <KpiTable
        items={props([
          { kpi: k1, value: Number.NaN, artefact: makeArtefact() },
          { kpi: k2, value: Number.POSITIVE_INFINITY, artefact: makeArtefact() },
          { kpi: k3, value: Number.NEGATIVE_INFINITY, artefact: makeArtefact() },
        ])}
      />,
    );
    expect(container.textContent).not.toMatch(/NaN|Infinity/);
    expect(container.textContent?.match(/Not yet run/g)).toHaveLength(3);
  });

  it("FR-018-05 · a number without a manifest artefact is not shown: there is no provenance, so no value and no badge", async () => {
    const kpi = a1[0];
    const { container } = await renderApp(<KpiTable items={props([{ kpi, value: 9, artefact: null }])} />);
    const text = row(container, kpi?.id as string).textContent ?? "";
    expect(text).toContain("Not yet run");
    expect(text).not.toMatch(/LIVE|REPLAY|STATIC/);
    expect(text).not.toContain("9");
  });
});
