// T-018-025 [red] · FR-018-09 (unit half): the catalogue, the coverage matrix and the tool matrix of `/cases`.
//
// Expected component API:
//   module  ~/cases/CatalogueView   export  function CatalogueView(props: {
//                                      registry: CaseRegistry;             // DC-018-01 document
//                                      tools:    ToolRegistryEntry[];      // entries of studio/tools.yaml: { id, name, category: "studio-tool" | "component", status, ... }
//                                    })
//   It renders three HTML tables, in this order, each `table[data-table="catalogue" | "coverage" | "tools"]`; every `th` in them has
//   a `scope` attribute ("col" in the header row, "row" for the first cell of a body row).
//   catalogue : 12 `tbody tr[data-case-id]` in canonical order; each row shows the case id, `title[lang]`, its category (letter and
//               `categories[letter].title[lang]`), every KPI as name + display unit symbol, every real data source id (`sources`), and every
//               synthetic data label (`synthetic_data[].label[lang]`).
//   coverage  : header cells with the 12 case ids in canonical order; 23 `tbody tr[data-method="M1"..."M23"]` in order, first cell
//               `th[scope=row]` containing the method id; per row 12 `td[data-case="<id>"]` in canonical order with
//               `data-marked="true"` (text "●") iff the case lists the method, else `data-marked="false"` (no "●").
//   tools     : one `tbody tr[data-tool="<tool id>"]` per STUDIO tool (category "studio-tool") that at least one case lists, in the order of
//               `tools`; component entries (minephys, colmap, ...) and unreferenced studio tools (evaluated-not-adopted) get no row; first
//               cell `th[scope=row]` containing the tool `name`; per row 12 `td[data-case]` with `data-role="named"` (text "●"),
//               "supporting" (text "○") or "none" (no mark) from the case's `tools` map.
//   Everything is generated from the registry; nothing is hard-coded in the component.
// Oracles: docs/cases/coverage-matrix.md (23 x 12, 34 marks) and docs/cases/tool-matrix.md (17 studio tools) transcribed in
//          ~/test-support/fixtures; the catalogue of docs/cases/README.md; registry example of DC-018-01.
import { within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CatalogueView } from "~/cases/CatalogueView";
import {
  CASE_IDS,
  type CaseRegistryJson,
  COVERAGE_MARKS,
  COVERAGE_ORACLE,
  loadCaseRegistry,
  TOOL_ENTRIES,
  TOOL_ORACLE,
  UNIT_SYMBOLS,
  withReversedKeys,
} from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const registry = loadCaseRegistry();
const METHODS = Array.from({ length: 23 }, (_, i) => `M${i + 1}`);
const TOOL_IDS = Object.keys(TOOL_ORACLE);

async function view(reg: CaseRegistryJson = registry, lang: "en" | "es" = "en") {
  const utils = await renderApp(<CatalogueView registry={props(reg)} tools={props(TOOL_ENTRIES)} />, {
    lang,
  });
  const table = (name: string) => {
    const t = utils.container.querySelector<HTMLTableElement>(`table[data-table="${name}"]`);
    if (!t) throw new Error(`no table ${name}`);
    return t;
  };
  return { ...utils, table };
}

describe("catalogue table (FR-018-09)", () => {
  it("FR-018-09 · renders three tables in the order catalogue, coverage, tools, with scoped header cells", async () => {
    const { container } = await view();
    const tables = [...container.querySelectorAll("table")];
    expect(tables.map((t) => t.dataset.table)).toEqual(["catalogue", "coverage", "tools"]);
    for (const table of tables) {
      const headers = [...table.querySelectorAll("th")];
      expect(headers.length).toBeGreaterThan(0);
      for (const th of headers) expect(["col", "row"]).toContain(th.getAttribute("scope"));
      expect(table.querySelectorAll("thead th[scope='col']").length).toBeGreaterThan(0);
      for (const tr of table.querySelectorAll("tbody tr")) {
        expect(tr.querySelector("th[scope='row']")).not.toBeNull();
      }
    }
  });

  it("FR-018-09 · the catalogue has 12 rows with id, title, category, KPIs with units, real and synthetic data", async () => {
    const { table } = await view();
    const rows = [...table("catalogue").querySelectorAll<HTMLElement>("tbody tr[data-case-id]")];
    expect(rows.map((r) => r.dataset.caseId)).toEqual([...CASE_IDS]);
    for (const row of rows) {
      const id = row.dataset.caseId as string;
      const c = registry.cases[id];
      const text = row.textContent ?? "";
      expect(text).toContain(id);
      expect(text).toContain(c?.title.en);
      expect(text).toContain(registry.categories[c?.category as string]?.title.en);
      for (const k of c?.kpis ?? []) {
        expect(text).toContain(k.name.en);
        const symbol = UNIT_SYMBOLS[k.unit];
        if (symbol) expect(text).toContain(symbol);
      }
      for (const s of c?.sources ?? []) expect(text).toContain(s);
      for (const s of c?.synthetic_data ?? []) expect(text).toContain(s.label.en);
    }
  });

  it("FR-018-09 · the catalogue rows follow the canonical order whatever the key order of the registry", async () => {
    const { table } = await view(withReversedKeys(registry));
    const ids = [...table("catalogue").querySelectorAll<HTMLElement>("tbody tr[data-case-id]")].map(
      (r) => r.dataset.caseId,
    );
    expect(ids).toEqual([...CASE_IDS]);
  });

  it("FR-018-09 · the catalogue is generated in the active language (ES)", async () => {
    const { table } = await view(registry, "es");
    for (const row of table("catalogue").querySelectorAll<HTMLElement>("tbody tr[data-case-id]")) {
      const c = registry.cases[row.dataset.caseId as string];
      expect(row.textContent).toContain(c?.title.es);
      expect(row.textContent).toContain(registry.categories[c?.category as string]?.title.es);
    }
  });
});

describe("coverage matrix (FR-018-09)", () => {
  it("FR-018-09 · is 23 methods x 12 cases with the marks of docs/cases/coverage-matrix.md", async () => {
    const { table } = await view();
    const t = table("coverage");
    const headerTexts = [...t.querySelectorAll("thead th[scope='col']")].map((th) => th.textContent ?? "");
    const caseHeaders = headerTexts.filter((h) => (CASE_IDS as readonly string[]).includes(h.trim()));
    expect(caseHeaders.map((h) => h.trim())).toEqual([...CASE_IDS]);

    const rows = [...t.querySelectorAll<HTMLElement>("tbody tr[data-method]")];
    expect(rows.map((r) => r.dataset.method)).toEqual(METHODS);
    let marks = 0;
    for (const row of rows) {
      const method = row.dataset.method as string;
      expect(row.querySelector("th[scope='row']")?.textContent).toContain(method);
      const cells = [...row.querySelectorAll<HTMLElement>("td[data-case]")];
      expect(cells.map((c) => c.dataset.case)).toEqual([...CASE_IDS]);
      for (const cell of cells) {
        const expected = (COVERAGE_ORACLE[method] ?? []).includes(cell.dataset.case as string);
        expect(cell.dataset.marked, `${method} x ${cell.dataset.case}`).toBe(String(expected));
        expect(cell.textContent?.includes("●"), `${method} x ${cell.dataset.case} mark`).toBe(expected);
        if (expected) marks += 1;
      }
    }
    expect(marks).toBe(COVERAGE_MARKS);
  });

  it("FR-018-09 · every method row has at least one mark and every case column has at least one (docs: 23 of 23 methods covered)", async () => {
    const { table } = await view();
    const t = table("coverage");
    for (const row of t.querySelectorAll("tbody tr[data-method]")) {
      expect(row.querySelectorAll('td[data-marked="true"]').length).toBeGreaterThanOrEqual(1);
    }
    for (const id of CASE_IDS) {
      expect(t.querySelectorAll(`td[data-case="${id}"][data-marked="true"]`).length).toBeGreaterThanOrEqual(
        1,
      );
    }
    // docs: methods per case 5 3 4 4 3 3 1 2 3 2 2 2
    const perCase = CASE_IDS.map(
      (id) => t.querySelectorAll(`td[data-case="${id}"][data-marked="true"]`).length,
    );
    expect(perCase).toEqual([5, 3, 4, 4, 3, 3, 1, 2, 3, 2, 2, 2]);
  });
});

describe("tool matrix (FR-018-09)", () => {
  it("FR-018-09 · is the 17 studio tools x 12 cases with the marks of docs/cases/tool-matrix.md", async () => {
    const { table } = await view();
    const rows = [...table("tools").querySelectorAll<HTMLElement>("tbody tr[data-tool]")];
    expect(rows.map((r) => r.dataset.tool)).toEqual(TOOL_IDS);
    expect(rows).toHaveLength(17);
    for (const row of rows) {
      const tool = row.dataset.tool as string;
      const oracle = TOOL_ORACLE[tool] as { named: string[]; supporting: string[] };
      expect(row.querySelector("th[scope='row']")?.textContent).toContain(`Tool ${tool}`);
      const cells = [...row.querySelectorAll<HTMLElement>("td[data-case]")];
      expect(cells.map((c) => c.dataset.case)).toEqual([...CASE_IDS]);
      for (const cell of cells) {
        const id = cell.dataset.case as string;
        const role = oracle.named.includes(id)
          ? "named"
          : oracle.supporting.includes(id)
            ? "supporting"
            : "none";
        expect(cell.dataset.role, `${tool} x ${id}`).toBe(role);
        expect(cell.textContent?.includes("●"), `${tool} x ${id} named mark`).toBe(role === "named");
        expect(cell.textContent?.includes("○"), `${tool} x ${id} supporting mark`).toBe(
          role === "supporting",
        );
      }
    }
  });

  it("FR-018-09 · gives no row to component entries (minephys, colmap, ...) or to studio tools no case lists", async () => {
    const { table } = await view();
    const ids = [...table("tools").querySelectorAll<HTMLElement>("tbody tr[data-tool]")].map(
      (r) => r.dataset.tool,
    );
    for (const absent of ["minephys", "minehaulsim", "oreblocks", "colmap", "brush", "pitstudio"]) {
      expect(ids).not.toContain(absent);
    }
    for (const absent of ["cuopt", "physicsnemo", "cosmos-predict-transfer"])
      expect(ids).not.toContain(absent);
  });

  it("FR-018-09 · every one of the 17 tools has at least one mark", async () => {
    const { table } = await view();
    for (const row of table("tools").querySelectorAll("tbody tr[data-tool]")) {
      expect(
        row.querySelectorAll('td[data-role="named"], td[data-role="supporting"]').length,
      ).toBeGreaterThanOrEqual(1);
    }
  });
});

describe("generated from the registry (FR-018-09)", () => {
  it("FR-018-09 · a changed registry changes the tables: moving M1 to B2 moves its mark and its totals", async () => {
    const changed = structuredClone(registry) as CaseRegistryJson;
    (changed.cases.A1 as { methods: string[] }).methods = (changed.cases.A1?.methods ?? []).filter(
      (m) => m !== "M1",
    );
    (changed.cases.B2 as { methods: string[] }).methods = [...(changed.cases.B2?.methods ?? []), "M1"];
    const { table } = await view(changed);
    const row = table("coverage").querySelector("tbody tr[data-method='M1']") as HTMLElement;
    expect(
      [...row.querySelectorAll("td[data-marked='true']")].map((c) => (c as HTMLElement).dataset.case),
    ).toEqual(["B2"]);
  });

  it("FR-018-09 · renders registry text as text: markup in a title, KPI name or synthetic label creates no element", async () => {
    const hostile = structuredClone(registry) as CaseRegistryJson;
    const evil = '<img src=x onerror="alert(1)">';
    const a1 = hostile.cases.A1 as CaseRegistryJson["cases"][string];
    a1.title.en = evil;
    (a1.kpis[0] as { name: { en: string } }).name.en = evil;
    (a1.synthetic_data[0] as { label: { en: string } }).label.en = evil;
    const { container } = await view(hostile);
    expect(container.querySelector("img")).toBeNull();
    expect(within(container).getAllByText(/alert\(1\)/).length).toBeGreaterThan(0);
  });
});
