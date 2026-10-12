// T-020-034 [red] · FR-020-27 (E2E half): the Cosmos tab of /results shows the published Cosmos bundle (balanced accuracy per question type with its interval, the Q8_0 agreement, the McNemar verdict, the attribution
// "Built on NVIDIA Cosmos") and no Cosmos result is a headline KPI on `/` or on a case page. Unit half: web/src/results/t_020_034_cosmos.test.tsx.
//
// The build under test holds the published results bundles of web/e2e/fixtures/results/ (the four valid examples of DC-020-02: a comparison, a single event, a Cosmos comparison and an acceleration bundle), copied to
// `web/public/results/` before the build by the environment variable `RESULTS_DIR=e2e/fixtures/results` (a contract the green commit and the CI job must provide, flagged in the report).
// Hooks: as in the unit half; the KPI panel of the case pages and of `/` is [data-testid="kpi-panel"] with [data-kpi="<kpi id>"] (T-018-021/022).
// Oracles: the facts of the Cosmos fixture (person-in-zone: Cosmos Reason 2 0.81 [0.77, 0.85], Qwen3-VL-2B 0.78, McNemar p = 0.27 with b = 31, c = 22, Q8_0 agreement 0.97 against 0.95) and the headline KPIs of the case registry example.
import { expect, test } from "@playwright/test";
import { CASE_IDS, headlineKpis, loadCaseRegistry } from "../src/test-support/fixtures";
import { open } from "./helpers";

const registry = loadCaseRegistry();

test.describe("the Cosmos tab (FR-020-27)", () => {
  test("FR-020-27 · /results/?tab=cosmos shows the question type with Cosmos 0.81, Qwen 0.78 and their intervals", async ({
    page,
  }) => {
    await open(page, "results/?tab=cosmos");
    const type = page.locator('[data-testid="cosmos-type"][data-qtype="person-in-zone"]');
    await expect(type).toBeVisible();
    await expect(
      type.locator('[data-testid="cosmos-system"][data-system="Cosmos Reason 2"] [data-field="value"]'),
    ).toContainText("0.81");
    await expect(
      type.locator('[data-testid="cosmos-system"][data-system="Cosmos Reason 2"] [data-field="interval"]'),
    ).toContainText(/0\.77.*0\.85/);
    await expect(
      type.locator('[data-testid="cosmos-system"][data-system="Qwen3-VL-2B"] [data-field="value"]'),
    ).toContainText("0.78");
    await expect(
      type.locator('[data-testid="cosmos-system"][data-system="detector + geometric rule"]'),
    ).toContainText("Not yet run");
  });

  test("FR-020-27 · the McNemar line reads p = 0.27 and 'no significant difference'; the Q8_0 agreement reads 0.97 against 95 %", async ({
    page,
  }) => {
    await open(page, "results/?tab=cosmos");
    await expect(page.getByTestId("cosmos-mcnemar")).toContainText("0.27");
    await expect(page.getByTestId("cosmos-mcnemar")).toContainText("no significant difference");
    await expect(page.getByTestId("q8-agreement")).toContainText("0.97");
    await expect(page.getByTestId("q8-agreement")).toHaveAttribute("data-met", "true");
  });

  test("FR-020-27 · the tab carries 'Built on NVIDIA Cosmos', in English and in Spanish", async ({
    page,
  }) => {
    await open(page, "results/?tab=cosmos");
    await expect(page.getByTestId("cosmos-attribution")).toContainText("Built on NVIDIA Cosmos");
    await open(page, "results/?tab=cosmos&lang=es");
    await expect(page.getByTestId("cosmos-attribution")).toContainText("NVIDIA Cosmos");
  });
});

test.describe("no Cosmos result as a headline (FR-020-27)", () => {
  test("FR-020-27 · `/` shows no Cosmos KPI for any of the 12 cases, whatever is published", async ({
    page,
  }) => {
    for (const id of CASE_IDS) {
      await open(page, `?case=${id}`);
      const panel = page.getByTestId("kpi-panel");
      await expect(panel).toHaveAttribute("data-case", id);
      const ids = await panel
        .locator("[data-kpi]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-kpi")));
      expect(ids.sort(), id).toEqual(
        headlineKpis(registry, id)
          .map((k) => k.id)
          .sort(),
      );
      await expect(panel, id).not.toContainText(/Cosmos|Qwen|balanced accuracy/i);
    }
  });

  for (const id of ["B1", "B2"]) {
    test(`FR-020-27 · /cases/${id}/ lists its registry KPIs only and no Cosmos KPI`, async ({ page }) => {
      await open(page, `cases/${id}/?tab=charts`);
      const names = (await page.locator("main [data-kpi]").allTextContents()).join(" ");
      expect(names).not.toMatch(/Cosmos|Qwen/i);
      const kpis = await page
        .locator("main [data-kpi]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-kpi")));
      const allowed = new Set((registry.cases[id]?.kpis ?? []).map((k) => k.id));
      for (const k of kpis) expect(allowed.has(k ?? ""), `${k} is a KPI of ${id}`).toBe(true);
    });
  }
});
