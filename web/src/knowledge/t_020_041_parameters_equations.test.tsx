// T-020-041 [red] · FR-020-33 (parameter browser: one row per knowledge-table row with id, value or range, units as published, SI value, citation linked to its bibliography entry, page or table, verification status and code symbol;
// filter by module and status, search by text; every UNVERIFIED row carries the text badge "UNVERIFIED — pinned at specification" with an icon), FR-020-34 (equation explorer: per `minephys` equation the rendered LaTeX, its symbols with units, source
// and page, verification status, the implementing `minephys` symbol, a link to its theory anchor and, where a browser engine implements it, a "Try it" panel that evaluates it with that engine) and FR-000-10.
//
// Expected API (web/src/knowledge/):
//   ParametersSection.tsx   ParametersSection({ parameters: ParameterRow[] }), rows of the knowledge bundle (DC-020-03); the filters are read from the URL query: `module` (a module of the rows), `status` ("verified" | "UNVERIFIED"), `q` (text).
//     Controls: select[data-testid="filter-module"] (an empty option for all, then the modules of the rows, sorted), select[data-testid="filter-status"] (all, verified, UNVERIFIED), input[type="search"][data-testid="search"] (value = q).
//     Rows: tr[data-parameter="<id>"] with [data-field="module|value|units|si|citation|page|verification|symbols"]; value shows `value` or the range "<min> – <max>"; units as published; `si` the SI value and unit; citation an a[href$="#<key>"]
//     (the bibliography anchor of FR-020-38); symbols the code symbols; an UNVERIFIED row has [data-testid="unverified-badge"] with the text "UNVERIFIED — pinned at specification" and an svg icon, a verified one has none.
//     [data-testid="no-match"] "No matching parameters" when the filters leave nothing.
//   EquationsSection.tsx    EquationsSection({ equations: EquationRow[]; evaluate?: (engine: string, equation: string) => Promise<{ value: number; unit: string }> }); `EquationRow` is a bundle equation plus an optional `html` (the KaTeX HTML and MathML
//     rendered at BUILD time: the client never renders LaTeX). Rows: article[data-equation="<id>"] with [data-testid="eq-rendered"] (the `html` as given, else the LaTeX in a code element), a table of symbols with units, the source (citation link) and page,
//     [data-testid="unverified-badge"] when UNVERIFIED, [data-field="function"] (the minephys symbol), a[data-testid="theory-link"][href="/theory/<topic>/#<anchor>"], and, only when the equation has an `engine`, [data-testid="try-it"][data-engine]
//     with button "Try it" that calls `evaluate(engine.id, equation.id)` once per press and shows the result "<value> <unit>" in [data-testid="try-result"] or, on a rejection, an inline [role="alert"] message and no thrown error.
// Oracles: the valid knowledge bundle of DC-020-03 (3 parameters: diesel CO2 verified, Kuz-Ram rock factor range UNVERIFIED, Beverloo exponent UNVERIFIED; 1 equation Bond specific energy with engine comminution), hand variations.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { EquationsSection } from "~/knowledge/EquationsSection";
import { ParametersSection } from "~/knowledge/ParametersSection";
import { renderApp } from "~/test-support/render";

const bundle = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../specs/020-web-knowledge/contracts/examples/knowledge-bundle.valid.json",
    ),
    "utf8",
  ),
) as { parameters: Array<Record<string, unknown>>; equations: Array<Record<string, unknown>> };
const BADGE = "UNVERIFIED — pinned at specification";
const params = (query = "", rows: unknown[] = bundle.parameters) =>
  renderApp(createElement(ParametersSection, { parameters: rows as never }), {
    route: `/knowledge/${query}`,
  });
const ids = () =>
  Array.from(document.querySelectorAll("tr[data-parameter]")).map((r) => r.getAttribute("data-parameter"));
const cell = (id: string, f: string) =>
  document.querySelector(`tr[data-parameter="${id}"] [data-field="${f}"]`)?.textContent ?? "";

describe("parameter browser rows (FR-020-33)", () => {
  it("FR-020-33 · one row per knowledge-table row, in the order of the bundle", async () => {
    await params();
    expect(ids()).toEqual(["diesel_co2_kg_per_us_gal", "kuzram_rock_factor_range", "beverloo_exponent"]);
  });

  it("FR-020-33 · a scalar row shows its value, units as published, SI value and unit, page, verification and code symbol", async () => {
    await params();
    const id = "diesel_co2_kg_per_us_gal";
    expect(cell(id, "value")).toContain("10.21");
    expect(cell(id, "units")).toContain("kg CO2 / US gal");
    expect(cell(id, "si")).toContain("2697.2");
    expect(cell(id, "si")).toContain("kg/m³");
    expect(cell(id, "page")).toContain("Table 2, p. 2");
    expect(cell(id, "verification")).toMatch(/verified/);
    expect(cell(id, "symbols")).toContain("minephys.haulage.co2_from_diesel");
    expect(cell(id, "module")).toContain("haulage");
  });

  it("FR-020-33 · a range row shows min to max, with the SI range", async () => {
    await params();
    expect(cell("kuzram_rock_factor_range", "value")).toMatch(/0\.8\s*[–-]\s*22/);
    expect(cell("kuzram_rock_factor_range", "si")).toMatch(/0\.8\s*[–-]\s*22/);
  });

  it("FR-020-33 · a text value such as 5/2 is shown as given, beside its SI value 2.5", async () => {
    await params();
    expect(cell("beverloo_exponent", "value")).toContain("5/2");
    expect(cell("beverloo_exponent", "si")).toContain("2.5");
  });

  it("FR-020-33 · the citation links to its bibliography entry by anchor", async () => {
    await params();
    expect(
      document
        .querySelector('tr[data-parameter="kuzram_rock_factor_range"] [data-field="citation"] a')
        ?.getAttribute("href"),
    ).toMatch(/#cunningham2005$/);
    expect(cell("kuzram_rock_factor_range", "citation")).toContain("cunningham2005");
  });

  it("FR-020-33 · every UNVERIFIED row carries the badge with its icon, and no verified row does", async () => {
    await params();
    for (const id of ["kuzram_rock_factor_range", "beverloo_exponent"]) {
      const badge = document.querySelector(`tr[data-parameter="${id}"] [data-testid="unverified-badge"]`);
      expect(badge?.textContent, id).toContain(BADGE);
      expect(badge?.querySelector("svg"), id).not.toBeNull();
    }
    expect(
      document.querySelector(
        'tr[data-parameter="diesel_co2_kg_per_us_gal"] [data-testid="unverified-badge"]',
      ),
    ).toBeNull();
  });
});

describe("filters and search (FR-020-33)", () => {
  it("FR-020-33 · the module filter lists the modules of the rows, sorted, and keeps the rows of one module", async () => {
    await params("?module=blasting");
    expect(ids()).toEqual(["kuzram_rock_factor_range"]);
    const options = Array.from(document.querySelectorAll('select[data-testid="filter-module"] option')).map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(options).toEqual(["", "blasting", "bulk", "haulage"]);
  });

  it("FR-020-33 · the status filter keeps verified or UNVERIFIED rows", async () => {
    await params("?status=UNVERIFIED");
    expect(ids()).toEqual(["kuzram_rock_factor_range", "beverloo_exponent"]);
    document.body.innerHTML = "";
    await params("?status=verified");
    expect(ids()).toEqual(["diesel_co2_kg_per_us_gal"]);
  });

  it("FR-020-33 · module and status filters combine", async () => {
    await params("?module=bulk&status=UNVERIFIED");
    expect(ids()).toEqual(["beverloo_exponent"]);
    document.body.innerHTML = "";
    await params("?module=bulk&status=verified");
    expect(ids()).toEqual([]);
    expect(screen.getByTestId("no-match").textContent).toContain("No matching parameters");
  });

  it("FR-020-33 · the text search matches the id, the quantity, the module, the citation key and the code symbol, ignoring case", async () => {
    for (const [q, expected] of [
      ["kuz", ["kuzram_rock_factor_range"]],
      ["DIESEL", ["diesel_co2_kg_per_us_gal"]],
      ["beverloo1961", ["beverloo_exponent"]],
      ["minephys.blasting", ["kuzram_rock_factor_range"]],
      ["bulk", ["beverloo_exponent"]],
      ["emission factor", ["diesel_co2_kg_per_us_gal"]],
      ["zzzz", []],
    ] as Array<[string, string[]]>) {
      document.body.innerHTML = "";
      await params(`?q=${encodeURIComponent(q)}`);
      expect(ids(), q).toEqual(expected);
    }
  });

  it("FR-020-33 · the search field shows the query of the URL", async () => {
    await params("?q=kuz");
    expect((screen.getByTestId("search") as HTMLInputElement).value).toBe("kuz");
  });

  it("FR-020-33 · typing in the field filters the rows without a reload", async () => {
    await params();
    fireEvent.change(screen.getByTestId("search"), { target: { value: "beverloo" } });
    await waitFor(() => expect(ids()).toEqual(["beverloo_exponent"]));
  });

  it("FR-020-33 · an unknown module or status falls back to no filter (FR-020-48)", async () => {
    await params("?module=<script>&status=maybe");
    expect(ids()).toHaveLength(3);
  });
});

describe("equation explorer (FR-020-34)", () => {
  const eq = bundle.equations[0] as Record<string, unknown>;
  const html = '<span class="katex"><math><mi>W</mi></math></span>';
  const render = (equations: unknown[] = [{ ...eq, html }], evaluate?: unknown) =>
    renderApp(
      createElement(EquationsSection, { equations: equations as never, evaluate: evaluate as never }),
    );
  const art = () =>
    document.querySelector<HTMLElement>('article[data-equation="bond_specific_energy"]') as HTMLElement;

  it("FR-020-34 · the equation shows its build-time rendering as given, and its LaTeX as code when there is none", async () => {
    await render();
    expect(art().querySelector('[data-testid="eq-rendered"] math')).not.toBeNull();
    document.body.innerHTML = "";
    await render([eq]);
    expect(art().querySelector('[data-testid="eq-rendered"]')?.textContent).toContain("W = 10");
  });

  it("FR-020-34 · its symbols are tabulated with their meaning and units", async () => {
    await render();
    const rows = Array.from(art().querySelectorAll("table tbody tr")).map((r) => r.textContent ?? "");
    expect(rows).toHaveLength(4);
    expect(rows[0]).toContain("specific energy");
    expect(rows[0]).toContain("kWh/t");
    expect(rows[2]).toContain("µm");
  });

  it("FR-020-34 · source and page, verification, the implementing minephys symbol and the theory link", async () => {
    await render();
    expect(art().textContent).toContain("bond1961");
    expect(art().textContent).toContain("eq. 3");
    expect(art().querySelector('[data-testid="unverified-badge"]')?.textContent).toContain(BADGE);
    expect(art().querySelector('[data-field="function"]')?.textContent).toContain(
      "minephys.comminution.bond_energy",
    );
    expect(art().querySelector('a[data-testid="theory-link"]')?.getAttribute("href")).toBe(
      "/theory/comminution/#eq-bond",
    );
  });

  it("FR-020-34 · a verified equation has no badge", async () => {
    await render([{ ...eq, html, verification: "verified", verified_on: "2026-10-06" }]);
    expect(art().querySelector('[data-testid="unverified-badge"]')).toBeNull();
  });

  it("FR-020-34 · 'Try it' exists only for an equation with a browser engine, and evaluates it once per press, showing the result", async () => {
    const evaluate = vi.fn(async () => ({ value: 11.25, unit: "kWh/t" }));
    await render(
      [
        { ...eq, html },
        { ...eq, id: "plain", html },
      ].map((e, i) => (i === 1 ? { ...e, engine: undefined } : e)),
      evaluate,
    );
    expect(art().querySelector('[data-testid="try-it"][data-engine="comminution"]')).not.toBeNull();
    expect(document.querySelector('article[data-equation="plain"] [data-testid="try-it"]')).toBeNull();
    fireEvent.click(art().querySelector('[data-testid="try-it"] button') as HTMLElement);
    await waitFor(() =>
      expect(art().querySelector('[data-testid="try-result"]')?.textContent).toContain("11.25 kWh/t"),
    );
    expect(evaluate).toHaveBeenCalledTimes(1);
    expect(evaluate).toHaveBeenCalledWith("comminution", "bond_specific_energy");
  });

  it("FR-020-34 · a failing evaluation is an inline alert, not an uncaught error", async () => {
    const evaluate = vi.fn(async () => {
      throw new Error("engine unavailable");
    });
    await render([{ ...eq, html }], evaluate);
    fireEvent.click(art().querySelector('[data-testid="try-it"] button') as HTMLElement);
    await waitFor(() => expect(art().querySelector('[data-testid="try-it"] [role="alert"]')).not.toBeNull());
    expect(art().querySelector('[data-testid="try-result"]')).toBeNull();
  });

  it("FR-020-34 · hostile text in a title or a symbol meaning is escaped", async () => {
    const evil = {
      ...eq,
      html: undefined,
      title: "<img src=x onerror=alert(1)>",
      symbols: [{ symbol: "<b>W</b>", meaning: "<script>alert(1)</script>", units: "kWh/t" }],
    };
    const { container } = await render([evil]);
    expect(container.querySelector("img[src='x'], b, script")).toBeNull();
  });
});
