// T-018-011 [red] · FR-018-06 (tier badge), FR-018-31 (T1 -> T2 -> T0 fallback with notice) and FR-000-02 on the production build.
//
// Observation hooks (the unit-level API is in web/src/engines/tier/t_018_011_fallback.test.ts):
//   [data-testid="tier-badge"]            the badge (an <output>, role "status", accessible name "Compute tier" / "Nivel de cómputo");
//                                          `data-tier` = t1 | t2 | t0; text "T1 · WebGPU", "T2 · WebAssembly", "T0 · baked"
//                                          (ES: "T0 · precalculado")
//   [data-testid="tier-notice"]           one element per fallback notice, role "status" (non-modal), text names the failed runtime
// A scripted `navigator.gpu` is injected with web/e2e/support/gpu.ts. Oracles: FR-018-06 and FR-018-31 text; the locale files'
// existing badge strings.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { injectGpu } from "./support/gpu";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];

test.describe("tier badge (FR-018-06)", () => {
  test.use({ viewport: { width: 1280, height: 720 } });

  test("FR-018-06 · a working WebGPU device shows 'T1 · WebGPU' with an accessible name, visible without scrolling", async ({
    page,
  }) => {
    await injectGpu(page, "ok");
    await open(page, "");
    const badge = page.getByTestId("tier-badge");
    await expect(badge).toHaveAttribute("data-tier", "t1");
    await expect(badge).toHaveText("T1 · WebGPU");
    await expect(page.getByRole("status", { name: "Compute tier" })).toBeVisible();
    const box = await badge.boundingBox();
    expect(box).not.toBeNull();
    expect((box?.y ?? -1) >= 0).toBe(true);
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(720);
  });

  for (const script of ["none", "null-adapter", "device-rejects"] as const) {
    test(`FR-018-29 · GPU script '${script}' shows 'T2 · WebAssembly'`, async ({ page }) => {
      await injectGpu(page, script);
      await open(page, "");
      await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", "t2");
      await expect(page.getByTestId("tier-badge")).toHaveText("T2 · WebAssembly");
    });
  }

  test("FR-018-30 · ?tier=t0 forces 'T0 · baked' even with a working GPU, and ?tier=t1 cannot raise a lower tier", async ({
    page,
  }) => {
    await injectGpu(page, "ok");
    await open(page, "?tier=t0");
    await expect(page.getByTestId("tier-badge")).toHaveText("T0 · baked");
    await injectGpu(page, "none");
    await open(page, "?tier=t1");
    await expect(page.getByTestId("tier-badge")).toHaveText("T2 · WebAssembly");
  });

  test("FR-018-06 · the Spanish label is used in ES", async ({ page }) => {
    await injectGpu(page, "ok");
    await open(page, "?lang=es&tier=t0");
    await expect(page.getByTestId("tier-badge")).toHaveText("T0 · precalculado");
    await expect(page.getByRole("status", { name: "Nivel de cómputo" })).toBeVisible();
  });

  test("FR-018-06 · every case page shows the badge without scrolling at 1280 x 720", async ({ page }) => {
    await injectGpu(page, "none");
    for (const id of CASE_IDS) {
      await open(page, `cases/${id}/`);
      const badge = page.getByTestId("tier-badge");
      await expect(badge).toHaveText(/^T[012] · /);
      const name = await badge.getAttribute("aria-label");
      expect((name ?? "").length).toBeGreaterThan(0);
      const box = await badge.boundingBox();
      expect((box?.y ?? -1) >= 0 && (box?.y ?? 0) + (box?.height ?? 0) <= 720).toBe(true);
    }
  });
});

test.describe("fallback on device loss (FR-018-31, FR-000-02)", () => {
  test("FR-018-31 · a device lost after the grant moves the badge to T2 within 1 s and shows a non-modal notice naming WebGPU", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await injectGpu(page, { lostAfterMs: 1500 });
    await open(page, "cases/A3/?tab=simulate");
    const badge = page.getByTestId("tier-badge");
    await expect(badge).toHaveAttribute("data-tier", "t1");
    await expect(badge).toHaveAttribute("data-tier", "t2", { timeout: 4000 });
    await expect(badge).toHaveText("T2 · WebAssembly");
    const notice = page.getByTestId("tier-notice").first();
    await expect(notice).toContainText("WebGPU");
    await expect(notice).toHaveAttribute("role", "status");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.locator('[aria-modal="true"]')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test("FR-000-02 · the page stays interactive after the fallback: the tab list still takes keyboard input", async ({
    page,
  }) => {
    await injectGpu(page, { lostAfterMs: 500 });
    await open(page, "cases/A3/?tab=simulate");
    await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", "t2", { timeout: 4000 });
    const tabs = page.getByRole("tab");
    await tabs.first().focus();
    await page.keyboard.press("End");
    await expect(tabs.last()).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.first()).toBeFocused();
  });

  test("FR-018-31 · requestDevice rejecting at page load needs no notice: the page simply starts on T2 and raises no error", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await injectGpu(page, "device-rejects");
    await open(page, "cases/A3/?tab=simulate");
    await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", "t2");
    expect(errors).toEqual([]);
  });
});
