// T-019-011 [red] · FR-019-03 (the React Flow chunk is requested only on /studio, after hydration, and belongs to no route's initial JavaScript), FR-019-04 (the prerendered HTML of
// /studio holds a static SVG of the graph and a data table, both usable with JavaScript disabled) and FR-019-39 (if the React Flow chunk fails to load, /studio keeps the static SVG
// and the table, shows "Interactive map unavailable" and raises no uncaught error). Unit half of the encodings: web/src/studio/t_019_010_tool_map.test.tsx.
//
// The React Flow chunk is recognised by its content, not by a file name the build may change: it is the JavaScript response whose body contains the class prefix `react-flow__`.
// Hooks: [data-testid="static-map"] (svg of the same graph) with a[data-testid="tool-node"][data-tool], table[data-testid="tool-table"] tr[data-tool],
// [data-testid="tool-map"][data-ready="true"] (the interactive map), [data-testid="map-unavailable"] with the text "Interactive map unavailable".
// Oracles: the EARS text; the 20 tool ids of spec section 7.1; the prerendered HTML as served (HTTP GET, no JavaScript).
import { expect, type Page, type Route, test } from "@playwright/test";
import { open } from "./helpers";

const BASE = process.env.BASE_PATH ?? "/";
const IDS = 20;
const FLOW = "react-flow__";
const ROUTES = [
  "",
  "cases/",
  "cases/A1/",
  "cases/E2/",
  "studio/tools/warp/",
  "studio/tools/cuopt/",
  "studio/runs/",
  "studio/gpu/",
  "theory/",
  "methods/",
  "results/",
  "knowledge/",
];

const scriptsOf = (html: string): string[] =>
  [...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)]
    .map((m) => m[1] as string)
    .filter((u) => u.startsWith(BASE));

async function failFlowChunk(
  page: Page,
  mode: "abort" | "http-500" | "script-error",
): Promise<{ hit: () => boolean }> {
  let hit = false;
  await page.route("**/*.js", async (route: Route) => {
    const res = await route.fetch();
    const body = await res.text();
    if (!body.includes(FLOW)) return route.fulfill({ response: res, body });
    hit = true;
    if (mode === "abort") return route.abort("failed");
    if (mode === "http-500") return route.fulfill({ status: 500, contentType: "text/plain", body: "boom" });
    return route.fulfill({
      status: 200,
      contentType: "text/javascript",
      body: "throw new Error('chunk failed to evaluate');",
    });
  });
  return { hit: () => hit };
}

test.describe("the React Flow chunk is lazy (FR-019-03)", () => {
  for (const route of ["studio/", ...ROUTES]) {
    test(`FR-019-03 · /${route}: no script of the prerendered HTML contains React Flow`, async ({
      request,
    }) => {
      const res = await request.get(route);
      expect(res.status()).toBe(200);
      const urls = scriptsOf(await res.text());
      expect(urls.length, "the page references scripts").toBeGreaterThan(0);
      for (const u of new Set(urls)) {
        const body = await (await request.get(u.slice(BASE.length))).text();
        expect(body.includes(FLOW), `${u} is part of the initial JavaScript of /${route}`).toBe(false);
      }
    });
  }

  test("FR-019-03 · /studio/ requests the React Flow chunk dynamically, once the page is up, and the other routes never do", async ({
    page,
  }) => {
    const flowUrls: string[] = [];
    page.on("response", async (r) => {
      if (/\.js(\?|$)/.test(r.url()) && (await r.text().catch(() => "")).includes(FLOW))
        flowUrls.push(r.url());
    });
    for (const route of ROUTES) {
      flowUrls.length = 0;
      await open(page, route);
      await page.waitForLoadState("networkidle");
      expect(flowUrls, `/${route}`).toEqual([]);
    }
    await open(page, "studio/");
    await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
    expect(flowUrls.length).toBeGreaterThan(0);
    const html = await (await page.request.get("studio/")).text();
    for (const u of flowUrls)
      expect(html, "the chunk is not referenced by the HTML").not.toContain(new URL(u).pathname);
  });

  test("FR-019-03 · while the chunk is still loading the static map and table are already visible", async ({
    page,
  }) => {
    await page.route("**/*.js", async (route) => {
      const res = await route.fetch();
      const body = await res.text();
      if (body.includes(FLOW)) await new Promise((r) => setTimeout(r, 3000));
      await route.fulfill({ response: res, body });
    });
    await open(page, "studio/");
    await expect(page.getByTestId("static-map")).toBeVisible();
    await expect(page.getByTestId("tool-table")).toBeVisible();
    await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  });
});

test.describe("no JavaScript (FR-019-04)", () => {
  test("FR-019-04 · the prerendered HTML of /studio/ has the static SVG with 20 tool nodes and the table with 20 rows", async ({
    request,
  }) => {
    const html = await (await request.get("studio/")).text();
    expect((html.match(/data-testid="tool-node"/g) ?? []).length).toBe(IDS);
    expect((html.match(/<tr[^>]*data-tool="/g) ?? []).length).toBe(IDS);
    expect(html).toContain('data-testid="static-map"');
    expect(html).toContain('data-testid="tool-table"');
    expect(html).toContain("Inbound handoffs");
    expect(html).toContain("Outbound handoffs");
    expect(html).toContain("Evaluated, not adopted");
  });

  test("FR-019-04 · with JavaScript disabled the map, the table and the links are visible and usable", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      javaScriptEnabled: false,
      baseURL: `http://localhost:${process.env.PORT ?? 4173}${BASE}`,
    });
    const page = await context.newPage();
    await page.goto("studio/");
    await expect(page.getByTestId("static-map")).toBeVisible();
    await expect(page.getByTestId("tool-table")).toBeVisible();
    await expect(page.getByTestId("tool-map")).toHaveCount(0);
    expect(await page.getByTestId("static-map").locator('[data-testid="tool-node"]').count()).toBe(IDS);
    expect(await page.locator('[data-testid="tool-table"] tbody tr').count()).toBe(IDS);
    await page.getByTestId("static-map").locator('a[data-tool="warp"]').click();
    await expect(page).toHaveURL(/\/studio\/tools\/warp\/?$/);
    await expect(page.locator("main h1")).toBeVisible();
    await context.close();
  });
});

test.describe("chunk failure (FR-019-39)", () => {
  for (const mode of ["abort", "http-500", "script-error"] as const) {
    test(`FR-019-39 · ${mode}: the static SVG and the table stay, 'Interactive map unavailable' is shown and nothing is thrown uncaught`, async ({
      page,
    }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      const probe = await failFlowChunk(page, mode);
      await open(page, "studio/");
      await expect(page.getByText("Interactive map unavailable")).toBeVisible({ timeout: 30_000 });
      expect(probe.hit()).toBe(true);
      await expect(page.getByTestId("static-map")).toBeVisible();
      await expect(page.getByTestId("tool-table")).toBeVisible();
      await expect(page.getByTestId("tool-map")).not.toHaveAttribute("data-ready", "true");
      expect(await page.getByTestId("static-map").locator('[data-testid="tool-node"]').count()).toBe(IDS);
      await page.getByTestId("static-map").locator('a[data-tool="warp"]').click();
      await expect(page).toHaveURL(/\/studio\/tools\/warp\/?$/);
      expect(errors).toEqual([]);
    });
  }
});
