// T-010-061 [red] · NFR-010-01, NFR-010-02: live LEM and PoF lane gates on forced T2.
//
// What the green commit must deliver (route `cases/C1/?tab=simulate&tier=t2`, engine `geotech`, the lane-measurement suite of spec 018):
//   - every live section solve (Bishop search of at most 12,800 circles x 50 slices, Spencer on the 64 lowest circles) is wrapped in
//     `performance.measure("pitstudio:geotech:solve")`; every live PoF (N = 2,000, K = 64) in `performance.measure("pitstudio:geotech:pof")`;
//   - the solve is retriggered by a change of the control "Cohesion c′ (kPa)" (a `role="spinbutton"` of the region "Slope section"),
//     the PoF by the button named "Run PoF".
// Gates (headless Chromium, forced T2): NFR-010-01: the median of 20 solves is <= 50 ms; NFR-010-02: the median of 5 live PoF runs is
// <= 1 s. The measured values are also exposed as `window.__pitstudio.lane.c1` = {solve_ms_median, pof_ms_median}, which the lane-
// measurement file (DC-018-06) is written from; a model of the live lane whose gate fails must carry `data-lane="PRECOMPUTE"` on
// `data-testid="c1-lane-geotech"`.
// Oracles: the thresholds of NFR-010-01/02 (lane estimates written in the spec).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

function median(xs: number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? (s[mid] as number) : ((s[mid - 1] as number) + (s[mid] as number)) / 2;
}

test.describe("C1 lane gates on forced T2", () => {
  test("NFR-010-01 · the median of 20 live section solves is at most 50 ms", async ({ page }) => {
    await open(page, "cases/C1/?tab=simulate&tier=t2");
    const c = page
      .getByRole("region", { name: "Slope section" })
      .getByRole("spinbutton", { name: "Cohesion c′ (kPa)" });
    await expect(c).toBeVisible();
    await page.evaluate(() => performance.clearMeasures("pitstudio:geotech:solve"));
    const start = Number(await c.inputValue());
    for (let i = 1; i <= 20; i++) {
      await c.fill(String(start + i));
      await c.blur();
      await page.waitForFunction(
        (n) => performance.getEntriesByName("pitstudio:geotech:solve").length >= n,
        i,
        { timeout: 10_000 },
      );
    }
    const durations = await page.evaluate(() =>
      performance.getEntriesByName("pitstudio:geotech:solve").map((e) => e.duration),
    );
    expect(durations.length).toBeGreaterThanOrEqual(20);
    expect(median(durations.slice(-20))).toBeLessThanOrEqual(50);
  });

  test("NFR-010-02 · the median of 5 live PoF runs (N = 2,000, K = 64) is at most one second", async ({
    page,
  }) => {
    await open(page, "cases/C1/?tab=simulate&tier=t2");
    const run = page.getByRole("button", { name: "Run PoF" });
    await expect(run).toBeVisible();
    await page.evaluate(() => performance.clearMeasures("pitstudio:geotech:pof"));
    for (let i = 1; i <= 5; i++) {
      await run.click();
      await page.waitForFunction(
        (n) => performance.getEntriesByName("pitstudio:geotech:pof").length >= n,
        i,
        { timeout: 30_000 },
      );
    }
    const durations = await page.evaluate(() =>
      performance.getEntriesByName("pitstudio:geotech:pof").map((e) => e.duration),
    );
    expect(durations.length).toBeGreaterThanOrEqual(5);
    expect(median(durations.slice(-5))).toBeLessThanOrEqual(1000);
  });

  test("NFR-010-01/02 · the measured medians are exposed for the lane-measurement file and decide the lane", async ({
    page,
  }) => {
    await open(page, "cases/C1/?tab=simulate&tier=t2");
    await expect(page.getByTestId("c1-fos-bishop")).toContainText(/\d/);
    const lane = await page.evaluate(
      () =>
        (window as unknown as { __pitstudio?: { lane?: { c1?: Record<string, number> } } }).__pitstudio?.lane
          ?.c1,
    );
    expect(lane).toBeDefined();
    expect(typeof lane?.solve_ms_median).toBe("number");
    expect(typeof lane?.pof_ms_median).toBe("number");
    const passes = (lane?.solve_ms_median as number) <= 50 && (lane?.pof_ms_median as number) <= 1000;
    await expect(page.getByTestId("c1-lane-geotech")).toHaveAttribute(
      "data-lane",
      passes ? "LIVE" : "PRECOMPUTE",
    );
  });
});
