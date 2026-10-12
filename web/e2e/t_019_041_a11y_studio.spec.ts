// T-019-041 [red] · NFR-019-04 (axe reports 0 serious or critical findings on /studio, every tool page, /studio/runs, one run page and /studio/gpu: one instance of each template in light and dark x EN and ES, every instance in
// light/EN), NFR-019-05 (Lighthouse on /studio, /studio/gpu and one tool page: accessibility >= 0.95, performance warns below 0.80), NFR-000-02 and FR-000-03 (theme and language).
//
// Lighthouse runs in CI through LHCI; the test fixes the configuration that makes it run, as T-018-037 does for the case routes. The studio set has its own file so that the two sets of URLs stay separate:
//   web/lighthouserc.studio.json   ci.collect.url = `/studio/`, `/studio/gpu/` and `/studio/tools/warp/` on the served base path; ci.assert.assertions["categories:accessibility"] = ["error", { "minScore": 0.95 }] and
//                                  ["categories:performance"] = ["warn", { "minScore": 0.8 }]; a package script "lhci:studio" that runs `lhci autorun` with `--config=lighthouserc.studio.json`; a step running it in .github/workflows/ci.yml.
// The build under test holds the fixture runs of web/e2e/support/studio-runs.ts (templates: the run page of RUN_B).
// Oracles: WCAG 2.2 AA as tagged in axe-core 4.13 (wcag2a, wcag2aa, wcag21aa, wcag22aa); the thresholds of the NFR rows.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { RUN_A, RUN_B, RUN_BIG } from "./support/studio-runs";

const WEB = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];
const TOOLS = [
  "openusd",
  "warp",
  "newton",
  "mujoco-warp",
  "physx-ovphysx",
  "ovrtx",
  "isaac-sim-replicator",
  "isaac-lab",
  "kit-usd-composer-explorer",
  "cosmos-reason-2",
  "pytorch",
  "onnx-runtime",
  "tensorrt",
  "nvenc-ffmpeg",
  "nsight-nvml",
  "threejs-r3f-3d-tiles",
  "rapier-webgpu-pyodide",
  "cuopt",
  "physicsnemo",
  "cosmos-predict-transfer",
];
/** One instance of each template. */
const TEMPLATES: Array<[string, string]> = [
  ["the tool map", "studio/"],
  ["a tool page", "studio/tools/warp/"],
  ["the runs ledger", "studio/runs/"],
  ["a run page", `studio/runs/${RUN_B}/`],
  ["the GPU page", "studio/gpu/"],
];

async function openThemed(page: Page, route: string, theme: "light" | "dark", lang: string): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  await open(page, `${route}?lang=${lang}`);
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
  await expect(page.locator("main h1")).toBeVisible();
  await expect(page.locator("main h1"), "the page exists (not the not-found page)").not.toHaveText(
    "Page not found",
  );
  await page.waitForLoadState("networkidle");
}

async function blocking(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
}

test.describe("one instance of each template in four combinations (NFR-019-04)", () => {
  for (const [name, route] of TEMPLATES) {
    for (const theme of ["light", "dark"] as const) {
      for (const lang of ["en", "es"]) {
        test(`NFR-019-04 · ${name} (/${route}) ${theme} ${lang}: no serious or critical axe finding`, async ({
          page,
        }) => {
          await openThemed(page, route, theme, lang);
          expect(await blocking(page)).toEqual([]);
        });
      }
    }
  }
});

test.describe("every instance in light English (NFR-019-04)", () => {
  for (const id of TOOLS) {
    test(`NFR-019-04 · /studio/tools/${id}/ light en: no serious or critical axe finding`, async ({
      page,
    }) => {
      await openThemed(page, `studio/tools/${id}/`, "light", "en");
      expect(await blocking(page)).toEqual([]);
    });
  }

  for (const id of [RUN_A, RUN_B, RUN_BIG]) {
    test(`NFR-019-04 · /studio/runs/${id}/ light en: no serious or critical axe finding`, async ({
      page,
    }) => {
      await openThemed(page, `studio/runs/${id}/`, "light", "en");
      expect(await blocking(page)).toEqual([]);
    });
  }
});

test.describe("interactive parts keep the bar (NFR-019-04)", () => {
  test("NFR-019-04 · with the 'How measured' popover open and the manifest tree expanded, axe still finds nothing serious", async ({
    page,
  }) => {
    await openThemed(page, "studio/gpu/", "dark", "es");
    await page.getByTestId("how-measured").first().click();
    expect(await blocking(page)).toEqual([]);
    await page.keyboard.press("Escape");
    await openThemed(page, `studio/runs/${RUN_A}/`, "dark", "en");
    await page.getByTestId("manifest-tree").locator('[data-path="/stages"]').focus();
    await page.keyboard.press("*");
    expect(await blocking(page)).toEqual([]);
  });

  test("NFR-019-04 · the tool map nodes and the connect control are reachable by keyboard and have accessible names", async ({
    page,
  }) => {
    await openThemed(page, "studio/", "light", "en");
    await expect(page.getByTestId("connect-port")).toHaveAccessibleName(/\S/);
    await expect(page.getByTestId("connect-button")).toHaveAccessibleName(/\S/);
    await page.getByTestId("tool-map").waitFor({ state: "attached" });
    const names = await page
      .locator('[data-testid="tool-node"]')
      .evaluateAll((els) => els.map((e) => e.getAttribute("aria-label") ?? ""));
    for (const n of names) expect(n.length).toBeGreaterThan(10);
  });
});

test.describe("Lighthouse configuration (NFR-019-05)", () => {
  const rc = () =>
    JSON.parse(readFileSync(resolve(WEB, "lighthouserc.studio.json"), "utf8")) as {
      ci?: { collect?: { url?: string[] }; assert?: { assertions?: Record<string, unknown> } };
    };

  test("NFR-019-05 · web/lighthouserc.studio.json collects /studio/, /studio/gpu/ and one tool page on the served base path", () => {
    const urls = rc().ci?.collect?.url ?? [];
    expect(urls).toHaveLength(3);
    const base = process.env.BASE_PATH ?? "/";
    const paths = urls.map((u) => new URL(u).pathname.slice(base.length - 1));
    expect(paths.slice(0, 2)).toEqual(["/studio/", "/studio/gpu/"]);
    expect(paths[2]).toMatch(/^\/studio\/tools\/[a-z0-9-]+\/$/);
  });

  test("NFR-019-05 · accessibility must reach 0.95 as an error, performance below 0.80 only warns", () => {
    const a = rc().ci?.assert?.assertions ?? {};
    const acc = a["categories:accessibility"] as [string, { minScore: number }];
    const perf = a["categories:performance"] as [string, { minScore: number }];
    expect(acc[0]).toBe("error");
    expect(acc[1].minScore).toBeGreaterThanOrEqual(0.95);
    expect(perf[0]).toBe("warn");
    expect(perf[1].minScore).toBeGreaterThanOrEqual(0.8);
  });

  test("NFR-019-05 · a package script runs LHCI with that config and CI runs it after the build", () => {
    const pkg = JSON.parse(readFileSync(resolve(WEB, "package.json"), "utf8")) as {
      scripts: Record<string, string>;
    };
    expect(pkg.scripts["lhci:studio"]).toContain("lhci autorun");
    expect(pkg.scripts["lhci:studio"]).toContain("lighthouserc.studio.json");
    const ci = readFileSync(resolve(WEB, "../.github/workflows/ci.yml"), "utf8");
    expect(ci).toMatch(/lhci:studio/);
    expect(ci.indexOf("pnpm run build")).toBeLessThan(ci.indexOf("lhci:studio"));
  });
});
