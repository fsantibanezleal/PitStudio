// T-020-088 [red] · SC-020-02 (every model row of plan section 7 has its criterion and a computed status on /results: 13 of 13 rows present) and FR-020-24 on the release build. Unit half: web/src/results/t_020_032_criteria.test.ts.
//
// Hooks: [data-testid="criteria"] on /results/ (on every tab) with one [data-model-row="<id>"] per model row, holding [data-testid="criterion"] (the pre-registered criterion text of the registry) and [data-testid="status"]
// (`data-status` "pass" | "fail" | "not-yet-run" and the text "pass", "fail" or "Not yet run"). The build under test holds the published results bundles of web/e2e/fixtures/results/ (RESULTS_DIR contract of T-020-034): the Cosmos bundle records
// SC-015-01 as pass and SC-015-03 as fail, the comparison bundle SC-007-01 as pass, the acceleration bundle SC-016-01 as pass.
// Oracles: the 13 model rows of plan section 7 in their order (dfine, rfdetr-seg, unet, gns, fno, dispatch, il1, il2, slope-forecasters, meta-model, dem-calibration, cosmos, tensorrt-engines), the rule of FR-020-24 (fail beats pass beats not yet run;
// a requirement that no bundle records keeps the row "Not yet run"), the recorded statuses of the fixtures above.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const ROWS = [
  "dfine",
  "rfdetr-seg",
  "unet",
  "gns",
  "fno",
  "dispatch",
  "il1",
  "il2",
  "slope-forecasters",
  "meta-model",
  "dem-calibration",
  "cosmos",
  "tensorrt-engines",
];
const TABS = [
  "learned-vs-classical",
  "sim-to-real",
  "parity",
  "dr-ablation",
  "isaac-lab",
  "cosmos",
  "acceleration",
];

test.describe("13 of 13 model rows (SC-020-02)", () => {
  test("SC-020-02 · /results/ lists the 13 model rows in the order of plan section 7", async ({ page }) => {
    await open(page, "results/");
    const rows = page.locator('[data-testid="criteria"] [data-model-row]');
    expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-model-row")))).toEqual(ROWS);
  });

  for (const id of ROWS) {
    test(`SC-020-02 · ${id}: a criterion text and a status (pass, fail or Not yet run)`, async ({ page }) => {
      await open(page, "results/");
      const row = page.locator(`[data-testid="criteria"] [data-model-row="${id}"]`);
      await expect(row).toBeVisible();
      expect(((await row.getByTestId("criterion").textContent()) ?? "").trim().length).toBeGreaterThan(15);
      const status = row.getByTestId("status");
      await expect(status).toHaveAttribute("data-status", /^(pass|fail|not-yet-run)$/);
      await expect(status).toContainText(/^(pass|fail|Not yet run)$/);
    });
  }

  test("SC-020-02 · the criteria are on every tab of /results, not only the first", async ({ page }) => {
    for (const tab of TABS) {
      await open(page, `results/?tab=${tab}`);
      await expect(page.locator('[data-testid="criteria"] [data-model-row]'), tab).toHaveCount(13);
    }
  });
});

test.describe("computed statuses (FR-020-24)", () => {
  test("FR-020-24 · the Cosmos row is 'fail' because SC-015-03 is recorded as fail in the published bundle", async ({
    page,
  }) => {
    await open(page, "results/");
    const status = page.locator('[data-model-row="cosmos"] [data-testid="status"]');
    await expect(status).toHaveAttribute("data-status", "fail");
    await expect(status).toHaveText("fail");
  });

  test("FR-020-24 · a model with no published result reads 'Not yet run', never pass: the detector rows have no bundle", async ({
    page,
  }) => {
    await open(page, "results/");
    for (const id of ["dfine", "rfdetr-seg", "fno", "il2"])
      await expect(page.locator(`[data-model-row="${id}"] [data-testid="status"]`), id).toHaveAttribute(
        "data-status",
        "not-yet-run",
      );
  });

  test("FR-020-24 · a row that has only some of its criteria recorded is not a pass: the dispatch row (SC-007-01 recorded as pass, SC-007-02 not) reads 'Not yet run'", async ({
    page,
  }) => {
    await open(page, "results/");
    await expect(page.locator('[data-model-row="dispatch"] [data-testid="status"]')).toHaveAttribute(
      "data-status",
      "not-yet-run",
    );
  });

  test("FR-020-24 · the criterion text follows the language: Spanish differs from English for the dispatch row", async ({
    page,
  }) => {
    await open(page, "results/?lang=en");
    const en = await page.locator('[data-model-row="dispatch"] [data-testid="criterion"]').innerText();
    await open(page, "results/?lang=es");
    const es = await page.locator('[data-model-row="dispatch"] [data-testid="criterion"]').innerText();
    expect(es).not.toBe(en);
    expect(es.length).toBeGreaterThan(15);
  });
});
