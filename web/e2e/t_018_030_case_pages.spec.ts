// T-018-030 [red] · FR-018-11, FR-018-12, FR-018-13: the 12 prerendered case pages, the five WAI-ARIA sub-tabs, `?tab=`, 404.
//
// What the green commit must deliver (route module `cases/:id`, prerender list generated from the case registry):
//   - `<base>cases/<ID>/` for each of the 12 canonical ids is a prerendered file of the build (build/client/cases/<ID>/index.html or
//     <ID>.html) answering 200; the build holds no other id (so upper case only; a case-sensitive host such as Pages answers 404 for the rest).
//   - the page has `main h1` containing the case id and its registry title (EN) and a single `role="tablist"` with five `role="tab"`
//     named Scene, Simulate (live), Studio replay, Charts, Context (in this order). Selected tab: aria-selected="true", tabindex 0;
//     the others aria-selected="false", tabindex -1 (roving tabindex); each tab has aria-controls naming its `role="tabpanel"`, whose
//     aria-labelledby names the tab; only the selected panel is exposed. Default (no ?tab=) is Scene.
//   - keyboard (WAI-ARIA tabs pattern): ArrowRight / ArrowLeft move focus to the next / previous tab (wrapping), Home / End to the first /
//     last; Enter or Space (or the arrow itself, for automatic activation) selects the focused tab.
//   - selecting a tab sets `tab=<scene|simulate|replay|charts|context>` in the URL keeping every other query parameter, without loading a
//     new document; loading `?tab=<value>` opens that tab.
//   - an id that is not one of the 12 canonical upper-case ids (any other string, a lower-case spelling) gives the app's not-found page
//     (`h1` "Page not found"; HTTP 404 from the static host) and no request for a case asset (any URL under `<base>assets/` other than the
//     build's own .js / .css / font files).
// Oracles: FR-018-11/12/13 text; 12 ids and titles from the valid case registry example; WAI-ARIA Authoring Practices tabs pattern.
import { readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";
import { CASE_IDS, CASE_TABS, loadCaseRegistry } from "../src/test-support/fixtures";
import { open } from "./helpers";

const registry = loadCaseRegistry();
const BASE = process.env.BASE_PATH ?? "/";
const BUILT_CASES = fileURLToPath(new URL("../build/client/cases", import.meta.url));

function caseAssetRequests(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (req) => {
    const path = new URL(req.url()).pathname;
    if (!path.startsWith(`${BASE}assets/`)) return;
    if (/\.(js|mjs|css|woff2?|map)$/.test(path)) return;
    seen.push(path);
  });
  return seen;
}

test.describe("prerendered pages (FR-018-11)", () => {
  test("FR-018-11 · the build holds exactly the 12 canonical case pages", () => {
    const names = readdirSync(BUILT_CASES)
      .filter((n) => statSync(`${BUILT_CASES}/${n}`).isDirectory() || n.endsWith(".html"))
      .map((n) => n.replace(/\.html$/, ""))
      .filter((n) => n !== "index")
      .sort();
    expect(names).toEqual([...CASE_IDS].sort());
  });

  for (const id of CASE_IDS) {
    test(`FR-018-11 · /cases/${id}/ is a prerendered page answering 200`, async ({ request }) => {
      const res = await request.get(`cases/${id}/`);
      expect(res.status()).toBe(200);
      expect(res.headers()["content-type"]).toContain("text/html");
      expect(await res.text()).toContain("<title>");
    });
  }

  test("FR-018-11 · every case page shows its title and the five sub-tabs in order", async ({ page }) => {
    for (const id of CASE_IDS) {
      await open(page, `cases/${id}/`);
      const h1 = page.locator("main h1");
      await expect(h1).toContainText(id);
      await expect(h1).toContainText(registry.cases[id]?.title.en as string);
      const tablist = page.getByRole("tablist");
      await expect(tablist).toHaveCount(1);
      await expect(tablist.getByRole("tab")).toHaveText(CASE_TABS.map(([label]) => label));
    }
  });

  test("FR-018-11 · the tab list follows WAI-ARIA: selected state, roving tabindex, tab to panel wiring", async ({
    page,
  }) => {
    await open(page, "cases/A1/");
    const tabs = page.getByRole("tablist").getByRole("tab");
    await expect(tabs).toHaveCount(5);
    for (let i = 0; i < 5; i++) {
      const tab = tabs.nth(i);
      const selected = i === 0;
      await expect(tab).toHaveAttribute("aria-selected", String(selected));
      await expect(tab).toHaveAttribute("tabindex", selected ? "0" : "-1");
      const panelId = await tab.getAttribute("aria-controls");
      expect(panelId).toBeTruthy();
      const tabId = await tab.getAttribute("id");
      expect(tabId).toBeTruthy();
      const panel = page.locator(`[id="${panelId}"]`);
      await expect(panel).toHaveAttribute("role", "tabpanel");
      await expect(panel).toHaveAttribute("aria-labelledby", tabId as string);
    }
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
    await expect(page.getByRole("tabpanel")).toBeVisible();
  });

  test("FR-018-11 · arrow keys, Home and End move between the tabs and wrap around", async ({ page }) => {
    await open(page, "cases/A1/");
    const tabs = page.getByRole("tablist").getByRole("tab");
    await tabs.nth(0).focus();
    await expect(tabs.nth(0)).toBeFocused();

    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(2)).toBeFocused();
    await page.keyboard.press("End");
    await expect(tabs.nth(4)).toBeFocused();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(0)).toBeFocused();
    await page.keyboard.press("ArrowLeft");
    await expect(tabs.nth(4)).toBeFocused();
    await page.keyboard.press("Home");
    await expect(tabs.nth(0)).toBeFocused();

    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Enter");
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(tabs.nth(0)).toHaveAttribute("aria-selected", "false");
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
  });
});

test.describe("?tab= (FR-018-12)", () => {
  test("FR-018-12 · selecting a sub-tab sets tab= in the URL, keeps the other parameters and does not load a new document", async ({
    page,
  }) => {
    await open(page, "cases/A1/?lang=en&t=3&foo=bar");
    await page.evaluate(() => {
      (window as unknown as { __marker?: number }).__marker = 42;
    });
    const tabs = page.getByRole("tablist").getByRole("tab");
    for (const [i, [label, param]] of CASE_TABS.entries()) {
      await tabs.nth(i).click();
      await expect(tabs.nth(i)).toHaveAttribute("aria-selected", "true");
      await expect(page).toHaveURL((url) => url.searchParams.get("tab") === param);
      const url = new URL(page.url());
      expect(url.pathname).toBe(`${BASE}cases/A1/`);
      expect(url.searchParams.get("t")).toBe("3");
      expect(url.searchParams.get("foo")).toBe("bar");
      expect(url.searchParams.get("lang")).toBe("en");
      await expect(tabs.nth(i)).toHaveText(label);
      const marker = await page.evaluate(() => (window as unknown as { __marker?: number }).__marker);
      expect(marker, `document reloaded when selecting ${label}`).toBe(42);
    }
  });

  test("FR-018-12 · loading ?tab=<value> opens that sub-tab", async ({ page }) => {
    for (const [i, [, param]] of CASE_TABS.entries()) {
      await open(page, `cases/C1/?tab=${param}`);
      const tabs = page.getByRole("tablist").getByRole("tab");
      await expect(tabs.nth(i)).toHaveAttribute("aria-selected", "true");
      await expect(page.getByRole("tabpanel")).toHaveCount(1);
      for (let j = 0; j < 5; j++) {
        if (j !== i) await expect(tabs.nth(j)).toHaveAttribute("aria-selected", "false");
      }
    }
  });

  test("FR-018-12 · without ?tab= the Scene tab is open", async ({ page }) => {
    await open(page, "cases/B1/");
    await expect(page.getByRole("tablist").getByRole("tab").nth(0)).toHaveAttribute("aria-selected", "true");
  });
});

test.describe("unknown ids (FR-018-13, hostile)", () => {
  for (const bad of ["Z9", "A4", "AA", "A1x", "A", "0", "%E2%80%A6", "A1-2"]) {
    test(`FR-018-13 · /cases/${bad}/ answers 404 with the app's not-found page and requests no case asset`, async ({
      page,
    }) => {
      const assets = caseAssetRequests(page);
      const res = await page.goto(`cases/${bad}/`);
      expect(res?.status()).toBe(404);
      await open(page, `cases/${bad}/`);
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
      await expect(page.getByRole("tablist")).toHaveCount(0);
      await page.waitForLoadState("networkidle");
      expect(assets).toEqual([]);
    });
  }

  test("FR-018-13 · a lower-case id is not a case: the not-found page is shown and no case asset is requested", async ({
    page,
  }) => {
    const assets = caseAssetRequests(page);
    await open(page, "cases/a1/");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await page.waitForLoadState("networkidle");
    expect(assets).toEqual([]);
  });

  test("FR-018-13 · the canonical ids still work after a not-found visit", async ({ page }) => {
    await open(page, "cases/Z9/");
    await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
    await open(page, "cases/E2/");
    await expect(page.locator("main h1")).toContainText(registry.cases.E2?.title.en as string);
  });
});
