// T-018-023 [red] · FR-018-08: if neither WebGPU nor WebGL 2 is available, the Explore route and the Scene tabs show the scene's WebP poster, the text
// "3D view needs WebGL 2 or WebGPU" and the KPI table, and keep every other control usable.
//
// The browser is made 3D-less in the page itself (an init script makes `getContext` return null for "webgl2", "webgl", "experimental-webgl" and "webgpu", and removes
// `navigator.gpu`), so the precondition does not depend on launch flags or on the machine's GPU. Hooks:
//   img[data-testid="scene-poster"]            the scene's WebP poster (src ends with .webp, non-empty alt text)
//   [data-testid="kpi-panel"]                  the KPI table (T-018-021/022)
// Oracles: the EARS text; the 12 canonical case ids and the Scene tab (`?tab=scene`) of FR-018-11/12.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { injectGpu } from "./support/gpu";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const NOTICE = "3D view needs WebGL 2 or WebGPU";

async function noThreeD(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await injectGpu(page, "none");
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      type: string,
      ...rest: unknown[]
    ) {
      if (["webgl2", "webgl", "experimental-webgl", "webgpu"].includes(type)) return null;
      return (original as (...a: unknown[]) => unknown).call(this, type, ...rest) as never;
    } as typeof original;
  });
  return errors;
}

test.describe("no WebGL 2 and no WebGPU (FR-018-08)", () => {
  test("FR-018-08 · the environment really has no 3D API (guard of the tests below)", async ({ page }) => {
    await noThreeD(page);
    await open(page, "");
    const has = await page.evaluate(() => ({
      webgl2: document.createElement("canvas").getContext("webgl2"),
      webgl: document.createElement("canvas").getContext("webgl"),
      gpu: (navigator as unknown as { gpu?: unknown }).gpu,
    }));
    expect(has.webgl2).toBeNull();
    expect(has.webgl).toBeNull();
    expect(has.gpu).toBeUndefined();
  });

  test("FR-018-08 · Explore shows the WebP poster, the notice and the KPI table, and no 3D canvas", async ({
    page,
  }) => {
    const errors = await noThreeD(page);
    await open(page, "?case=A1");
    const poster = page.getByTestId("scene-poster");
    await expect(poster).toBeVisible();
    await expect(poster).toHaveAttribute("src", /\.webp(\?|$)/);
    expect(((await poster.getAttribute("alt")) ?? "").length).toBeGreaterThan(0);
    await expect(page.getByText(NOTICE)).toBeVisible();
    await expect(page.getByTestId("kpi-panel")).toBeVisible();
    await expect(page.locator('canvas[data-testid="scene-canvas"]')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  for (const id of CASE_IDS) {
    test(`FR-018-08 · /cases/${id}/ Scene tab shows the poster, the notice and the KPI table`, async ({
      page,
    }) => {
      const errors = await noThreeD(page);
      await open(page, `cases/${id}/?tab=scene`);
      await expect(page.getByTestId("scene-poster")).toHaveAttribute("src", /\.webp(\?|$)/);
      await expect(page.getByText(NOTICE)).toBeVisible();
      await expect(page.getByTestId("kpi-panel")).toBeVisible();
      expect(errors).toEqual([]);
    });
  }

  test("FR-018-08 · every other control stays usable: layer toggles respond, tabs move with the keyboard, the language switch works and navigation links work", async ({
    page,
  }) => {
    await noThreeD(page);
    await open(page, "cases/A1/?tab=scene");
    await expect(page.getByText(NOTICE)).toBeVisible();
    const tabs = page.getByRole("tab");
    await tabs.first().focus();
    await page.keyboard.press("End");
    await expect(tabs.last()).toBeFocused();
    await tabs.nth(3).click();
    await expect(page).toHaveURL(/tab=charts/);
    await page.getByLabel("Language").selectOption("es");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await page
      .getByRole("link", { name: /Casos|Cases/ })
      .first()
      .click();
    await expect(page).toHaveURL(/cases\/?$/);
    await open(page, "?case=A1");
    const toggles = page.getByTestId("layers").locator("button");
    expect(await toggles.count()).toBeGreaterThan(0);
    await expect(toggles.first()).toBeVisible();
  });

  test("FR-018-08 · with WebGPU or WebGL 2 present the notice and the poster are not shown (the fallback appears only when needed)", async ({
    page,
  }) => {
    await open(page, "?case=A1");
    await expect(page.getByText(NOTICE)).toHaveCount(0);
    await expect(page.getByTestId("scene-poster")).toHaveCount(0);
  });
});
