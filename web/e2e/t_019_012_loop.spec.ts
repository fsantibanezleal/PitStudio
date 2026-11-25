// T-019-012 [red] · FR-019-07 (E2E half): below the map, /studio/ shows the physical-AI loop with its eight steps; with no published run every step says "Not yet run".
// Unit half (links to published runs): web/src/studio/t_019_012_loop.test.tsx. Hooks: ol[data-testid="loop"] with li[data-step]; the map is [data-testid="static-map"] or [data-testid="tool-map"].
// Oracle: the loop of spec section 3.1 (eight steps in order) and section 7.2.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const STEPS = ["scene", "sensors", "labels", "training", "validation", "acceleration", "encoding", "web"];

test("FR-019-07 · /studio/ lists the eight loop steps in order, all 'Not yet run' while nothing is published", async ({
  page,
}) => {
  await open(page, "studio/");
  const loop = page.getByTestId("loop");
  await expect(loop).toBeVisible();
  expect(
    await loop.locator("> li").evaluateAll((els) => els.map((e) => e.getAttribute("data-step"))),
  ).toEqual(STEPS);
  for (const step of STEPS)
    await expect(loop.locator(`li[data-step="${step}"]`)).toContainText("Not yet run");
  await expect(loop.locator("a")).toHaveCount(0);
});

test("FR-019-07 · the loop is below the map in the page", async ({ page }) => {
  await open(page, "studio/");
  const map = page.getByTestId("static-map").or(page.getByTestId("tool-map")).first();
  const loopBox = await page.getByTestId("loop").boundingBox();
  const mapBox = await map.boundingBox();
  expect(loopBox && mapBox && loopBox.y >= mapBox.y + mapBox.height - 1).toBe(true);
});

test("FR-019-07 · the loop is readable without JavaScript and in Spanish", async ({ page }) => {
  const html = await (await page.request.get("studio/")).text();
  expect(html).toContain('data-testid="loop"');
  expect((html.match(/data-step="/g) ?? []).length).toBe(8);
  await open(page, "studio/?lang=es");
  await expect(page.getByTestId("loop")).toBeVisible();
  await expect(page.getByTestId("loop").locator('li[data-step="scene"]')).not.toContainText("Scene");
});
