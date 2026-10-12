// T-018-015 [red] · FR-018-36: the TypeScript engines run in module workers, so that during any engine run the main thread
// records no long task above 100 ms (PerformanceObserver type "longtask").
//
// Hooks: web/e2e/support/simulate.ts (engine panels with data-state / data-requests, numeric controls with data-min / data-max).
// Oracle: the EARS bound (100 ms) and the long-task definition of the Long Tasks API (a task of 50 ms or more; entries over
// 100 ms are the violations). Cases and engines: spec 018 section 7.1 (TypeScript-worker engines only).
import { expect, type Page, test } from "@playwright/test";
import { enginePanel, openSimulate } from "./support/simulate";

/** Engines that run in a TypeScript worker (section 7.1 runtime column) and the case that shows them. */
const TS_ENGINES: Array<[caseId: string, engines: string[]]> = [
  ["A1", ["des", "haulage", "lp"]],
  ["A2", ["haulage", "routing"]],
  ["B1", ["dust-lidar"]],
  ["C1", ["geotech"]],
  ["C3", ["plume", "dust-lidar"]],
  ["D1", ["blasting", "watershed"]],
  ["D2", ["comminution"]],
  ["E1", ["routing", "mincut"]],
  ["E2", ["volume"]],
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const w = window as unknown as { __longtasks: Array<{ start: number; duration: number }> };
    w.__longtasks = [];
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) w.__longtasks.push({ start: e.startTime, duration: e.duration });
    }).observe({ type: "longtask", buffered: true });
  });
});

async function runEngine(page: Page, engine: string): Promise<{ requests: number }> {
  const panel = enginePanel(page, engine);
  await expect(panel).toBeVisible();
  const controls = panel.locator("input[data-control]");
  const n = await controls.count();
  expect(n, `engine ${engine} has at least one numeric control`).toBeGreaterThan(0);
  const before = Number((await panel.getAttribute("data-requests")) ?? "0");
  const input = controls.first();
  const min = Number(await input.getAttribute("data-min"));
  const max = Number(await input.getAttribute("data-max"));
  await input.fill(String((min + max) / 2));
  await input.press("Enter");
  await expect
    .poll(async () => Number(await panel.getAttribute("data-requests")), { timeout: 30_000 })
    .toBeGreaterThan(before);
  await expect.poll(() => panel.getAttribute("data-state"), { timeout: 30_000 }).toMatch(/done|replay/);
  return { requests: Number(await panel.getAttribute("data-requests")) };
}

for (const [caseId, engines] of TS_ENGINES) {
  test(`FR-018-36 · ${caseId}: running ${engines.join(", ")} leaves no main-thread long task above 100 ms`, async ({
    page,
  }) => {
    await openSimulate(page, caseId, "&tier=t2");
    await page.waitForLoadState("networkidle");
    const t0 = await page.evaluate(() => performance.now());
    for (const engine of engines) await runEngine(page, engine);
    await page.waitForTimeout(300);
    const tasks = await page.evaluate(
      () => (window as unknown as { __longtasks: Array<{ start: number; duration: number }> }).__longtasks,
    );
    const during = tasks.filter((t) => t.start >= t0 && t.duration > 100);
    expect(during, `long tasks during the engine runs: ${JSON.stringify(during)}`).toEqual([]);
  });
}

test("FR-018-36 · the TypeScript engines run in module workers, not on the main thread", async ({ page }) => {
  await openSimulate(page, "C1", "&tier=t2");
  await runEngine(page, "geotech");
  const workers = page.workers();
  expect(workers.length).toBeGreaterThanOrEqual(1);
  const kinds = await Promise.all(
    workers.map((w) =>
      w.evaluate(() => {
        try {
          // a classic worker accepts importScripts; a module worker throws a TypeError
          (self as unknown as { importScripts(...u: string[]): void }).importScripts(
            "data:text/javascript,0",
          );
          return "classic";
        } catch (e) {
          return e instanceof TypeError ? "module" : "classic";
        }
      }),
    ),
  );
  expect(kinds).toContain("module");
  expect(kinds).not.toContain("classic");
});
