// T-010-034 [red] · FR-010-32, NFR-010-03, NFR-010-05: the C1 cut-off slider and the forecaster lanes.
//
// What the green commit must deliver (route `cases/C1/?tab=charts&tier=t2`, engines `geotech` and `forecasters` of spec 018). UI contract:
//   - `role="slider"` named "Forecast cut-off" with min 0.30, max 0.95, step 0.01 (attributes `aria-valuemin`, `aria-valuemax`, and the
//     step 0.01 of the keyboard: ArrowRight adds 0.01); its value is shown as `data-testid="c1-cutoff-value"` with two decimals.
//   - one row per method with `data-testid="c1-forecast-<method>"` for inverse_velocity, bayesian_ttf, tcn, patchtst, chronos_bolt_zero_shot,
//     chronos_bolt_fine_tuned; each row has `data-lane` "LIVE" or "PRECOMPUTE" and a TTF text (`data-testid="c1-ttf-<method>"`, hours).
//     Inverse velocity and the Bayesian band are always LIVE and are refitted live on every slider move (the TTF text changes with the
//     cut-off on the fixture event); a LIVE learned model updates live too; a PRECOMPUTE model shows the baked forecast of the nearest grid
//     cut-off and prints that cut-off in its row as "baked forecast at cut-off 0.xx" (two decimals, a value of the 0.30 .. 0.95 grid).
//   - the engines wrap each inverse-velocity + Bayesian refit in `performance.measure("pitstudio:forecasters:refit")` and each learned
//     read-out in `performance.measure("pitstudio:forecasters:readout:<method>")`.
// Gates on forced T2 (headless Chromium; `?tier=t2`): NFR-010-03: the 95th percentile of 50 refits is <= 16 ms; NFR-010-05: a LIVE learned
// model's read-out of <= 4 blocks takes <= 1 s, otherwise the model's lane is PRECOMPUTE (FR-000-15).
// Oracles: the ranges and steps of FR-010-32, the gates of NFR-010-03/05.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const CHARTS = "cases/C1/?tab=charts&tier=t2";
const METHODS = [
  "inverse_velocity",
  "bayesian_ttf",
  "tcn",
  "patchtst",
  "chronos_bolt_zero_shot",
  "chronos_bolt_fine_tuned",
];
const LEARNED = METHODS.slice(2);

async function ready(page: Page) {
  await open(page, CHARTS);
  await expect(page.getByRole("slider", { name: "Forecast cut-off" })).toBeVisible();
  await expect(page.getByTestId("c1-ttf-inverse_velocity")).toContainText(/\d/);
}

function hours(text: string | null): number {
  const m = /-?\d+(\.\d+)?/.exec(text ?? "");
  if (!m) throw new Error(`no number in ${JSON.stringify(text)}`);
  return Number(m[0]);
}

test.describe("C1 cut-off slider", () => {
  test("FR-010-32 · the slider spans 0.30 to 0.95 in steps of 0.01", async ({ page }) => {
    await ready(page);
    const slider = page.getByRole("slider", { name: "Forecast cut-off" });
    await expect(slider).toHaveAttribute("aria-valuemin", "0.3");
    await expect(slider).toHaveAttribute("aria-valuemax", "0.95");
    await slider.focus();
    await page.keyboard.press("Home");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.30/);
    await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.31/);
    await page.keyboard.press("End");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.95/);
    await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.95/); // clamped
  });

  test("FR-010-32 · inverse velocity and the Bayesian band are refitted live on every move", async ({
    page,
  }) => {
    await ready(page);
    const slider = page.getByRole("slider", { name: "Forecast cut-off" });
    await slider.focus();
    await page.keyboard.press("Home");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.30/);
    const early = hours(await page.getByTestId("c1-ttf-inverse_velocity").textContent());
    const earlyBayes = await page.getByTestId("c1-ttf-bayesian_ttf").textContent();
    for (let i = 0; i < 30; i++) await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.60/);
    const later = hours(await page.getByTestId("c1-ttf-inverse_velocity").textContent());
    expect(later).not.toBe(early);
    await expect(page.getByTestId("c1-ttf-bayesian_ttf")).not.toHaveText(earlyBayes as string);
    for (const m of ["inverse_velocity", "bayesian_ttf"]) {
      await expect(page.getByTestId(`c1-forecast-${m}`)).toHaveAttribute("data-lane", "LIVE");
    }
  });

  test("FR-010-32 · a PRECOMPUTE model shows the baked forecast of the nearest grid cut-off with that cut-off printed", async ({
    page,
  }) => {
    await ready(page);
    const slider = page.getByRole("slider", { name: "Forecast cut-off" });
    await slider.focus();
    await page.keyboard.press("Home");
    for (let i = 0; i < 13; i++) await page.keyboard.press("ArrowRight"); // 0.43
    await expect(page.getByTestId("c1-cutoff-value")).toHaveText(/0\.43/);
    let precompute = 0;
    for (const m of LEARNED) {
      const row = page.getByTestId(`c1-forecast-${m}`);
      await expect(row).toBeVisible();
      const lane = await row.getAttribute("data-lane");
      expect(["LIVE", "PRECOMPUTE"]).toContain(lane);
      if (lane === "PRECOMPUTE") {
        precompute++;
        const text = (await row.textContent()) ?? "";
        const m2 = /baked forecast at cut-off (0\.\d\d)/.exec(text);
        expect(m2, `row of ${m} must print the cut-off of its baked forecast`).not.toBeNull();
        const printed = Number(m2?.[1]);
        expect(printed).toBeGreaterThanOrEqual(0.3);
        expect(printed).toBeLessThanOrEqual(0.95);
        expect(Math.abs(printed - 0.43)).toBeLessThanOrEqual(0.05); // the nearest grid value to the slider
      }
    }
    expect(precompute).toBeGreaterThanOrEqual(1); // the zero-shot arm is published as baked forecasts only
    await expect(page.getByTestId("c1-forecast-chronos_bolt_zero_shot")).toHaveAttribute(
      "data-lane",
      "PRECOMPUTE",
    );
  });

  test("NFR-010-03 · the 95th percentile of 50 refits after slider moves is at most 16 ms on forced T2", async ({
    page,
  }) => {
    await ready(page);
    const slider = page.getByRole("slider", { name: "Forecast cut-off" });
    await slider.focus();
    await page.keyboard.press("Home");
    await page.evaluate(() => performance.clearMeasures("pitstudio:forecasters:refit"));
    for (let i = 0; i < 50; i++) {
      await page.keyboard.press(i < 25 ? "ArrowRight" : "ArrowLeft");
      await page.waitForTimeout(20);
    }
    const durations = await page.evaluate(() =>
      performance.getEntriesByName("pitstudio:forecasters:refit").map((e) => e.duration),
    );
    expect(durations.length).toBeGreaterThanOrEqual(50);
    const sorted = [...durations].sort((a, b) => a - b);
    const p95 = sorted[Math.min(sorted.length - 1, Math.ceil(0.95 * sorted.length) - 1)] as number;
    expect(p95).toBeLessThanOrEqual(16);
  });

  test("NFR-010-05 · a LIVE learned model reads out in at most one second, otherwise its lane is PRECOMPUTE", async ({
    page,
  }) => {
    await ready(page);
    for (const m of LEARNED) {
      const lane = await page.getByTestId(`c1-forecast-${m}`).getAttribute("data-lane");
      const ms = await page.evaluate(
        (name) =>
          performance.getEntriesByName(`pitstudio:forecasters:readout:${name}`).map((e) => e.duration),
        m,
      );
      if (lane === "LIVE") {
        expect(ms.length).toBeGreaterThan(0);
        expect(Math.max(...ms)).toBeLessThanOrEqual(1000);
      } else {
        expect(lane).toBe("PRECOMPUTE");
      }
    }
  });
});
