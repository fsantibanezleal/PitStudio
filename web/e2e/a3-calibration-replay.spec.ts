// T-011-040 [red] · FR-011-31: the A3 calibration replay view.
//
// What the green commit must deliver on `cases/A3/?tab=replay` (spec 018 case page, tab "Studio replay"): a region named "Calibration replay" with
//   - the badge REPLAY (text "REPLAY") in the region and no LIVE badge anywhere in it, at every compute tier (the calibration is precomputed);
//   - four image-role charts inside `figure` elements, each with a "Show data" button (spec 020 FR-020-11 convention) that reveals a table with units in
//     its header cells:
//       "Repose angle against sliding friction": the baked theta(mu) curve with its packing-seed band; columns "μ", "Mean θ (°)", "Band lower (°)",
//         "Band upper (°)", at least 5 rows in increasing mu, lower <= mean <= upper in every row;
//       "Optimiser paths": the iterates of both arms; columns "Arm" ("Gradient (tape)" or "CMA-ES"), "Iteration", "μ", "Simulations" (cumulative
//         forward-equivalent simulations); each arm's first row has mu = 0.55 (mu0, FR-011-19/20) and no cumulative count exceeds 60 (FR-011-21);
//       "Coverage of the 95 % interval": one row per arm; columns "Arm", "Covering trials" (text "n / 50"), "Coverage" (n / 50 as a fraction or a
//         percentage), "Wilson 95 % interval lower" and "Wilson 95 % interval upper" (same scale as Coverage), with lower < coverage < upper;
//       "Fitted heap profile": columns "Radius (m)", "Height (m)", "Fitted height (m)", radius increasing, at least 5 rows;
//   - the sentence "the 95 % interval covers the synthetic truth in n of 50 trials" per arm, and no claim that one arm is better, faster, more accurate
//     or narrower unless the sentence "paired 95 % interval of the difference excludes 0" accompanies it; otherwise the words "no significant difference".
// Oracles: FR-011-31 text, FR-011-19/20/21/24 constants (mu0 = 0.55, budget 60, 50 trials, Wilson 95 % interval), internal consistency of the displayed
// numbers (coverage = n / 50, the band contains the mean, the Wilson interval contains the coverage), FR-000-05 wording.
import { expect, type Locator, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const REPLAY = "cases/A3/?tab=replay";

async function chart(page: Page, name: string): Promise<Locator> {
  const region = page.getByRole("region", { name: "Calibration replay" });
  const img = region.getByRole("img", { name });
  await expect(img).toBeVisible();
  const figure = region.locator("figure").filter({ has: img });
  await figure.getByRole("button", { name: "Show data" }).click();
  const table = figure.getByRole("table");
  await expect(table).toBeVisible();
  return table;
}

function toNumber(text: string): number {
  return Number.parseFloat(text.replace(/[^0-9eE+.-]/g, ""));
}

interface Grid {
  heads: string[];
  rows: string[][];
}

async function read(table: Locator): Promise<Grid> {
  const heads = (await table.locator("thead th").allTextContents()).map((h) => h.trim());
  const rows: string[][] = [];
  for (const row of await table.locator("tbody tr").all())
    rows.push((await row.locator("th, td").allTextContents()).map((c) => c.trim()));
  return { heads, rows };
}

function column(grid: Grid, pattern: RegExp): number {
  const i = grid.heads.findIndex((h) => pattern.test(h));
  expect(i, `a column matching ${pattern} in [${grid.heads.join(" | ")}]`).toBeGreaterThanOrEqual(0);
  return i;
}

test.describe("badge and tiers (FR-011-31)", () => {
  for (const tier of ["t0", "t1", "t2"]) {
    test(`FR-011-31 · the calibration view carries the REPLAY badge and no LIVE badge on tier ${tier}`, async ({
      page,
    }) => {
      await open(page, `${REPLAY}&tier=${tier}`);
      const region = page.getByRole("region", { name: "Calibration replay" });
      await expect(region).toBeVisible();
      await expect(region.getByText("REPLAY", { exact: true }).first()).toBeVisible();
      await expect(region.getByText("LIVE", { exact: true })).toHaveCount(0);
    });
  }
});

test.describe("the four charts (FR-011-31)", () => {
  test("FR-011-31 · the theta(mu) curve has its packing-seed band: increasing mu, lower <= mean <= upper", async ({
    page,
  }) => {
    await open(page, REPLAY);
    const grid = await read(await chart(page, "Repose angle against sliding friction"));
    const [iMu, iMean, iLo, iHi] = [
      column(grid, /^μ/),
      column(grid, /Mean θ.*°/),
      column(grid, /Band lower.*°/),
      column(grid, /Band upper.*°/),
    ];
    expect(grid.rows.length).toBeGreaterThanOrEqual(5);
    let previous = Number.NEGATIVE_INFINITY;
    for (const row of grid.rows) {
      const [mu, mean, lo, hi] = [iMu, iMean, iLo, iHi].map((i) => toNumber(row[i] as string)) as [
        number,
        number,
        number,
        number,
      ];
      expect(mu).toBeGreaterThan(previous);
      previous = mu;
      expect(lo).toBeLessThanOrEqual(mean);
      expect(mean).toBeLessThanOrEqual(hi);
    }
  });

  test("FR-011-31 · both optimiser paths start at mu0 = 0.55 and stay within 60 forward-equivalent simulations", async ({
    page,
  }) => {
    await open(page, REPLAY);
    const grid = await read(await chart(page, "Optimiser paths"));
    const [iArm, iMu, iSims] = [column(grid, /^Arm/), column(grid, /^μ/), column(grid, /^Simulations/)];
    for (const arm of ["Gradient (tape)", "CMA-ES"]) {
      const rows = grid.rows.filter((r) => r[iArm] === arm);
      expect(rows.length, `iterates of ${arm}`).toBeGreaterThanOrEqual(2);
      expect(toNumber((rows[0] as string[])[iMu] as string)).toBeCloseTo(0.55, 12);
      const sims = rows.map((r) => toNumber(r[iSims] as string));
      expect(Math.max(...sims)).toBeLessThanOrEqual(60);
      expect([...sims].sort((a, b) => a - b)).toEqual(sims);
    }
  });

  test("FR-011-31 · the coverage chart gives n / 50, the coverage and a Wilson interval that contains it, per arm", async ({
    page,
  }) => {
    await open(page, REPLAY);
    const grid = await read(await chart(page, "Coverage of the 95 % interval"));
    const [iArm, iCount, iCov, iLo, iHi] = [
      column(grid, /^Arm/),
      column(grid, /Covering trials/),
      column(grid, /^Coverage/),
      column(grid, /Wilson 95 % interval lower/),
      column(grid, /Wilson 95 % interval upper/),
    ];
    for (const arm of ["Gradient (tape)", "CMA-ES"]) {
      const rows = grid.rows.filter((r) => r[iArm] === arm);
      expect(rows).toHaveLength(1);
      const row = rows[0] as string[];
      const m = (row[iCount] as string).match(/^(\d+)\s*\/\s*50$/);
      expect(m, `"n / 50" for ${arm}`).not.toBeNull();
      const covering = Number(m?.[1]);
      expect(covering).toBeGreaterThanOrEqual(0);
      expect(covering).toBeLessThanOrEqual(50);
      const scale = (row[iCov] as string).includes("%") ? 100 : 1;
      const coverage = toNumber(row[iCov] as string) / scale;
      expect(coverage).toBeCloseTo(covering / 50, 2);
      const lower = toNumber(row[iLo] as string) / scale;
      const upper = toNumber(row[iHi] as string) / scale;
      expect(lower).toBeGreaterThanOrEqual(0);
      expect(upper).toBeLessThanOrEqual(1);
      expect(lower).toBeLessThan(coverage);
      expect(coverage).toBeLessThan(upper);
    }
  });

  test("FR-011-31 · the fitted heap profile gives radius, height and the fitted height in metres", async ({
    page,
  }) => {
    await open(page, REPLAY);
    const grid = await read(await chart(page, "Fitted heap profile"));
    const [iR, iH, iF] = [
      column(grid, /Radius \(m\)/),
      column(grid, /^Height \(m\)/),
      column(grid, /Fitted height \(m\)/),
    ];
    expect(grid.rows.length).toBeGreaterThanOrEqual(5);
    const radius = grid.rows.map((r) => toNumber(r[iR] as string));
    expect([...radius].sort((a, b) => a - b)).toEqual(radius);
    for (const r of grid.rows) {
      expect(Number.isFinite(toNumber(r[iH] as string))).toBe(true);
      expect(Number.isFinite(toNumber(r[iF] as string))).toBe(true);
    }
  });
});

test.describe("honest statements (FR-011-31, FR-000-05)", () => {
  test("FR-011-31 · the coverage statement is in words for both arms", async ({ page }) => {
    await open(page, REPLAY);
    const region = page.getByRole("region", { name: "Calibration replay" });
    await expect(
      region.getByText(/95 % interval covers the synthetic truth in \d+ of 50 trials/),
    ).toHaveCount(2);
  });

  test("FR-011-31 · no arm is called better, faster, more accurate or narrower without the decision rule", async ({
    page,
  }) => {
    await open(page, REPLAY);
    const region = page.getByRole("region", { name: "Calibration replay" });
    const text = (await region.textContent()) ?? "";
    if (/\b(better|faster|more accurate|narrower)\b/i.test(text)) {
      await expect(region).toContainText("paired 95 % interval of the difference excludes 0");
    } else {
      await expect(region).toContainText("no significant difference");
    }
  });
});
