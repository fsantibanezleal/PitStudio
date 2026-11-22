// T-018-095 [red] · FR-018-72: the Built with section is in the first viewport of a case page at both sizes, has its four groups,
// every chip shows its status, B2 lists Isaac Sim Replicator as planned in the Omniverse and NVIDIA group, and every visual frame
// of /cases/C1 carries a producer attribution. Test names contain "built with" (run with --grep "built with").
import { expect, test } from "@playwright/test";

const SIZES = [
  { name: "1440x900", width: 1440, height: 900 },
  { name: "390x844", width: 390, height: 844 },
];
const GROUPS = ["omniverse", "frameworks", "methods", "data"];

for (const size of SIZES) {
  for (const id of ["C1", "B2"]) {
    test(`built with: /cases/${id} shows the section in the first viewport at ${size.name}`, async ({ page }) => {
      await page.setViewportSize({ width: size.width, height: size.height });
      await page.goto(`/cases/${id}/`);
      const section = page.locator('[data-testid="built-with"]');
      await expect(section).toBeVisible();
      const box = await section.boundingBox();
      expect(box).not.toBeNull();
      expect(box?.y ?? Infinity).toBeLessThan(size.height);
      expect((box?.y ?? 0) + Math.min(box?.height ?? 0, 120)).toBeLessThanOrEqual(size.height);
      for (const g of GROUPS) await expect(section.locator(`[data-group="${g}"]`)).toBeVisible();
      const chips = section.locator("[data-chip]");
      expect(await chips.count()).toBeGreaterThan(3);
      for (const status of await chips.evaluateAll((els) => els.map((e) => e.getAttribute("data-status")))) {
        expect(["used", "planned"]).toContain(status);
      }
    });
  }
}

test("built with: /cases/B2 lists Isaac Sim Replicator in the Omniverse and NVIDIA group as planned, not yet run", async ({ page }) => {
  await page.goto("/cases/B2/");
  const chip = page.locator('[data-testid="built-with"] [data-group="omniverse"] [data-chip="isaac-sim-replicator"]');
  await expect(chip).toBeVisible();
  await expect(chip).toContainText(/planned, not yet run/i);
  await expect(chip.locator("a")).toHaveAttribute("href", /\/studio\/tools\/isaac-sim-replicator\/?$/);
});

test("built with: every visual frame of /cases/C1 carries its producer attribution", async ({ page }) => {
  for (const tab of ["scene", "simulate", "replay", "charts"]) {
    await page.goto(`/cases/C1/?tab=${tab}`);
    const frames = page.locator("[data-visual]");
    await expect(frames.first()).toBeVisible();
    for (const text of await frames.evaluateAll((els) => els.map((e) => e.querySelector("[data-producer]")?.textContent ?? ""))) {
      expect(text.trim().length).toBeGreaterThan(10);
    }
  }
});

test("built with: the catalogue shows the section per row in compact form", async ({ page }) => {
  await page.goto("/cases/");
  await expect(page.locator('[data-testid="built-with-compact"]').first()).toBeVisible();
  expect(await page.locator('[data-testid="built-with-compact"]').count()).toBe(12);
});
