// T-020-063 [red] · NFR-020-02 (the first view of every top-level route other than `/` and of one instance of each dynamic template transfers at most 2,000,000 encoded bytes before interaction), NFR-020-07 (a figure is interactive within 1 s
// of entering the viewport on CI Chromium; the frame time while zooming has p95 <= 16.7 ms on the reference desktop, REPORTED with a warning in CI, so the test records it and fails only when it cannot be measured) and NFR-000-03.
//
// Encoded bytes are summed through the Chrome DevTools Protocol (`Network.loadingFinished.encodedDataLength` of every request, headers included in `Network.dataReceived`-independent form) from the navigation until the network has been idle for 2 s.
// Hooks: figures carry `data-first-render-ms` (milliseconds from the moment the figure entered the viewport to its first interactive render: the chart drawn and its controls enabled); the chart sandbox `/charts/` of T-020-010 gives a chart to zoom;
// frame times are the deltas of requestAnimationFrame callbacks while a wheel zoom runs. The build under test holds the fixture runs of web/e2e/support/studio-runs.ts.
// Oracles: the thresholds of the NFR rows (2,000,000 bytes; 1 s; 16.7 ms), CDP byte counts.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { RUN_A } from "./support/studio-runs";

const TOP = ["cases/", "studio/", "theory/", "methods/", "results/", "knowledge/"];
const TEMPLATES = [
  "cases/A1/",
  "cases/C2/?tab=simulate",
  "studio/tools/warp/",
  `studio/runs/${RUN_A}/`,
  "studio/gpu/",
  "theory/haulage/",
  "theory/tailings/",
  "methods/m04/",
  "results/?tab=acceleration",
  "knowledge/?section=parameters",
];

async function firstViewBytes(page: Page, path: string): Promise<number> {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  let total = 0;
  let lastActivity = Date.now();
  cdp.on("Network.loadingFinished", (e: { encodedDataLength: number }) => {
    total += e.encodedDataLength;
    lastActivity = Date.now();
  });
  cdp.on("Network.requestWillBeSent", () => {
    lastActivity = Date.now();
  });
  await open(page, path);
  const deadline = Date.now() + 60_000;
  while (Date.now() - lastActivity < 2000 && Date.now() < deadline) await page.waitForTimeout(250);
  while (Date.now() - lastActivity < 2000 && Date.now() < deadline) await page.waitForTimeout(250);
  await cdp.detach();
  return total;
}

test.describe("first view of every route (NFR-020-02)", () => {
  for (const route of [...TOP, ...TEMPLATES]) {
    test(`NFR-020-02 · /${route}: at most 2,000,000 encoded bytes before interaction`, async ({ page }) => {
      test.setTimeout(120_000);
      const bytes = await firstViewBytes(page, route);
      expect(bytes, "the page transferred something").toBeGreaterThan(1000);
      expect(bytes).toBeLessThanOrEqual(2_000_000);
      await expect(page.locator("main h1")).not.toHaveText("Page not found");
    });
  }

  test("NFR-020-02 · the routes of the list exist (guard): every one answers 200", async ({ request }) => {
    for (const route of [...TOP, ...TEMPLATES])
      expect((await request.get(route.split("?")[0] ?? route)).status(), route).toBe(200);
  });
});

test.describe("figures render fast (NFR-020-07)", () => {
  for (const [topic, id] of [
    ["robot-learning", "ppo-clip"],
    ["tailings", "ritter-dam-break"],
    ["bulk-flow-dem-mpm", "beverloo-discharge"],
    ["slopes-and-monitoring", "inverse-velocity"],
    ["dust", "plume-ground-field"],
  ] as Array<[string, string]>) {
    test(`NFR-020-07 · ${id} is interactive within 1 s of entering the viewport`, async ({ page }) => {
      await open(page, `theory/${topic}/`);
      const fig = page.locator(`[data-testid="figure"][data-figure="${id}"]`);
      await fig.scrollIntoViewIfNeeded();
      await expect(fig).toHaveAttribute("data-first-render-ms", /^\d+(\.\d+)?$/, { timeout: 5000 });
      const ms = Number(await fig.getAttribute("data-first-render-ms"));
      expect(ms).toBeLessThanOrEqual(1000);
      await expect(fig.locator("[data-control]").first()).toBeEnabled();
      await expect(fig.locator('[data-testid="chart"]').first()).toBeVisible();
    });
  }
});

test.describe("zoom frame time (NFR-020-07)", () => {
  test("NFR-020-07 · the frame times of a wheel zoom on a chart are measured and reported (p95 against 16.7 ms is a CI warning)", async ({
    page,
  }, testInfo) => {
    await open(page, "charts/");
    const chart = page.locator('[data-testid="chart"][data-chart-id="sine"]');
    await expect(chart).toBeVisible();
    const box = await chart.getByTestId("chart-plot").boundingBox();
    if (!box) throw new Error("no plot area");
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    const frames = page.evaluate(
      () =>
        new Promise<number[]>((resolve) => {
          const deltas: number[] = [];
          let last = performance.now();
          const tick = (now: number) => {
            deltas.push(now - last);
            last = now;
            if (deltas.length < 90) requestAnimationFrame(tick);
            else resolve(deltas);
          };
          requestAnimationFrame(tick);
        }),
    );
    for (let i = 0; i < 30; i++) {
      await page.mouse.wheel(0, i % 2 === 0 ? -120 : 120);
      await page.waitForTimeout(16);
    }
    const deltas = (await frames).slice(5).sort((a, b) => a - b);
    expect(deltas.length).toBeGreaterThanOrEqual(30);
    const p95 = deltas[Math.min(deltas.length - 1, Math.ceil(0.95 * deltas.length) - 1)] as number;
    testInfo.annotations.push({ type: "frame-time-p95-ms", description: p95.toFixed(1) });
    if (p95 > 16.7)
      console.warn(`NFR-020-07 warning: zoom frame time p95 ${p95.toFixed(1)} ms is above 16.7 ms`);
    expect(Number.isFinite(p95)).toBe(true);
  });
});
