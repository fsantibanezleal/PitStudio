// T-020-064 [red] · NFR-020-05 (axe reports 0 serious or critical findings on every top-level route in light and dark x EN and ES, on one instance of every dynamic template in the four combinations, and on every prerendered instance in
// light/EN), NFR-020-06 (Lighthouse on each top-level route, one theory page and one method page: accessibility >= 0.95, performance warns below 0.80), SC-020-01 (100 % of the prerendered routes meet both bars in both themes and both languages) and
// NFR-000-02. The Lighthouse configuration is `web/lighthouserc.site.json` (the other two sets live in lighthouserc.json for the case routes and lighthouserc.studio.json for the studio): its URLs are the six top-level routes, one theory page and one method page,
// and a package script `lhci:site` runs it in CI after the build.
//
// Routes: the six top-level routes (`/cases/`, `/studio/`, `/theory/`, `/methods/`, `/results/`, `/knowledge/` and `/`), the dynamic templates (a theory page, a method page and the tabs of /results and sections of /knowledge); every prerendered instance in
// light/EN (13 theory pages, 23 method pages, 7 results tabs, 6 knowledge sections).
// Oracles: WCAG 2.2 AA as tagged in axe-core 4.13; the thresholds of the NFR rows.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];
const THEORY = [
  "haulage",
  "loading-and-terramechanics",
  "drill-and-blast",
  "slopes-and-monitoring",
  "bulk-flow-dem-mpm",
  "comminution",
  "dust",
  "tailings",
  "planning",
  "rtx-sensor-physics",
  "robot-learning",
  "vision-language-reasoning",
  "sim-to-real",
];
const METHODS = Array.from({ length: 23 }, (_, i) => `m${String(i + 1).padStart(2, "0")}`);
const RESULTS_TABS = [
  "learned-vs-classical",
  "sim-to-real",
  "parity",
  "dr-ablation",
  "isaac-lab",
  "cosmos",
  "acceleration",
];
const SECTIONS = ["glossary", "equations", "parameters", "datasets", "frameworks", "bibliography"];
const TOP: Array<[string, string]> = [
  ["Explore", ""],
  ["Cases", "cases/"],
  ["Studio", "studio/"],
  ["Theory", "theory/"],
  ["Methods", "methods/"],
  ["Results", "results/"],
  ["Knowledge", "knowledge/"],
];
const TEMPLATES: Array<[string, string]> = [
  ["a theory page", "theory/tailings/"],
  ["a method page", "methods/m04/"],
  ["a results tab", "results/?tab=cosmos"],
  ["a knowledge section", "knowledge/?section=parameters"],
];

async function openThemed(page: Page, route: string, theme: "light" | "dark", lang: string): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  const sep = route.includes("?") ? "&" : "?";
  await open(page, `${route}${sep}lang=${lang}`);
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.locator("main h1"), "the page exists").not.toHaveText("Page not found");
  await page.waitForLoadState("networkidle");
}

async function blocking(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

test.describe("top-level routes in four combinations (NFR-020-05)", () => {
  for (const [name, route] of TOP) {
    for (const theme of ["light", "dark"] as const) {
      for (const lang of ["en", "es"]) {
        test(`NFR-020-05 · ${name} (/${route}) ${theme} ${lang}: no serious or critical axe finding`, async ({
          page,
        }) => {
          await openThemed(page, route, theme, lang);
          expect(await blocking(page)).toEqual([]);
        });
      }
    }
  }
});

test.describe("one instance of each dynamic template in four combinations (NFR-020-05)", () => {
  for (const [name, route] of TEMPLATES) {
    for (const theme of ["light", "dark"] as const) {
      for (const lang of ["en", "es"]) {
        test(`NFR-020-05 · ${name} (/${route}) ${theme} ${lang}: no serious or critical axe finding`, async ({
          page,
        }) => {
          await openThemed(page, route, theme, lang);
          expect(await blocking(page)).toEqual([]);
        });
      }
    }
  }
});

test.describe("every prerendered instance in light English (NFR-020-05, SC-020-01)", () => {
  const all: string[] = [
    ...THEORY.map((id) => `theory/${id}/`),
    ...METHODS.map((id) => `methods/${id}/`),
    ...RESULTS_TABS.map((t) => `results/?tab=${t}`),
    ...SECTIONS.map((s) => `knowledge/?section=${s}`),
  ];
  for (const route of all) {
    test(`NFR-020-05 · /${route} light en: no serious or critical axe finding`, async ({ page }) => {
      await openThemed(page, route, "light", "en");
      expect(await blocking(page)).toEqual([]);
    });
  }
});

test.describe("the interactive parts keep the bar (NFR-020-05)", () => {
  test("NFR-020-05 · a figure with its controls and a chart with its data table open: no serious or critical finding in dark Spanish", async ({
    page,
  }) => {
    await openThemed(page, "theory/robot-learning/", "dark", "es");
    await page
      .locator('[data-testid="figure"]')
      .first()
      .getByRole("button", { name: /Mostrar datos|Show data/i })
      .first()
      .click();
    expect(await blocking(page)).toEqual([]);
  });

  test("NFR-020-05 · the architecture modal open: no serious or critical finding in both themes", async ({
    page,
  }) => {
    for (const theme of ["light", "dark"] as const) {
      await openThemed(page, "", theme, "en");
      await page.getByRole("button", { name: /About this app/ }).click();
      expect(await blocking(page)).toEqual([]);
      await page.keyboard.press("Escape");
    }
  });
});

test.describe("Lighthouse configuration (NFR-020-06)", () => {
  const rc = () =>
    JSON.parse(readFileSync(resolve(WEB, "lighthouserc.site.json"), "utf8")) as {
      ci?: { collect?: { url?: string[] }; assert?: { assertions?: Record<string, unknown> } };
    };

  test("NFR-020-06 · web/lighthouserc.site.json collects the six top-level routes, one theory page and one method page", async () => {
    const base = process.env.BASE_PATH ?? "/";
    const urls = (rc().ci?.collect?.url ?? []).map((u) => new URL(u).pathname.slice(base.length - 1));
    for (const route of ["/cases/", "/studio/", "/theory/", "/methods/", "/results/", "/knowledge/"])
      expect(urls, route).toContain(route);
    expect(urls.filter((u) => /^\/theory\/[a-z-]+\/$/.test(u))).toHaveLength(1);
    expect(urls.filter((u) => /^\/methods\/m\d\d\/$/.test(u))).toHaveLength(1);
    expect(urls).toHaveLength(8);
  });

  test("NFR-020-06 · accessibility must reach 0.95 as an error, performance below 0.80 only warns", async () => {
    const a = rc().ci?.assert?.assertions ?? {};
    const acc = a["categories:accessibility"] as [string, { minScore: number }];
    const perf = a["categories:performance"] as [string, { minScore: number }];
    expect(acc[0]).toBe("error");
    expect(acc[1].minScore).toBeGreaterThanOrEqual(0.95);
    expect(perf[0]).toBe("warn");
    expect(perf[1].minScore).toBeGreaterThanOrEqual(0.8);
  });

  test("NFR-020-06 · a package script runs LHCI with that config and CI runs it after the build", async () => {
    const pkg = JSON.parse(readFileSync(resolve(WEB, "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    expect(pkg.scripts["lhci:site"]).toContain("lhci autorun");
    expect(pkg.scripts["lhci:site"]).toContain("lighthouserc.site.json");
    const ci = readFileSync(resolve(WEB, "../.github/workflows/ci.yml"), "utf8");
    expect(ci).toMatch(/lhci:site/);
    expect(ci.indexOf("pnpm run build")).toBeLessThan(ci.indexOf("lhci:site"));
  });
});
