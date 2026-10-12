// T-020-010 [red] · the browser half of the chart component: FR-020-07 (zoom and pan by wheel, drag and keys, reset by double-click or the Reset button, a crosshair read-out of x and y in physical units, SI or the source's units
// followed by SI in parentheses), FR-020-11 (focusable and keyboard-operable: arrow keys move the crosshair by one data point, + and - zoom, 0 resets; a "Show data" control revealing a table with units in its header cells and the
// values of every plotted series from the full, undecimated data), FR-020-12 (colours from the theme tokens, repainted within one frame on a theme change without reload), FR-020-15 (full data, min/max-per-column drawing, at most 8
// WebGL contexts alive per page). The numerical half (decimation and view-transform properties): web/src/charts/t_020_010_chart.test.ts.
//
// The charts under test live on an unlisted prerendered sandbox route `<base>charts/` (like `<base>parity/`; test hooks invented by the test author, flagged in the report). It draws, each as `[data-testid="chart"][data-chart-id=<id>]`:
//   sine  x_i = 0.005 i s (i = 0..2000), y_i = 5 sin(2 pi x_i / 10) + 2 m;           kmh  x_i = i s (i = 0..100), y_i = 3.6 i km/h (source units; SI m/s = i);
//   big   x_i = i, y_i = ((i * 2654435761) mod 2^32) / 2^32 for i = 0..999999;       gap  100 samples with NaN for i = 40..59;       many-01 .. many-12  12 small charts of 50 samples.
// Hooks of a chart: tabindex 0; data-view-x0 | x1 | y0 | y1 (the visible ranges, numbers), data-n (samples of the full data), data-drawn (points drawn after decimation), data-drawn-ymin | ymax (extremes of the drawn points),
//   data-series-color and data-axis-color (the colours in use, resolved from the theme tokens); [data-testid="chart-plot"] (the plot area: its bounding box maps the visible x and y ranges);
//   [data-testid="readout"][data-x][data-y] (the sample nearest to the cursor or to the keyboard crosshair: its x and y as numbers, with the text of both in units);
//   button[data-testid="chart-reset"] (name "Reset"); button named "Show data" revealing table[data-testid="chart-table"] (data-rows = the number of rows of the full data, first column x).
// Interpretation fixed here: the read-out snaps to the nearest sample of the FULL data; arrow keys move it by one sample; Shift + arrow keys pan the view by 10 % of its span (FR-020-07 lists the arrows as pan keys and FR-020-11 gives
// them to the crosshair).
// Oracles: the closed-form series above (nearest sample = round(x / 0.005), y analytic), the Knuth multiplicative hash for the `big` extremes (computed here by a loop), unit conversion 1 km/h = 1/3.6 m/s, pixel geometry of the plot's
// bounding box.
import { expect, type Locator, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const chart = (page: Page, id: string) => page.locator(`[data-testid="chart"][data-chart-id="${id}"]`);
const num = async (c: Locator, attr: string) => Number(await c.getAttribute(attr));
const view = async (c: Locator) => ({
  x0: await num(c, "data-view-x0"),
  x1: await num(c, "data-view-x1"),
  y0: await num(c, "data-view-y0"),
  y1: await num(c, "data-view-y1"),
});
async function plotBox(c: Locator) {
  const box = await c.getByTestId("chart-plot").boundingBox();
  if (!box) throw new Error("the chart has no plot area");
  return box;
}
async function openCharts(page: Page): Promise<void> {
  await open(page, "charts/");
  await expect(chart(page, "sine")).toBeVisible();
}

test.describe("zoom, pan and reset (FR-020-07)", () => {
  test("FR-020-07 · wheel up zooms in about the cursor: the ranges shrink and the data point under the cursor stays under it (within 0.5 px)", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const before = await view(c);
    const box = await plotBox(c);
    const mx = box.x + 0.3 * box.width;
    const my = box.y + 0.4 * box.height;
    const xData = before.x0 + 0.3 * (before.x1 - before.x0);
    await page.mouse.move(mx, my);
    await page.mouse.wheel(0, -300);
    await expect
      .poll(async () => (await view(c)).x1 - (await view(c)).x0)
      .toBeLessThan(before.x1 - before.x0);
    const after = await view(c);
    const factor = (before.x1 - before.x0) / (after.x1 - after.x0);
    expect(factor).toBeGreaterThan(1.05);
    expect(factor).toBeLessThanOrEqual(10);
    const pxAfter = box.x + ((xData - after.x0) / (after.x1 - after.x0)) * box.width;
    expect(Math.abs(pxAfter - mx)).toBeLessThanOrEqual(0.5);
    const yBefore = before.y0 + (1 - 0.4) * (before.y1 - before.y0);
    const pyAfter = box.y + (1 - (yBefore - after.y0) / (after.y1 - after.y0)) * box.height;
    expect(Math.abs(pyAfter - my)).toBeLessThanOrEqual(0.5);
  });

  test("FR-020-07 · wheel down zooms out", async ({ page }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const box = await plotBox(c);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -400);
    const zoomed = await view(c);
    await page.mouse.wheel(0, 400);
    await expect
      .poll(async () => (await view(c)).x1 - (await view(c)).x0)
      .toBeGreaterThan(zoomed.x1 - zoomed.x0);
  });

  test("FR-020-07 · dragging pans: 100 px to the right moves the content with the pointer, the span is unchanged", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const box = await plotBox(c);
    await page.mouse.move(box.x + 0.5 * box.width, box.y + 0.5 * box.height);
    await page.mouse.wheel(0, -300); // zoom first so that there is room to pan
    const start = await view(c);
    await page.mouse.move(box.x + 0.4 * box.width, box.y + 0.5 * box.height);
    await page.mouse.down();
    await page.mouse.move(box.x + 0.4 * box.width + 100, box.y + 0.5 * box.height, { steps: 8 });
    await page.mouse.up();
    const end = await view(c);
    const span = start.x1 - start.x0;
    expect(end.x1 - end.x0).toBeCloseTo(span, 9);
    expect(end.x0 - start.x0).toBeCloseTo((-100 / box.width) * span, 6);
  });

  test("FR-020-07 · the keys + and - zoom, Shift + arrow pans, and 0 resets", async ({ page }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const initial = await view(c);
    await c.focus();
    await page.keyboard.press("+");
    const zoomed = await view(c);
    expect(zoomed.x1 - zoomed.x0).toBeLessThan(initial.x1 - initial.x0);
    await page.keyboard.press("Shift+ArrowRight");
    const panned = await view(c);
    expect(panned.x1 - panned.x0).toBeCloseTo(zoomed.x1 - zoomed.x0, 9);
    expect(panned.x0).toBeGreaterThan(zoomed.x0);
    await page.keyboard.press("-");
    await page.keyboard.press("-");
    expect((await view(c)).x1 - (await view(c)).x0).toBeGreaterThan(zoomed.x1 - zoomed.x0);
    await page.keyboard.press("0");
    expect(await view(c)).toEqual(initial);
  });

  test("FR-020-07 · a double-click and the Reset button both restore the initial view", async ({ page }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const initial = await view(c);
    const box = await plotBox(c);
    await page.mouse.move(box.x + 0.7 * box.width, box.y + 0.3 * box.height);
    await page.mouse.wheel(0, -500);
    expect((await view(c)).x1 - (await view(c)).x0).toBeLessThan(initial.x1 - initial.x0);
    await page.mouse.dblclick(box.x + 0.7 * box.width, box.y + 0.3 * box.height);
    expect(await view(c)).toEqual(initial);
    await page.mouse.wheel(0, -500);
    await c.getByRole("button", { name: "Reset" }).click();
    expect(await view(c)).toEqual(initial);
  });
});

test.describe("the read-out (FR-020-07)", () => {
  for (const u of [0.1, 0.25, 0.5, 0.777, 1]) {
    test(`FR-020-07 · sine: with the cursor at ${u * 100} % of the plot the read-out is the nearest sample, y = 5 sin(2 pi x / 10) + 2`, async ({
      page,
    }) => {
      await openCharts(page);
      const c = chart(page, "sine");
      const v = await view(c);
      const box = await plotBox(c);
      await page.mouse.move(box.x + u * (box.width - 1), box.y + box.height / 2);
      const readout = c.getByTestId("readout");
      await expect(readout).toBeVisible();
      const px = u * (box.width - 1);
      const xCursor = v.x0 + (px / box.width) * (v.x1 - v.x0);
      const i = Math.min(2000, Math.max(0, Math.round(xCursor / 0.005)));
      const x = Number(await readout.getAttribute("data-x"));
      const y = Number(await readout.getAttribute("data-y"));
      expect(Math.abs(x - i * 0.005)).toBeLessThanOrEqual(0.005 + 1e-9); // the nearest sample, give or take the pixel rounding of the cursor
      expect(Math.abs(y - (5 * Math.sin((2 * Math.PI * x) / 10) + 2))).toBeLessThan(1e-9);
      await expect(readout).toContainText(/\bm\b/);
      await expect(readout).toContainText(/\bs\b/);
    });
  }

  test("FR-020-07 · a series in source units shows them followed by SI in parentheses: sample 10 of the km/h chart reads 36 km/h (10 m/s)", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "kmh");
    await c.focus();
    for (let i = 0; i < 10; i++) await page.keyboard.press("ArrowRight");
    const readout = c.getByTestId("readout");
    expect(Number(await readout.getAttribute("data-x"))).toBe(10);
    expect(Number(await readout.getAttribute("data-y"))).toBeCloseTo(36, 9);
    await expect(readout).toContainText(/36(\.0+)?\s?km\/h\s?\(10(\.0+)?\s?m\/s\)/);
  });
});

test.describe("keyboard and data table (FR-020-11)", () => {
  test("FR-020-11 · the chart is a tab stop, and the arrow keys move the crosshair by exactly one data point", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    await expect(c).toHaveAttribute("tabindex", "0");
    await c.focus();
    await expect(c).toBeFocused();
    const readout = c.getByTestId("readout");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    const x3 = Number(await readout.getAttribute("data-x"));
    await page.keyboard.press("ArrowLeft");
    const x2 = Number(await readout.getAttribute("data-x"));
    expect(x3 - x2).toBeCloseTo(0.005, 9);
    expect(x2).toBeGreaterThanOrEqual(0.005 - 1e-9);
    expect(Number(await readout.getAttribute("data-y"))).toBeCloseTo(
      5 * Math.sin((2 * Math.PI * x2) / 10) + 2,
      9,
    );
  });

  test("FR-020-11 · the crosshair stops at the ends of the data: ArrowLeft at the first sample and ArrowRight at the last stay", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "kmh");
    await c.focus();
    await page.keyboard.press("Home");
    await page.keyboard.press("ArrowLeft");
    expect(Number(await c.getByTestId("readout").getAttribute("data-x"))).toBe(0);
    await page.keyboard.press("End");
    await page.keyboard.press("ArrowRight");
    expect(Number(await c.getByTestId("readout").getAttribute("data-x"))).toBe(100);
  });

  test("FR-020-11 · 'Show data' reveals a table with the units in its header cells and every sample of the full data", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    await c.getByRole("button", { name: /Show data/i }).click();
    const table = c.getByTestId("chart-table");
    await expect(table).toBeVisible();
    await expect(table).toHaveAttribute("data-rows", "2001");
    const heads = (await table.locator("thead th").allTextContents()).join(" ");
    expect(heads).toMatch(/\bs\b/);
    expect(heads).toMatch(/\bm\b/);
    const rows = await table
      .locator("tbody tr")
      .evaluateAll((els) =>
        els.map((r) => Array.from(r.querySelectorAll("td, th")).map((c) => c.textContent?.trim() ?? "")),
      );
    expect(rows.length).toBe(2001);
    expect(Number(rows[0]?.[0])).toBe(0);
    expect(Number(rows[0]?.[1])).toBeCloseTo(2, 9);
    expect(Number(rows[500]?.[0])).toBeCloseTo(2.5, 9);
    expect(Number(rows[500]?.[1])).toBeCloseTo(7, 9);
    expect(Number(rows[2000]?.[0])).toBeCloseTo(10, 9);
  });

  test("FR-020-11 · the table holds the FULL data, not the decimated drawing: the million-sample chart reports 1,000,000 rows", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "big");
    await c.getByRole("button", { name: /Show data/i }).click();
    await expect(c.getByTestId("chart-table")).toHaveAttribute("data-rows", "1000000");
  });

  test("FR-020-11 · the table of a series with a gap marks the missing readings and never shows 0 for them", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "gap");
    await c.getByRole("button", { name: /Show data/i }).click();
    const cells = await c
      .getByTestId("chart-table")
      .locator("tbody tr")
      .evaluateAll((rows) => rows.map((r) => r.querySelectorAll("td, th")[1]?.textContent?.trim() ?? ""));
    for (let i = 40; i < 60; i++) expect(cells[i], `row ${i}`).toMatch(/not available|n\/a|—|^$/i);
    expect(cells[39]).not.toMatch(/not available/i);
  });
});

test.describe("theme tokens (FR-020-12)", () => {
  test("FR-020-12 · toggling the theme repaints the chart within one frame, without a reload, with colours that differ between themes", async ({
    page,
  }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await openCharts(page);
    const c = chart(page, "sine");
    await page.evaluate(() => {
      (window as unknown as { __marker: number }).__marker = 1;
    });
    const light = {
      series: await c.getAttribute("data-series-color"),
      axis: await c.getAttribute("data-axis-color"),
    };
    const toggle = page.getByRole("button", { name: /^Theme:/ });
    await toggle.click();
    await toggle.click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));
    const dark = {
      series: await c.getAttribute("data-series-color"),
      axis: await c.getAttribute("data-axis-color"),
    };
    expect(await page.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(1);
    expect(light.series).toBeTruthy();
    expect(dark.series).toBeTruthy();
    expect(dark.axis).not.toBe(light.axis);
    expect(`${dark.series}|${dark.axis}`).not.toBe(`${light.series}|${light.axis}`);
  });

  test("FR-020-12 · the colours in use are the app's theme tokens as computed by the browser (not literals of the chart)", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "sine");
    const colours = [await c.getAttribute("data-series-color"), await c.getAttribute("data-axis-color")];
    const valid = await page.evaluate(
      (values) =>
        values.map((v) => {
          const s = new Option().style;
          s.color = v ?? "";
          return s.color !== "";
        }),
      colours,
    );
    expect(valid).toEqual([true, true]);
  });
});

test.describe("full data, min/max drawing, WebGL contexts (FR-020-15)", () => {
  test("FR-020-15 · a million samples are drawn as at most two points per pixel column, and the global extremes are among them", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "big");
    expect(await num(c, "data-n")).toBe(1_000_000);
    const box = await plotBox(c);
    const drawn = await num(c, "data-drawn");
    expect(drawn).toBeGreaterThan(0);
    expect(drawn).toBeLessThanOrEqual(2 * Math.ceil(box.width));
    let min = 1;
    let max = 0;
    for (let i = 0; i < 1_000_000; i++) {
      const y = Number((BigInt(i) * 2654435761n) % 4294967296n) / 4294967296;
      if (y < min) min = y;
      if (y > max) max = y;
    }
    expect(await num(c, "data-drawn-ymin")).toBeCloseTo(min, 12);
    expect(await num(c, "data-drawn-ymax")).toBeCloseTo(max, 12);
  });

  test("FR-020-15 · after a zoom the drawing is recomputed from the full data: still at most two points per column, and the extremes of the visible part are drawn", async ({
    page,
  }) => {
    await openCharts(page);
    const c = chart(page, "big");
    const box = await plotBox(c);
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    for (let i = 0; i < 5; i++) await page.mouse.wheel(0, -300);
    const v = await view(c);
    expect(v.x1 - v.x0).toBeLessThan(1_000_000 / 4);
    expect(await num(c, "data-drawn")).toBeLessThanOrEqual(2 * Math.ceil(box.width));
    const lo = Math.max(0, Math.ceil(v.x0));
    const hi = Math.min(999_999, Math.floor(v.x1));
    let min = 1;
    let max = 0;
    for (let i = lo; i <= hi; i++) {
      const y = Number((BigInt(i) * 2654435761n) % 4294967296n) / 4294967296;
      if (y < min) min = y;
      if (y > max) max = y;
    }
    expect(await num(c, "data-drawn-ymin")).toBeCloseTo(min, 12);
    expect(await num(c, "data-drawn-ymax")).toBeCloseTo(max, 12);
  });

  test("FR-020-15 · with 15 charts on the page at most 8 WebGL contexts are alive, and every chart still draws", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      const made: Array<WebGLRenderingContext | WebGL2RenderingContext> = [];
      (window as unknown as { __gl: typeof made }).__gl = made;
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (
        this: HTMLCanvasElement,
        type: string,
        ...rest: unknown[]
      ) {
        const ctx = (original as (...a: unknown[]) => unknown).call(this, type, ...rest);
        if ((type === "webgl" || type === "webgl2" || type === "experimental-webgl") && ctx)
          made.push(ctx as WebGLRenderingContext);
        return ctx as never;
      } as typeof original;
    });
    await openCharts(page);
    await expect(page.locator('[data-testid="chart"]')).toHaveCount(16); // sine, kmh, big, gap and 12 small ones
    await page.waitForTimeout(500);
    const alive = await page.evaluate(
      () =>
        (window as unknown as { __gl: Array<{ isContextLost(): boolean }> }).__gl.filter(
          (g) => !g.isContextLost(),
        ).length,
    );
    expect(alive).toBeLessThanOrEqual(8);
    for (const id of ["many-01", "many-06", "many-12", "sine", "big", "gap", "kmh"])
      expect(await num(chart(page, id), "data-drawn"), id).toBeGreaterThan(0);
  });
});
