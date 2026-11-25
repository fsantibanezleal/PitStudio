// T-020-031 [red] · FR-020-20, FR-020-31 (E2E half) on the production build, route `/results/`.
// Contract the green commit must deliver (row and pending-item DOM: see web/src/results/t_020_031_rows.test.tsx):
//   - `main h1` "Results" and one `role="tablist"` with seven `role="tab"` named, in order,
//     "Learned vs classical", "Sim-to-real and sim-to-sim", "Parity", "DR ablation", "Isaac Lab vs baselines",
//     "Cosmos vs Qwen vs detector", "Acceleration"; WAI-ARIA selected state and roving tabindex as on the case pages
//     (web/e2e/t_018_030_case_pages.spec.ts); the selection is kept in `?tab=<id>` (ids of RESULTS_TAB_IDS), default the first tab;
//     selecting a tab sets `tab=` and keeps the other parameters without loading a new document.
//   - nothing is published yet, so every tab panel shows "Not yet run", the word "criterion" (the pre-registered acceptance criterion is
//     named), at least one `[data-pending]` item, and no `[data-comparison-row]` (no placeholder number).
// Oracles: FR-020-20 tab names and order; FR-020-31 text; the repository state (no results bundle committed).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const BASE = process.env.BASE_PATH ?? "/";
const TABS: ReadonlyArray<readonly [label: string, id: string]> = [
  ["Learned vs classical", "learned-vs-classical"],
  ["Sim-to-real and sim-to-sim", "sim-to-real"],
  ["Parity", "parity"],
  ["DR ablation", "dr-ablation"],
  ["Isaac Lab vs baselines", "isaac-lab"],
  ["Cosmos vs Qwen vs detector", "cosmos"],
  ["Acceleration", "acceleration"],
];

test.describe("/results tabs (FR-020-20)", () => {
  test("FR-020-20 · /results offers the seven tabs in order as a WAI-ARIA tab list, the first selected", async ({
    page,
  }) => {
    await open(page, "results/");
    await expect(page.locator("main h1")).toHaveText("Results");
    const tablist = page.getByRole("tablist");
    await expect(tablist).toHaveCount(1);
    const tabs = tablist.getByRole("tab");
    await expect(tabs).toHaveText(TABS.map(([label]) => label));
    for (let i = 0; i < TABS.length; i++) {
      await expect(tabs.nth(i)).toHaveAttribute("aria-selected", String(i === 0));
      await expect(tabs.nth(i)).toHaveAttribute("tabindex", i === 0 ? "0" : "-1");
      const panelId = await tabs.nth(i).getAttribute("aria-controls");
      expect(panelId).toBeTruthy();
      await expect(page.locator(`[id="${panelId}"]`)).toHaveAttribute("role", "tabpanel");
    }
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
  });

  test("FR-020-20 · selecting a tab keeps it in ?tab= together with the other parameters, without a new document", async ({
    page,
  }) => {
    await open(page, "results/?foo=bar");
    await page.evaluate(() => {
      (window as unknown as { __marker?: number }).__marker = 7;
    });
    const tabs = page.getByRole("tablist").getByRole("tab");
    for (const [i, [, id]] of TABS.entries()) {
      await tabs.nth(i).click();
      await expect(tabs.nth(i)).toHaveAttribute("aria-selected", "true");
      await expect(page).toHaveURL((url) => url.searchParams.get("tab") === id);
      const url = new URL(page.url());
      expect(url.pathname).toBe(`${BASE}results/`);
      expect(url.searchParams.get("foo")).toBe("bar");
      expect(await page.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(7);
    }
  });

  test("FR-020-20 · loading ?tab=<id> opens that tab", async ({ page }) => {
    for (const [i, [, id]] of TABS.entries()) {
      await open(page, `results/?tab=${id}`);
      await expect(page.getByRole("tablist").getByRole("tab").nth(i)).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await expect(page.getByRole("tabpanel")).toHaveCount(1);
    }
  });

  test("FR-020-20 · arrow keys, Home and End move between the tabs", async ({ page }) => {
    await open(page, "results/");
    const tabs = page.getByRole("tablist").getByRole("tab");
    await tabs.nth(0).focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await page.keyboard.press("End");
    await expect(tabs.nth(6)).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(0)).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(tabs.nth(6)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.nth(0)).toBeFocused();
  });

  test("FR-020-20 · an unknown or hostile ?tab= opens the first tab and raises no error", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const value of ["nope", "PARITY", "%3Cscript%3E", "__proto__", "a".repeat(3000), ""]) {
      await open(page, `results/?tab=${value}`);
      await expect(page.getByRole("tablist").getByRole("tab").nth(0)).toHaveAttribute(
        "aria-selected",
        "true",
      );
    }
    expect(errors).toEqual([]);
  });
});

test.describe("/results without published results (FR-020-31)", () => {
  test("FR-020-31 · every tab shows 'Not yet run' with its pre-registered criterion and no placeholder number", async ({
    page,
  }) => {
    for (const [, id] of TABS) {
      await open(page, `results/?tab=${id}`);
      const panel = page.getByRole("tabpanel");
      await expect(panel).toContainText("Not yet run");
      await expect(panel).toContainText(/criterion/i);
      expect(await panel.locator("[data-pending]").count(), id).toBeGreaterThan(0);
      await expect(panel.locator("[data-comparison-row]")).toHaveCount(0);
      await expect(panel).not.toContainText(/NaN|undefined|null/);
    }
  });
});
