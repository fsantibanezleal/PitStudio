// T-018-025 [red] · FR-018-09 (E2E half): `/cases/` on the production build.
// DOM contract: see web/src/routes/t_018_025_catalogue.test.tsx (tables `table[data-table="catalogue" | "coverage" | "tools"]`,
// rows `tr[data-case-id]`, `tr[data-method]`, `tr[data-tool]`, cells `td[data-case]` with `data-marked` / `data-role`).
// Oracles: docs/cases/coverage-matrix.md and docs/cases/tool-matrix.md (via ~/test-support/fixtures), docs/cases/README.md catalogue,
// the valid case registry example (titles, KPIs, sources).
import { expect, test } from "@playwright/test";
import {
  CASE_IDS,
  COVERAGE_MARKS,
  COVERAGE_ORACLE,
  loadCaseRegistry,
  TOOL_ORACLE,
  UNIT_SYMBOLS,
} from "../src/test-support/fixtures";
import { open } from "./helpers";

const registry = loadCaseRegistry();
const METHODS = Array.from({ length: 23 }, (_, i) => `M${i + 1}`);

test.describe("/cases catalogue and matrices (FR-018-09)", () => {
  test("FR-018-09 · /cases shows the catalogue of 12 cases with id, title, category, KPIs, real and synthetic data", async ({
    page,
  }) => {
    await open(page, "cases/");
    const table = page.locator('table[data-table="catalogue"]');
    await expect(table).toBeVisible();
    const rows = table.locator("tbody tr[data-case-id]");
    await expect(rows).toHaveCount(12);
    for (const [i, id] of CASE_IDS.entries()) {
      const row = rows.nth(i);
      const c = registry.cases[id];
      await expect(row).toHaveAttribute("data-case-id", id);
      await expect(row).toContainText(id);
      await expect(row).toContainText(c?.title.en as string);
      await expect(row).toContainText(registry.categories[c?.category as string]?.title.en as string);
      for (const k of c?.kpis ?? []) {
        await expect(row).toContainText(k.name.en);
        const symbol = UNIT_SYMBOLS[k.unit];
        if (symbol) await expect(row).toContainText(symbol);
      }
      for (const s of c?.sources ?? []) await expect(row).toContainText(s);
      for (const s of c?.synthetic_data ?? []) await expect(row).toContainText(s.label.en);
    }
  });

  test("FR-018-09 · the coverage matrix is 23 methods x 12 cases with 34 marks as in docs/cases/coverage-matrix.md", async ({
    page,
  }) => {
    await open(page, "cases/");
    const table = page.locator('table[data-table="coverage"]');
    const rows = table.locator("tbody tr[data-method]");
    await expect(rows).toHaveCount(23);
    for (const [i, method] of METHODS.entries()) {
      const row = rows.nth(i);
      await expect(row).toHaveAttribute("data-method", method);
      await expect(row.locator("th[scope='row']")).toContainText(method);
      await expect(row.locator("td[data-case]")).toHaveCount(12);
      for (const id of CASE_IDS) {
        const expected = (COVERAGE_ORACLE[method] ?? []).includes(id);
        await expect(row.locator(`td[data-case="${id}"]`)).toHaveAttribute("data-marked", String(expected));
      }
    }
    await expect(table.locator('td[data-marked="true"]')).toHaveCount(COVERAGE_MARKS);
  });

  test("FR-018-09 · the tool matrix is 17 studio tools x 12 cases with the marks of docs/cases/tool-matrix.md", async ({
    page,
  }) => {
    await open(page, "cases/");
    const table = page.locator('table[data-table="tools"]');
    const rows = table.locator("tbody tr[data-tool]");
    await expect(rows).toHaveCount(17);
    for (const [tool, oracle] of Object.entries(TOOL_ORACLE)) {
      const row = table.locator(`tbody tr[data-tool="${tool}"]`);
      await expect(row).toHaveCount(1);
      for (const id of CASE_IDS) {
        const role = oracle.named.includes(id)
          ? "named"
          : oracle.supporting.includes(id)
            ? "supporting"
            : "none";
        await expect(row.locator(`td[data-case="${id}"]`)).toHaveAttribute("data-role", role);
      }
    }
    await expect(table.locator('td[data-role="named"]')).toHaveCount(
      Object.values(TOOL_ORACLE).reduce((n, o) => n + o.named.length, 0),
    );
    await expect(table.locator('td[data-role="supporting"]')).toHaveCount(
      Object.values(TOOL_ORACLE).reduce((n, o) => n + o.supporting.length, 0),
    );
  });

  test("FR-018-09 · every table header cell carries a scope", async ({ page }) => {
    await open(page, "cases/");
    for (const name of ["catalogue", "coverage", "tools"]) {
      const headers = page.locator(`table[data-table="${name}"] th`);
      const count = await headers.count();
      expect(count).toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        expect(["col", "row"]).toContain(await headers.nth(i).getAttribute("scope"));
      }
    }
  });

  test("FR-018-09 · the catalogue follows the active language", async ({ page }) => {
    await open(page, "cases/?lang=es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    const rows = page.locator('table[data-table="catalogue"] tbody tr[data-case-id]');
    await expect(rows).toHaveCount(12);
    for (const [i, id] of CASE_IDS.entries()) {
      await expect(rows.nth(i)).toContainText(registry.cases[id]?.title.es as string);
    }
  });
});
