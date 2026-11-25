// T-020-020 [red] · FR-020-17 (/methods lists M1 to M23 and /methods/<m01...m23>/ is a prerendered page answering 200, any other id 404) and FR-020-18 (a method page: design, criterion, lane, Simulate link, docs page, status) on the built site.
// Unit half: web/src/routes/t_020_020_methods.test.tsx.
//
// Oracles: the 23 page stems of docs/methods/ (m01-match-factor-queueing ... m23-rtx-sensor-simulation) for the ids; for the page of M2 the registry example (lanes live and precompute, cases A1, A2, B1, C3, docs page docs/methods/m02-haulage-des.md);
// the independent test of US-020-4 ("/methods/m02/ shows the DES comparison design and links to /cases/A1/?tab=simulate"). Hooks as in the unit half.
import { readdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const STEMS = readdirSync(resolve("..", "docs", "methods"))
  .filter((f) => /^m\d\d-.*\.md$/.test(f))
  .map((f) => f.slice(0, 3));
const IDS = Array.from({ length: 23 }, (_, i) => `m${String(i + 1).padStart(2, "0")}`);

test.describe("the index (FR-020-17)", () => {
  test("FR-020-17 · the docs hold the 23 method pages the site must mirror (guard of the oracle)", () => {
    expect(STEMS.sort()).toEqual(IDS);
  });

  test("FR-020-17 · /methods/ lists M1 to M23, each with tier, implementation, SPDX licence, lane, cases, learned flag and status", async ({
    page,
  }) => {
    await open(page, "methods/");
    const rows = page.locator('[data-testid="methods-table"] tr[data-method]');
    expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-method")))).toEqual(
      IDS.map((id) => `M${Number(id.slice(1))}`),
    );
    for (const field of ["tiers", "implementation", "spdx", "lanes", "cases", "learned", "status"])
      await expect(rows.first().locator(`[data-field="${field}"]`)).toBeVisible();
    await expect(
      rows.nth(1).locator('[data-field="name"] a, a[href$="/methods/m02/"]').first(),
    ).toBeVisible();
  });

  test("FR-020-17 · every row links to its page, which opens", async ({ page }) => {
    await open(page, "methods/");
    await page.locator('tr[data-method="M2"] a').first().click();
    await expect(page).toHaveURL(/\/methods\/m02\/?$/);
    await expect(page.locator("main h1")).toBeVisible();
  });
});

test.describe("the 23 pages (FR-020-17)", () => {
  for (const id of IDS) {
    test(`FR-020-17 · /methods/${id}/ is a prerendered page answering 200`, async ({ request }) => {
      const res = await request.get(`methods/${id}/`);
      expect(res.status()).toBe(200);
      expect(await res.text()).toContain("<title>");
    });
  }

  for (const [what, id] of [
    ["m00", "m00"],
    ["m24", "m24"],
    ["no zero padding", "m1"],
    ["upper case", "M02"],
    ["an unknown id", "m99"],
    ["the docs stem", "m02-haulage-des"],
    ["an extension", "m02.html"],
    ["an encoded slash", "m02%2Fx"],
    ["markup", "%3Cscript%3E"],
  ] as Array<[string, string]>) {
    test(`FR-020-17 · ${what}: HTTP 404 and the not-found page`, async ({ page }) => {
      const res = await page.goto(`methods/${id}/`);
      expect(res?.status()).toBe(404);
      await open(page, `methods/${id}/`);
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    });
  }
});

test.describe("a method page (FR-020-18)", () => {
  test("FR-020-18 · /methods/m02/ shows what it computes, its lanes, its docs page and links to the Simulate tab of A1", async ({
    page,
  }) => {
    await open(page, "methods/m02/");
    await expect(page.locator("main h1")).toContainText("Haulage DES");
    await expect(page.getByTestId("computes")).toContainText("minehaulsim");
    await expect(page.getByTestId("lane")).toContainText(/live/);
    await expect(page.getByTestId("lane")).toContainText(/estimate|T2/);
    await expect(
      page.locator('[data-testid="simulate-links"] a[href$="/cases/A1/?tab=simulate"]'),
    ).toHaveCount(1);
    await expect(page.locator('[data-testid="docs-link"]')).toContainText(/m02-haulage-des/);
    await expect(page.getByTestId("status")).toContainText("Not yet run");
  });

  test("FR-020-18 · /methods/m04/ shows the comparison design and the recorded criterion of the PPO method", async ({
    page,
  }) => {
    await open(page, "methods/m04/");
    await expect(page.getByTestId("design")).toContainText("SPTF and two-stage LP");
    await expect(page.getByTestId("design")).toContainText("t/h");
    await expect(page.getByTestId("criterion")).toContainText("SC-007-01");
    await expect(page.getByTestId("criterion")).toContainText("excludes 0");
  });

  test("FR-020-18 · following the Simulate link opens the live tab of the case", async ({ page }) => {
    await open(page, "methods/m02/");
    await page.locator('[data-testid="simulate-links"] a').first().click();
    await expect(page).toHaveURL(/\/cases\/A1\/\?tab=simulate$/);
    await expect(page.getByRole("tab", { selected: true })).toContainText(/Simulate/);
  });

  test("FR-020-18 · the page is available in Spanish with the same blocks", async ({ page }) => {
    await open(page, "methods/m04/?lang=es");
    await expect(page.getByTestId("criterion")).toContainText("supera a SPTF o LP");
    await expect(page.getByTestId("design")).toContainText("semilla");
  });
});
