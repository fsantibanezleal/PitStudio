// T-018-037 [red] · NFR-018-04 (accessibility of `/`, `/cases` and the 12 case pages in light and dark, EN and ES: axe reports 0 serious or critical findings; the 3D
// canvas has a visible text summary and the KPI table as its alternative; Lighthouse accessibility >= 0.95 on `/`, `/cases` and `/cases/A1/`), NFR-000-02 (WCAG 2.2 AA in both
// themes and both languages) and FR-000-03 (theme and language).
//
// Lighthouse is run by LHCI in CI, not in this browser: the test fixes the CONFIGURATION that makes it run, as the oracle the EARS row names ("LHCI"):
//   web/lighthouserc.json   ci.collect.url = the three pages (`/`, `/cases/`, `/cases/A1/`, on the served base path), ci.assert.assertions["categories:accessibility"] =
//                           ["error", { "minScore": 0.95 }]; devDependency "@lhci/cli" and a package script "lhci" in web/package.json; a step `lhci autorun` in
//                           the web job of .github/workflows/ci.yml.
// Hooks for the canvas alternative: [data-testid="scene-canvas"] has aria-describedby pointing at [data-testid="scene-summary"] (visible text, at least 20 characters, in the
// active language); the KPI table [data-testid="kpi-panel"] is on the same page.
// Oracles: the EARS text, WCAG 2.2 AA as tagged in axe-core 4.13 (wcag2a, wcag2aa, wcag21aa, wcag22aa), the 14 routes of the row (`/`, `/cases`, the 12 canonical case ids).
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { routeTiles } from "./support/tiles";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const ROUTES = ["", "cases/", ...CASE_IDS.map((id) => `cases/${id}/`)];
const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];

async function openThemed(page: Page, route: string, theme: "light" | "dark", lang: string): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  const sep = route.includes("?") ? "&" : "?";
  await open(page, `${route}${sep}lang=${lang}`);
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect(page.locator("main h1")).toBeVisible();
}

async function blocking(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

test.describe("axe on every case route (NFR-018-04, NFR-000-02)", () => {
  test("NFR-018-04 · the route list of the row is the 14 pages: `/`, `/cases`, the 12 case pages", () => {
    expect(ROUTES).toHaveLength(14);
    expect(new Set(ROUTES).size).toBe(14);
  });

  for (const route of ROUTES) {
    for (const theme of ["light", "dark"] as const) {
      for (const lang of ["en", "es"]) {
        test(`NFR-018-04 · /${route} ${theme} ${lang}: no serious or critical axe finding`, async ({
          page,
        }) => {
          await openThemed(page, route, theme, lang);
          expect(await blocking(page)).toEqual([]);
        });
      }
    }
  }

  for (const id of CASE_IDS) {
    test(`NFR-018-04 · /cases/${id}/ every tab (scene, simulate, replay, charts) has no serious or critical finding in dark Spanish`, async ({
      page,
    }) => {
      for (const tab of ["scene", "simulate", "replay", "charts"]) {
        await openThemed(page, `cases/${id}/?tab=${tab}`, "dark", "es");
        expect(await blocking(page), tab).toEqual([]);
      }
    });
  }
});

test.describe("the canvas has a text alternative (NFR-018-04)", () => {
  const pages: Array<[string, string]> = [
    ["/ with a case", "?case=A1"],
    ...CASE_IDS.map((id): [string, string] => [`/cases/${id}/ scene`, `cases/${id}/?tab=scene`]),
  ];
  for (const [label, path] of pages) {
    test(`NFR-018-04 · ${label}: the 3D canvas is described by a visible text summary and the KPI table is on the page`, async ({
      page,
    }) => {
      await routeTiles(page);
      await open(page, path);
      const canvas = page.getByTestId("scene-canvas");
      await expect(canvas).toBeVisible({ timeout: 30_000 });
      const id = await canvas.getAttribute("aria-describedby");
      expect(id, "the canvas names its description").toBeTruthy();
      const summary = page.locator(`[id="${id}"]`);
      await expect(summary).toBeVisible();
      await expect(summary).toHaveAttribute("data-testid", "scene-summary");
      expect(((await summary.textContent()) ?? "").trim().length).toBeGreaterThanOrEqual(20);
      await expect(page.getByTestId("kpi-panel")).toBeVisible();
    });
  }

  test("NFR-018-04 · the summary follows the language", async ({ page }) => {
    await routeTiles(page);
    await open(page, "?case=A1&lang=en");
    const en = (await page.getByTestId("scene-summary").textContent()) ?? "";
    await open(page, "?case=A1&lang=es");
    const es = (await page.getByTestId("scene-summary").textContent()) ?? "";
    expect(en.length).toBeGreaterThan(0);
    expect(es.length).toBeGreaterThan(0);
    expect(es).not.toBe(en);
  });

  for (const theme of ["light", "dark"] as const) {
    test(`NFR-018-04 · / with the 3D canvas present (${theme}): no serious or critical axe finding`, async ({
      page,
    }) => {
      await routeTiles(page);
      await page.emulateMedia({ colorScheme: theme });
      await open(page, "?case=A1");
      await expect(page.getByTestId("scene-canvas")).toBeVisible({ timeout: 30_000 });
      expect(await blocking(page)).toEqual([]);
    });
  }
});

test.describe("Lighthouse accessibility configuration (NFR-018-04)", () => {
  const rc = () =>
    JSON.parse(readFileSync(resolve(WEB, "lighthouserc.json"), "utf8")) as {
      ci?: { collect?: { url?: string[] }; assert?: { assertions?: Record<string, unknown> } };
    };

  test("NFR-018-04 · web/lighthouserc.json collects `/`, `/cases/` and `/cases/A1/` on the served base path", () => {
    const urls = rc().ci?.collect?.url ?? [];
    expect(urls).toHaveLength(3);
    const base = process.env.BASE_PATH ?? "/";
    const paths = urls.map((u) => new URL(u).pathname);
    for (const p of paths) expect(p.startsWith(base) || base === "/").toBe(true);
    expect(paths.map((p) => p.slice(base.length - 1).replace(/^\/?/, "/"))).toEqual([
      "/",
      "/cases/",
      "/cases/A1/",
    ]);
  });

  test("NFR-018-04 · the accessibility score must be at least 0.95, as an error and not a warning", () => {
    const assertion = rc().ci?.assert?.assertions?.["categories:accessibility"] as [
      string,
      { minScore: number },
    ];
    expect(assertion[0]).toBe("error");
    expect(assertion[1].minScore).toBeGreaterThanOrEqual(0.95);
  });

  test("NFR-018-04 · LHCI is a pinned dev dependency with a script, and CI runs it after the build", () => {
    const pkg = JSON.parse(readFileSync(resolve(WEB, "package.json"), "utf8")) as {
      devDependencies: Record<string, string>;
      scripts: Record<string, string>;
    };
    expect(pkg.devDependencies["@lhci/cli"]).toMatch(/^[\^~]?\d+\.\d+\.\d+/);
    expect(pkg.scripts.lhci).toContain("lhci autorun");
    const ci = readFileSync(resolve(WEB, "../.github/workflows/ci.yml"), "utf8");
    expect(ci).toMatch(/run:\s*pnpm (exec )?(run )?lhci/);
    expect(ci.indexOf("pnpm run build")).toBeLessThan(ci.search(/pnpm (exec )?(run )?lhci/));
  });
});
