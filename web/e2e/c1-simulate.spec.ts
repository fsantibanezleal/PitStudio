// T-010-017 [red] · FR-010-04, FR-010-05, FR-010-10: the C1 Simulate tab (static stability): PoF labels, UNVERIFIED acceptance inputs,
// hostile controls and query.
//
// What the green commit must deliver (route `cases/C1/?tab=simulate`, web/src/cases/c1/, engine `geotech` of spec 018). UI contract:
//   - region `role="region"` named "Slope section" with `role="spinbutton"` controls named exactly: "Cohesion c′ (kPa)",
//     "Friction angle φ′ (°)", "Unit weight γ (kN/m³)", "Pore-pressure ratio r_u", "Slices n_s", "Samples N"; each has an element
//     `data-testid="c1-hint-<key>"` (keys: cohesion, friction, unit-weight, ru, slices, samples) that shows the valid range and the unit
//     when the value is out of range (FR-010-07 / FR-010-10: c′ 0..1e5 kPa, φ′ 0..60 °, γ (0, 40] kN/m³, r_u [0, 1), n_s 10..200 in the web,
//     N 1..100000 in the web) and is empty otherwise. URL keys: c, phi, gamma, ru, ns, n.
//   - results: `data-testid="c1-fos-bishop"` and `c1-fos-spencer` (a number with 2 decimals), `c1-pof-live`, `c1-pof-baked` (the baked
//     K = 1,024 PoF with its Wilson interval, present for the fixture section), `c1-pof-difference` (live minus baked, in percentage points).
//   - the exact label "PoF over the 64 most critical surfaces of the mean case" next to the live PoF; the exact text "Educational, not
//     design software" next to every FoS and PoF output (at least four occurrences on the tab: two FoS, live PoF, baked PoF).
//   - acceptance levels (FR-010-05): six `role="spinbutton"` controls named "Acceptance FoS (bench)", "Acceptance FoS (inter-ramp)",
//     "Acceptance FoS (overall)", "Acceptance PoF (bench)", "Acceptance PoF (inter-ramp)", "Acceptance PoF (overall)", each inside a group
//     `data-testid="c1-acceptance-<bench|inter-ramp|overall>-<fos|pof>"` that contains the badge text "UNVERIFIED" and the word
//     "configurable"; the inputs start empty (no default is stated as a fact).
//   - every solve of the `geotech` worker is wrapped in `performance.measure("pitstudio:geotech:solve")` (live PoF:
//     "pitstudio:geotech:pof"): a request to the worker is observable as a new entry of that name.
// Oracles: the texts of FR-010-04/05/10; the ranges of FR-010-07 written below; monotonicity of F in c′ (a metamorphic relation, P-010-01).
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const SIMULATE = "cases/C1/?tab=simulate";
const LIVE_LABEL = "PoF over the 64 most critical surfaces of the mean case";
const DISCLAIMER = "Educational, not design software";

function num(text: string | null): number {
  const m = /-?\d+(\.\d+)?/.exec(text ?? "");
  if (!m) throw new Error(`no number in ${JSON.stringify(text)}`);
  return Number(m[0]);
}

async function solves(page: Page): Promise<number> {
  return page.evaluate(() => performance.getEntriesByName("pitstudio:geotech:solve").length);
}

async function ready(page: Page): Promise<void> {
  await open(page, SIMULATE);
  await expect(page.getByRole("region", { name: "Slope section" })).toBeVisible();
  await expect(page.getByTestId("c1-fos-bishop")).toContainText(/\d/);
}

const CONTROLS: Record<string, string> = {
  cohesion: "Cohesion c′ (kPa)",
  friction: "Friction angle φ′ (°)",
  "unit-weight": "Unit weight γ (kN/m³)",
  ru: "Pore-pressure ratio r_u",
  slices: "Slices n_s",
  samples: "Samples N",
};

test.describe("C1 Simulate tab", () => {
  test("FR-010-04 · the live PoF carries its label and the baked PoF, its interval and the difference are shown", async ({
    page,
  }) => {
    await ready(page);
    await expect(page.getByText(LIVE_LABEL, { exact: true })).toBeVisible();
    const live = num(await page.getByTestId("c1-pof-live").textContent());
    const baked = num(await page.getByTestId("c1-pof-baked").textContent());
    await expect(page.getByTestId("c1-pof-baked")).toContainText(
      /\(\s*\d+(\.\d+)?\s*[–-]\s*\d+(\.\d+)?\s*\)/,
    ); // Wilson interval
    const diff = num(await page.getByTestId("c1-pof-difference").textContent());
    expect(Math.abs(diff - (live - baked))).toBeLessThanOrEqual(0.11); // percentage points, rounding of the two displayed values
  });

  test("FR-010-05 · 'Educational, not design software' stands next to every FoS and PoF", async ({
    page,
  }) => {
    await ready(page);
    expect(await page.getByText(DISCLAIMER, { exact: true }).count()).toBeGreaterThanOrEqual(4);
    for (const id of ["c1-fos-bishop", "c1-fos-spencer", "c1-pof-live", "c1-pof-baked"]) {
      const holder = page
        .getByTestId(id)
        .locator("xpath=ancestor::*[self::section or self::div or self::li][1]");
      await expect(holder.getByText(DISCLAIMER, { exact: true })).toBeVisible();
    }
  });

  test("FR-010-05 · the six acceptance levels are empty inputs flagged UNVERIFIED and configurable", async ({
    page,
  }) => {
    await ready(page);
    for (const scale of ["bench", "inter-ramp", "overall"]) {
      for (const measure of ["fos", "pof"]) {
        const group = page.getByTestId(`c1-acceptance-${scale}-${measure}`);
        await expect(group).toContainText("UNVERIFIED");
        await expect(group).toContainText(/configurable/i);
        const input = group.getByRole("spinbutton");
        await expect(input).toHaveCount(1);
        await expect(input).toHaveValue("");
      }
    }
    await expect(page.getByRole("spinbutton", { name: "Acceptance FoS (bench)" })).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: "Acceptance PoF (overall)" })).toBeVisible();
  });

  test("US-010-1 · raising the cohesion raises the factor of safety (P-010-01)", async ({ page }) => {
    await ready(page);
    const before = num(await page.getByTestId("c1-fos-bishop").textContent());
    const c = page.getByRole("spinbutton", { name: CONTROLS.cohesion });
    const start = Number(await c.inputValue());
    await c.fill(String(start + 40));
    await c.blur();
    await expect
      .poll(async () => num(await page.getByTestId("c1-fos-bishop").textContent()))
      .toBeGreaterThan(before);
    const spencer = num(await page.getByTestId("c1-fos-spencer").textContent());
    expect(spencer).toBeGreaterThan(0);
  });
});

test.describe("hostile controls (FR-010-10)", () => {
  const HOSTILE: [string, string, string, RegExp][] = [
    ["cohesion", "-1", "kPa", /0/],
    ["friction", "61", "°", /60/],
    ["unit-weight", "0", "kN/m³", /40/],
    ["unit-weight", "41", "kN/m³", /40/],
    ["ru", "1", "", /1/],
    ["slices", "9", "", /10/],
    ["slices", "201", "", /200/],
    ["samples", "0", "", /1/],
    ["samples", "100001", "", /100000|100,000/],
  ];
  for (const [key, value, unit, range] of HOSTILE) {
    test(`FR-010-10 · ${key} = ${value} keeps the last valid section, shows range and unit, sends no request`, async ({
      page,
    }) => {
      await ready(page);
      const fos = await page.getByTestId("c1-fos-bishop").textContent();
      const before = await solves(page);
      const control = page.getByRole("spinbutton", { name: CONTROLS[key] as string });
      await control.fill(value);
      await control.blur();
      const hint = page.getByTestId(`c1-hint-${key}`);
      await expect(hint).toContainText(range);
      if (unit) await expect(hint).toContainText(unit);
      await page.waitForTimeout(300);
      expect(await solves(page)).toBe(before); // no request to the worker
      await expect(page.getByTestId("c1-fos-bishop")).toHaveText(fos as string); // the last valid section is kept
    });
  }

  for (const [param, bad] of [
    ["c", "-5"],
    ["phi", "61"],
    ["gamma", "41"],
    ["ru", "1.5"],
    ["ns", "9"],
    ["n", "100001"],
    ["phi", "abc"],
    ["c", "NaN"],
  ]) {
    test(`FR-010-10 · the query ?${param}=${bad} is refused: the default section stays, no extra request`, async ({
      page,
    }) => {
      await open(page, SIMULATE);
      await expect(page.getByTestId("c1-fos-bishop")).toContainText(/\d/);
      const clean = await solves(page);
      const cleanFos = await page.getByTestId("c1-fos-bishop").textContent();
      await open(page, `${SIMULATE}&${param}=${encodeURIComponent(bad)}`);
      await expect(page.getByTestId("c1-fos-bishop")).toContainText(/\d/);
      await page.waitForTimeout(300);
      expect(await solves(page)).toBe(clean);
      await expect(page.getByTestId("c1-fos-bishop")).toHaveText(cleanFos as string);
      await expect(page.locator('[data-testid^="c1-hint-"]:not(:empty)').first()).toBeVisible();
    });
  }
});
