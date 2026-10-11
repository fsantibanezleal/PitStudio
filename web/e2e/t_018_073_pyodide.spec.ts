// T-018-073 [red] · FR-018-61 ("Run in Python": Pyodide, numpy, PyYAML and the minephys wheel evaluate the same inputs; both results side by side with absolute and
// relative differences and a parity verdict), FR-018-62 (a wheel or package that fails its SHA-256 check, or Pyodide not ready within 60 s: "Python reference could not
// load", the TypeScript result is kept, no unhandled promise rejection) and NFR-018-06 (first result on CI Chromium within 20 s as a warning, 60 s as the hard limit).
//
// Hooks: web/e2e/support/simulate.ts (engine panels, lane badge) and, inside the panel of an analytical engine, a button named "Run in Python"; after the run
//   [data-testid="python-result"][data-verdict="pass" | "fail"] holds one row per numeric output field:
//   [data-testid="python-row"][data-field="<result field>"] with data-ts, data-py, data-abs, data-rel (full-precision numbers) and the visible cells TypeScript, Python, absolute
//   difference, relative difference. The verdict applies the FR-018-51 tolerance |y_ts - y_py| <= 1e-12 s_y + rtol |y_py| with rtol = 1e-9 for closed forms.
// The runtime files are under `<base>assets/runtimes/pyodide/` (requests: `pyodide.asm.wasm`, `pyodide-lock.json`, wheels `numpy-*.whl`, `pyyaml-*.whl`, `minephys-*.whl`).
// Oracles: the EARS text; for the verdict the numbers read from the page itself (difference arithmetic recomputed here); case C1 geotech and D2 comminution are analytical.
import { expect, type Page, test } from "@playwright/test";
import { enginePanel, openSimulate } from "./support/simulate";

const FAIL_TEXT = "Python reference could not load";

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

test.describe("Run in Python (FR-018-61)", () => {
  test("FR-018-61 · pressing 'Run in Python' on C1 geotech shows the TypeScript and Python results side by side with their differences and a parity verdict, within 60 s", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openSimulate(page, "C1", "&tier=t2");
    const panel = enginePanel(page, "geotech");
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    const t0 = Date.now();
    await panel.getByRole("button", { name: "Run in Python" }).click();
    const result = panel.getByTestId("python-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    const seconds = (Date.now() - t0) / 1000;
    test.info().annotations.push({ type: "pyodide-first-result-seconds", description: seconds.toFixed(1) });
    expect(seconds).toBeLessThanOrEqual(60);
    if (seconds > 20)
      test
        .info()
        .annotations.push({
          type: "warning",
          description: `NFR-018-06: first result took ${seconds.toFixed(1)} s (> 20 s)`,
        });

    await expect(result).toHaveAttribute("data-verdict", "pass");
    const rows = result.getByTestId("python-row");
    expect(await rows.count()).toBeGreaterThan(0);
    for (let i = 0; i < (await rows.count()); i++) {
      const row = rows.nth(i);
      const [ts, py, abs, rel] = await Promise.all(
        ["data-ts", "data-py", "data-abs", "data-rel"].map((a) => row.getAttribute(a)),
      );
      const t = Number(ts);
      const p = Number(py);
      expect(Number.isFinite(t) && Number.isFinite(p), `row ${i} numbers`).toBe(true);
      expect(Math.abs(Number(abs) - Math.abs(t - p)), `row ${i} absolute difference`).toBeLessThanOrEqual(
        1e-12 * Math.max(Math.abs(t), Math.abs(p), 1e-300),
      );
      if (p !== 0)
        expect(
          Math.abs(Number(rel) - Math.abs(t - p) / Math.abs(p)),
          `row ${i} relative difference`,
        ).toBeLessThanOrEqual(1e-9);
      expect(Math.abs(t - p), `row ${i} parity`).toBeLessThanOrEqual(1e-9 * Math.abs(p) + 1e-12);
      await expect(row).toContainText(/TypeScript|\d/);
    }
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE");
  });

  test("FR-018-61 · the result table has the four columns TypeScript, Python, absolute difference and relative difference", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openSimulate(page, "D2", "&tier=t2");
    const panel = enginePanel(page, "comminution");
    await panel.getByRole("button", { name: "Run in Python" }).click();
    const result = panel.getByTestId("python-result");
    await expect(result).toBeVisible({ timeout: 60_000 });
    for (const name of [/TypeScript/i, /Python/i, /absolute/i, /relative/i])
      await expect(result.getByRole("columnheader", { name })).toBeVisible();
  });

  test("FR-018-61 · only analytical engines offer the button: the ORT-web forecasters of C1 and the detector of B2 do not", async ({
    page,
  }) => {
    await openSimulate(page, "C1", "&tier=t2");
    await expect(enginePanel(page, "geotech").getByRole("button", { name: "Run in Python" })).toBeVisible();
    await expect(enginePanel(page, "forecasters").getByRole("button", { name: "Run in Python" })).toHaveCount(
      0,
    );
    await openSimulate(page, "B2", "&tier=t2");
    await expect(enginePanel(page, "detector").getByRole("button", { name: "Run in Python" })).toHaveCount(0);
  });
});

test.describe("Python reference failures (FR-018-62)", () => {
  async function pressAndExpectFailure(page: Page): Promise<void> {
    await openSimulate(page, "C1", "&tier=t2");
    const panel = enginePanel(page, "geotech");
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    const before = await panel.locator("[data-kpi], [data-testid='kpi-panel'] [data-kpi]").allTextContents();
    await panel.getByRole("button", { name: "Run in Python" }).click();
    await expect(panel).toContainText(FAIL_TEXT, { timeout: 70_000 });
    await expect(panel.getByTestId("python-result")).toHaveCount(0);
    // the TypeScript result is kept
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE");
    expect(await panel.locator("[data-kpi], [data-testid='kpi-panel'] [data-kpi]").allTextContents()).toEqual(
      before,
    );
  }

  test("FR-018-62 · a minephys wheel whose bytes differ from its pinned SHA-256 shows 'Python reference could not load' and keeps the TypeScript result", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/pyodide\/.*minephys.*\.whl(\?|$)/i, async (route) => {
      const res = await route.fetch();
      const body = Buffer.from(await res.body());
      body[Math.floor(body.length / 2)] = (body[Math.floor(body.length / 2)] as number) ^ 0xff;
      await route.fulfill({ response: res, body });
    });
    await pressAndExpectFailure(page);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-62 · a corrupted numpy wheel is refused the same way", async ({ page }) => {
    test.setTimeout(150_000);
    const rejections = await trackRejections(page);
    await page.route(/\/assets\/runtimes\/pyodide\/.*numpy.*\.whl(\?|$)/i, async (route) => {
      const res = await route.fetch();
      const body = Buffer.from(await res.body());
      body[10] = (body[10] as number) ^ 0x01;
      await route.fulfill({ response: res, body });
    });
    await pressAndExpectFailure(page);
    expect(await rejections()).toEqual([]);
  });

  test("FR-018-62 · Pyodide that is not ready within 60 s shows the same message (timer fast-forwarded), with no unhandled rejection", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const rejections = await trackRejections(page);
    await page.route(
      /\/assets\/runtimes\/pyodide\/.*pyodide\.asm\.wasm(\?|$)/,
      () => new Promise(() => undefined),
    ); // the request never completes
    await page.clock.install();
    await openSimulate(page, "C1", "&tier=t2");
    const panel = enginePanel(page, "geotech");
    await page.clock.resume();
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    await panel.getByRole("button", { name: "Run in Python" }).click();
    await page.clock.fastForward(61_000);
    await expect(panel).toContainText(FAIL_TEXT);
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE");
    expect(await rejections()).toEqual([]);
  });
});
