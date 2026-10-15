// T-010-053 [red] · FR-010-38: the optional EGMS layer on the C1 Scene tab and its "Not run" state.
//
// What the green commit must deliver (route `cases/C1/?tab=scene`, layer `egms` of the C1 Scene tab, derived-only):
//   - a layer toggle named "EGMS deformation (Hambach)" in the layer list (`role="checkbox"` inside the group named "Layers");
//   - fixture WITH the EGMS summaries (`?fixture=egms`): toggling the layer on shows the label "derived-only (EGMS)" and the attribution
//     text of the EGMS summaries in an element `data-testid="egms-attribution"`; the layer holds summary values, never per-point
//     measurements (no more than 200 rendered items `data-testid="egms-summary-item"`);
//   - fixture WITHOUT (default, `?fixture=no-egms`): the layer shows "Not run — EGMS access not set up" and no value;
//   - no C1 KPI depends on the layer: the KPI table (`role="table"` named "Key figures") has the same cells with the layer on, off and
//     in either fixture.
// Oracles: the exact strings of FR-010-38; DOM comparison of the KPI table across the four states.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const NOT_RUN = "Not run — EGMS access not set up";
const LABEL = "derived-only (EGMS)";

async function kpiCells(page: Page): Promise<string[]> {
  return page.getByRole("table", { name: "Key figures" }).locator("td, th").allTextContents();
}

test.describe("C1 Scene tab: EGMS layer", () => {
  test("FR-010-38 · with EGMS summaries present the layer is labelled derived-only and carries its attribution", async ({
    page,
  }) => {
    await open(page, "cases/C1/?tab=scene&fixture=egms");
    const toggle = page
      .getByRole("group", { name: "Layers" })
      .getByRole("checkbox", { name: "EGMS deformation (Hambach)" });
    await toggle.check();
    await expect(page.getByText(LABEL, { exact: true })).toBeVisible();
    await expect(page.getByTestId("egms-attribution")).not.toBeEmpty();
    const items = await page.getByTestId("egms-summary-item").count();
    expect(items).toBeGreaterThan(0);
    expect(items).toBeLessThanOrEqual(200);
    await expect(page.getByText(NOT_RUN)).toHaveCount(0);
  });

  test("FR-010-38 · without EGMS access the layer says Not run and shows no value", async ({ page }) => {
    await open(page, "cases/C1/?tab=scene&fixture=no-egms");
    const toggle = page
      .getByRole("group", { name: "Layers" })
      .getByRole("checkbox", { name: "EGMS deformation (Hambach)" });
    await toggle.check();
    await expect(page.getByText(NOT_RUN, { exact: true })).toBeVisible();
    await expect(page.getByTestId("egms-summary-item")).toHaveCount(0);
    await expect(page.getByTestId("egms-attribution")).toHaveCount(0);
    await expect(page.getByText(LABEL, { exact: true })).toHaveCount(0);
  });

  test("FR-010-38 · no C1 key figure depends on the layer", async ({ page }) => {
    const states: string[][] = [];
    for (const fixture of ["egms", "no-egms"]) {
      await open(page, `cases/C1/?tab=scene&fixture=${fixture}`);
      await expect(page.getByRole("table", { name: "Key figures" })).toBeVisible();
      states.push(await kpiCells(page));
      await page
        .getByRole("group", { name: "Layers" })
        .getByRole("checkbox", { name: "EGMS deformation (Hambach)" })
        .check();
      states.push(await kpiCells(page));
    }
    expect(states[0]?.length).toBeGreaterThan(0);
    for (const s of states) expect(s).toEqual(states[0]);
  });

  test("FR-010-38 · the layer is optional: the Scene tab works with it off in both fixtures", async ({
    page,
  }) => {
    for (const fixture of ["egms", "no-egms"]) {
      await open(page, `cases/C1/?tab=scene&fixture=${fixture}`);
      await expect(page.getByRole("tabpanel")).toBeVisible();
      const toggle = page
        .getByRole("group", { name: "Layers" })
        .getByRole("checkbox", { name: "EGMS deformation (Hambach)" });
      await expect(toggle).not.toBeChecked();
    }
  });
});
