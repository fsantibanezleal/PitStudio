// T-011-056 [red] · FR-011-38, FR-011-39: C2 and C3 live controls, baked comparison, extrapolation label (engine `fno`).
//
// What the green commit must deliver on `cases/C2/?tab=simulate` (tailings breach) and `cases/C3/?tab=simulate` (dust), spec 018 Simulate tab, forced
// tier T2 (`?tier=t2`; the default Chromium project has no WebGPU):
//   - C2 region named "FNO tailings flow": spin buttons "Breach row" (0 ... 63), "Breach column" (0 ... 63), "Release volume (m³)" (10,000 ... 200,000),
//     "Yield stress τ_y (Pa)" (10 ... 200), "Plastic viscosity μ_B (Pa·s)" (0.05 ... 1.0) with the ranges of the DC-011-02 training envelope as `min` and
//     `max` attributes of the inputs;
//   - C3 region named "FNO dust plume": spin buttons "Wind speed (m/s)" (0 ... 50) and "Wind direction (°)" (0 ... 359);
//   - after every accepted change: an image-role canvas "FNO depth field" (C2) or "FNO concentration field" (C3) is redrawn (its data URL changes),
//     the LIVE badge shows inside the region "Live field", a readout named "Evaluation time" shows "<number> ms", and an image-role canvas "Baked solver
//     field (nearest scenario)" with the REPLAY badge (region "Solver reference") and a readout "Relative L2 of the nearest scenario" showing "<number> %";
//   - FR-011-39: a control value outside the training range (yield stress 500 Pa, wind speed 80 m/s) still computes the field, shows the text
//     "extrapolation — no accuracy claim" and no relative L2 readout; a value inside the range (or exactly on a limit) shows no such text;
//   - NFR-011-03: when the measured evaluation time exceeds 1,000 ms on T2 the view is not LIVE: it shows the REPLAY badge (lane PRECOMPUTE) instead.
// Oracles: the wording of FR-011-38 and FR-011-39 (the em dash is part of the string), the ranges of the DC-011-02 envelope
// (`surrogate-io.valid-fno.json`: yield stress 10 ... 200, plastic viscosity 0.05 ... 1, release volume 10^4 ... 2 x 10^5, breach row and column 0 ... 63),
// FR-018-06 and FR-018-14 badges, NFR-011-03 (1 s on T2).
import { expect, type Locator, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const C2 = "cases/C2/?tab=simulate&tier=t2";
const C3 = "cases/C3/?tab=simulate&tier=t2";
const EXTRAPOLATION = "extrapolation — no accuracy claim";

async function snapshot(canvas: Locator): Promise<string> {
  return canvas.evaluate((c: HTMLCanvasElement) => c.toDataURL());
}

async function setValue(region: Locator, name: string, value: number): Promise<void> {
  const input = region.getByRole("spinbutton", { name });
  await input.fill(String(value));
  await input.blur();
}

async function evaluationMs(page: Page): Promise<number> {
  const readout = page.getByRole("status", { name: "Evaluation time" });
  await expect(readout).toHaveText(/\d+(\.\d+)?\s?ms/, { timeout: 60_000 });
  return Number.parseFloat(((await readout.textContent()) ?? "").match(/\d+(\.\d+)?/)?.[0] ?? "NaN");
}

test.describe("C2 tailings controls (FR-011-38)", () => {
  test("FR-011-38 · the controls carry the training ranges of the DC-011-02 envelope", async ({ page }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    const ranges: [string, string, string][] = [
      ["Breach row", "0", "63"],
      ["Breach column", "0", "63"],
      ["Release volume (m³)", "10000", "200000"],
      ["Yield stress τ_y (Pa)", "10", "200"],
      ["Plastic viscosity μ_B (Pa·s)", "0.05", "1"],
    ];
    for (const [name, min, max] of ranges) {
      const input = region.getByRole("spinbutton", { name });
      await expect(input).toHaveAttribute("min", min);
      await expect(input).toHaveAttribute("max", max);
    }
  });

  test("FR-011-38 · moving a control redraws the FNO field with the LIVE badge and the evaluation time", async ({
    page,
  }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    const field = page.getByRole("img", { name: "FNO depth field" });
    await expect(field).toBeVisible();
    const before = await snapshot(field);
    await setValue(region, "Breach column", 40);
    await expect.poll(() => snapshot(field)).not.toBe(before);
    const ms = await evaluationMs(page);
    const live = page.getByRole("region", { name: "Live field" });
    if (ms <= 1000) await expect(live.getByText("LIVE", { exact: true })).toBeVisible();
    else await expect(live.getByText("REPLAY", { exact: true })).toBeVisible(); // NFR-011-03: slower than 1 s on T2 is PRECOMPUTE
  });

  test("FR-011-38 · the baked solver field of the nearest published scenario is shown with its relative L2 and the REPLAY badge", async ({
    page,
  }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    await setValue(region, "Yield stress τ_y (Pa)", 80);
    const reference = page.getByRole("region", { name: "Solver reference" });
    await expect(reference.getByRole("img", { name: "Baked solver field (nearest scenario)" })).toBeVisible();
    await expect(reference.getByText("REPLAY", { exact: true })).toBeVisible();
    const l2 = reference.getByRole("status", { name: "Relative L2 of the nearest scenario" });
    await expect(l2).toHaveText(/\d+(\.\d+)?\s?%/);
    const value = Number.parseFloat(((await l2.textContent()) ?? "").match(/\d+(\.\d+)?/)?.[0] ?? "NaN");
    expect(value).toBeGreaterThanOrEqual(0);
  });

  test("FR-011-38 · every control of C2 triggers a new evaluation", async ({ page }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    const field = page.getByRole("img", { name: "FNO depth field" });
    await expect(field).toBeVisible();
    for (const [name, value] of [
      ["Breach row", 20],
      ["Release volume (m³)", 150000],
      ["Yield stress τ_y (Pa)", 150],
      ["Plastic viscosity μ_B (Pa·s)", 0.8],
    ] as const) {
      const before = await snapshot(field);
      await setValue(region, name, value);
      await expect.poll(() => snapshot(field), { message: `field after ${name}` }).not.toBe(before);
    }
  });
});

test.describe("C3 dust controls (FR-011-38)", () => {
  test("FR-011-38 · wind speed and direction redraw the concentration field and show the baked comparison", async ({
    page,
  }) => {
    await open(page, C3);
    const region = page.getByRole("region", { name: "FNO dust plume" });
    const field = page.getByRole("img", { name: "FNO concentration field" });
    await expect(field).toBeVisible();
    const before = await snapshot(field);
    await setValue(region, "Wind speed (m/s)", 12);
    await expect.poll(() => snapshot(field)).not.toBe(before);
    const mid = await snapshot(field);
    await setValue(region, "Wind direction (°)", 270);
    await expect.poll(() => snapshot(field)).not.toBe(mid);
    const reference = page.getByRole("region", { name: "Solver reference" });
    await expect(reference.getByRole("img", { name: "Baked solver field (nearest scenario)" })).toBeVisible();
    await expect(reference.getByText("REPLAY", { exact: true })).toBeVisible();
    await expect(reference.getByRole("status", { name: "Relative L2 of the nearest scenario" })).toHaveText(
      /\d+(\.\d+)?\s?%/,
    );
  });

  test("FR-011-38 · the wind direction takes every value of the circle (0 and 359)", async ({ page }) => {
    await open(page, C3);
    const region = page.getByRole("region", { name: "FNO dust plume" });
    const input = region.getByRole("spinbutton", { name: "Wind direction (°)" });
    await expect(input).toHaveAttribute("min", "0");
    await expect(input).toHaveAttribute("max", "359");
    for (const v of [0, 359]) {
      await setValue(region, "Wind direction (°)", v);
      await expect(page.getByRole("img", { name: "FNO concentration field" })).toBeVisible();
      await expect(page.getByText(EXTRAPOLATION)).toHaveCount(0);
    }
  });
});

test.describe("extrapolation (FR-011-39)", () => {
  test("FR-011-39 · a yield stress of 500 Pa is computed, labelled extrapolation and has no relative L2", async ({
    page,
  }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    const field = page.getByRole("img", { name: "FNO depth field" });
    const before = await snapshot(field);
    await setValue(region, "Yield stress τ_y (Pa)", 500);
    await expect(page.getByText(EXTRAPOLATION)).toBeVisible();
    await expect.poll(() => snapshot(field)).not.toBe(before);
    await expect(page.getByRole("status", { name: "Relative L2 of the nearest scenario" })).toHaveCount(0);
  });

  test("FR-011-39 · a wind speed of 80 m/s is labelled extrapolation", async ({ page }) => {
    await open(page, C3);
    await setValue(page.getByRole("region", { name: "FNO dust plume" }), "Wind speed (m/s)", 80);
    await expect(page.getByText(EXTRAPOLATION)).toBeVisible();
  });

  test("FR-011-39 · values on the limits of the training range (10 and 200 Pa) are inside it", async ({
    page,
  }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    for (const v of [10, 200]) {
      await setValue(region, "Yield stress τ_y (Pa)", v);
      await expect(page.getByRole("img", { name: "FNO depth field" })).toBeVisible();
      await expect(page.getByText(EXTRAPOLATION)).toHaveCount(0);
    }
  });

  test("FR-011-39 · returning inside the range removes the label", async ({ page }) => {
    await open(page, C2);
    const region = page.getByRole("region", { name: "FNO tailings flow" });
    await setValue(region, "Yield stress τ_y (Pa)", 500);
    await expect(page.getByText(EXTRAPOLATION)).toBeVisible();
    await setValue(region, "Yield stress τ_y (Pa)", 100);
    await expect(page.getByText(EXTRAPOLATION)).toHaveCount(0);
  });
});
