// T-018-016 [red] · FR-018-44: a runtime or model file that cannot be fetched (offline, HTTP error, blocked) or fails to compile or
// instantiate makes the engine fall back to T0, shows "<runtime> could not load — showing precomputed results" and leaves no
// unhandled promise rejection.
//
// Hooks: web/e2e/support/simulate.ts. A T0 engine panel has data-state="replay", data-tier="t0" and the REPLAY badge; the
// message is in [data-testid="engine-notice"]. Cases (section 7.1): C1 forecasters (ORT-web, `.onnx` model), B1 traffic (Rapier),
// C1 geotech "Run in Python" (Pyodide). Oracles: the EARS text; engines that do not need the broken runtime keep computing.
import { expect, type Page, test } from "@playwright/test";
import { enginePanel, openSimulate } from "./support/simulate";

const REPLAY_NOTICE = /could not load — showing precomputed results/;

async function trackRejections(page: Page): Promise<() => Promise<string[]>> {
  await page.addInitScript(() => {
    const w = window as unknown as { __rejections: string[] };
    w.__rejections = [];
    window.addEventListener("unhandledrejection", (e) => w.__rejections.push(String(e.reason)));
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  return async () => [
    ...errors,
    ...(await page.evaluate(() => (window as unknown as { __rejections: string[] }).__rejections)),
  ];
}

async function expectFallback(page: Page, engine: string, runtimeName: RegExp): Promise<void> {
  const panel = enginePanel(page, engine);
  await expect(panel).toHaveAttribute("data-state", "replay", { timeout: 60_000 });
  await expect(panel).toHaveAttribute("data-tier", "t0");
  await expect(panel.getByTestId("lane-badge")).toHaveText("REPLAY");
  const notice = panel.getByTestId("engine-notice");
  await expect(notice).toContainText(REPLAY_NOTICE);
  await expect(notice).toContainText(runtimeName);
}

test.describe("blocked or broken runtime files fall back to T0 (FR-018-44)", () => {
  test("FR-018-44 · ORT-web files blocked (request aborted): forecasters fall back to T0, geotech keeps computing live", async ({
    page,
  }) => {
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/ort\//, (route) => route.abort("blockedbyclient"));
    await openSimulate(page, "C1", "&tier=t2");
    await expectFallback(page, "forecasters", /ORT/i);
    await expect(enginePanel(page, "geotech").getByTestId("lane-badge")).toHaveText("LIVE", {
      timeout: 60_000,
    });
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-44 · ORT-web files answering HTTP 500 fall back to T0 with the same message", async ({
    page,
  }) => {
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/ort\//, (route) => route.fulfill({ status: 500, body: "boom" }));
    await openSimulate(page, "C1", "&tier=t2");
    await expectFallback(page, "forecasters", /ORT/i);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-44 · a model file answering 404 falls back to T0", async ({ page }) => {
    const rejections = await trackRejections(page);
    await page.route(/\.onnx(\?|$)/, (route) => route.fulfill({ status: 404, body: "missing" }));
    await openSimulate(page, "C1", "&tier=t2");
    await expectFallback(page, "forecasters", /./);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-44 · a WASM file that is not WebAssembly (fails to compile) falls back to T0", async ({
    page,
  }) => {
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/ort\/.*\.wasm(\?|$)/, (route) =>
      route.fulfill({ status: 200, contentType: "application/wasm", body: "this is not a wasm module" }),
    );
    await openSimulate(page, "C1", "&tier=t2");
    await expectFallback(page, "forecasters", /ORT/i);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-44 · Rapier files blocked: the traffic engine falls back to T0 and names Rapier", async ({
    page,
  }) => {
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/rapier\//, (route) => route.abort("failed"));
    await openSimulate(page, "B1", "&tier=t2");
    await expectFallback(page, "traffic", /Rapier/i);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-44 · Pyodide files blocked: 'Run in Python' reports the failure, keeps the TypeScript result and raises nothing", async ({
    page,
  }) => {
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/pyodide\//, (route) => route.abort("blockedbyclient"));
    await openSimulate(page, "C1", "&tier=t2");
    const panel = enginePanel(page, "geotech");
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    await panel.getByRole("button", { name: "Run in Python" }).click();
    await expect(panel).toContainText(/(Pyodide|Python reference) could not load/, { timeout: 60_000 });
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE");
    expect(await rejections()).toEqual([]);
  });
});

test.describe("offline after load (FR-018-44)", () => {
  test("FR-018-44 · going offline after the page loaded and then opening Simulate falls back to T0 and keeps the page usable", async ({
    page,
    context,
  }) => {
    const rejections = await trackRejections(page);
    await page.goto("cases/C1/?tier=t2");
    await expect(page.getByRole("tab", { name: /Simulate/ })).toBeVisible();
    await context.setOffline(true);
    await page.getByRole("tab", { name: /Simulate/ }).click();
    await expectFallback(page, "forecasters", /ORT/i);
    // the page is still interactive: the tab list takes keyboard input
    await page.getByRole("tab", { name: /Context/ }).click();
    await expect(page.getByRole("tab", { name: /Context/, selected: true })).toBeVisible();
    await context.setOffline(false);
    expect(await rejections()).toEqual([]);
  });
});
