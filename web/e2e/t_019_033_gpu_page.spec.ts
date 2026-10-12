// T-019-033 [red] · FR-019-27 (/studio/gpu: timelines of every published public stage: busy %, memory against the GPU's total, power against the enforced limit, SM clock, throttle reasons), FR-019-28 (busy % with power-at-limit
// beside it), FR-019-29 (the "How measured" popover) and FR-019-31 (a null telemetry value reads "not available on this GPU"). Unit half: web/src/studio/telemetry/t_019_033_timelines.test.tsx.
//
// Fixture runs: web/e2e/support/studio-runs.ts. Hooks as in the unit half: [data-testid="gpu-stage"][data-run][data-stage], [data-testid="chart"][data-chart], [data-testid="power-at-limit"], [data-testid="chart-reference"][data-ref][data-value],
// button[data-testid="how-measured"] and [data-testid="how-measured-popover"].
// Oracles: the facts of the fixture runs (A: stage st56_encode, 3 points; B: stage st50_physics, 3 points with a null power reading at t = 4 s; BIG: stage s50_evaluate, 1 point; GPU 17,171,480,576 B = 16 GiB, 175 W).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { RUN_A, RUN_B, RUN_BIG } from "./support/studio-runs";

const STAGES: Array<[string, string]> = [
  [RUN_A, "st56_encode"],
  [RUN_B, "st50_physics"],
  [RUN_BIG, "s50_evaluate"],
];
const stage = (page: import("@playwright/test").Page, run: string, id: string) =>
  page.locator(`[data-testid="gpu-stage"][data-run="${run}"][data-stage="${id}"]`);

test.describe("the GPU page (FR-019-27)", () => {
  test("FR-019-27 · every public stage with published telemetry has a block, and no local-only stage has one", async ({
    page,
  }) => {
    await open(page, "studio/gpu/");
    for (const [run, id] of STAGES) await expect(stage(page, run, id)).toHaveCount(1);
    for (const [run, id] of [
      [RUN_A, "st53_sensors"],
      [RUN_A, "st45b_kit_validate"],
      [RUN_B, "st55_sdg"],
    ])
      await expect(stage(page, run as string, id as string)).toHaveCount(0);
    await expect(page.locator('[data-testid="gpu-stage"]')).toHaveCount(STAGES.length);
  });

  for (const [run, id] of STAGES) {
    test(`FR-019-27 · ${id} of ${run}: busy, memory, power, SM clock and throttle charts`, async ({
      page,
    }) => {
      await open(page, "studio/gpu/");
      for (const name of ["busy", "memory", "power", "sm_clock", "throttle"])
        await expect(
          stage(page, run, id).locator(`[data-testid="chart"][data-chart="${name}"]`),
        ).toBeVisible();
      await expect(stage(page, run, id).locator('[data-chart="busy"]')).toContainText(
        "time-busy fraction, not SM occupancy",
      );
    });
  }

  test("FR-019-27 · the memory chart has the card's 16 GB reference and the power chart the 175 W limit", async ({
    page,
  }) => {
    await open(page, "studio/gpu/");
    const s = stage(page, RUN_B, "st50_physics");
    await expect(s.locator('[data-chart="memory"] [data-ref="vram_total"]')).toHaveAttribute(
      "data-value",
      "17171480576",
    );
    await expect(s.locator('[data-chart="memory"] [data-ref="vram_total"]')).toContainText("16 GB");
    await expect(s.locator('[data-chart="power"] [data-ref="power_limit"]')).toHaveAttribute(
      "data-value",
      "175",
    );
    await expect(s.locator('[data-chart="power"] [data-ref="power_limit"]')).toContainText("175 W");
  });

  test("FR-019-27 · the throttle chart is a stacked band with the five reasons", async ({ page }) => {
    await open(page, "studio/gpu/");
    const band = stage(page, RUN_B, "st50_physics").locator('[data-chart="throttle"]');
    await expect(band).toHaveAttribute("data-kind", "stacked-band");
    expect(
      await band
        .locator("[data-series]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-series")).sort()),
    ).toEqual(["hw_slowdown", "hw_thermal", "power_brake", "sw_power_cap", "sw_thermal"]);
  });
});

test.describe("busy next to power at limit (FR-019-28)", () => {
  for (const [run, id] of STAGES) {
    test(`FR-019-28 · ${id} of ${run}: the busy chart holds the power-at-limit fraction`, async ({
      page,
    }) => {
      await open(page, "studio/gpu/");
      await expect(
        stage(page, run, id).locator('[data-chart="busy"] [data-testid="power-at-limit"]'),
      ).toContainText(/\d+(\.\d+)?\s?%|not available on this GPU/);
    });
  }

  test("FR-019-28 · the physics stage reads the 6.25 % of its run card", async ({ page }) => {
    await open(page, "studio/gpu/");
    await expect(
      stage(page, RUN_B, "st50_physics").locator('[data-chart="busy"] [data-testid="power-at-limit"]'),
    ).toContainText(/6\.25\s?%/);
  });
});

test.describe("a missing reading (FR-019-31)", () => {
  test("FR-019-31 · the null power value of the physics stage reads 'not available on this GPU' in the data table and is not drawn as zero", async ({
    page,
  }) => {
    await open(page, "studio/gpu/");
    const chart = stage(page, RUN_B, "st50_physics").locator('[data-chart="power"]');
    await expect(chart).toHaveAttribute("data-missing", "1");
    await chart.getByRole("button", { name: /Show data/i }).click();
    const cells = await chart
      .locator("table tbody tr")
      .evaluateAll((rows) => rows.map((r) => r.querySelectorAll("td, th")[1]?.textContent?.trim()));
    expect(cells).toEqual(["31.5", "97.2", "not available on this GPU"]);
  });
});

test.describe("How measured (FR-019-29)", () => {
  test("FR-019-29 · the popover names the run's sampling rate, the definitions and the NVML pages, and Escape returns the focus", async ({
    page,
  }) => {
    await open(page, "studio/gpu/");
    const button = stage(page, RUN_B, "st50_physics")
      .locator('[data-chart="busy"]')
      .getByTestId("how-measured");
    await button.click();
    const pop = page.getByTestId("how-measured-popover");
    await expect(pop).toBeVisible();
    await expect(pop).toContainText(/\b2\s?Hz/);
    await expect(pop).toContainText(/utilisation/i);
    await expect(pop).toContainText(/power averaging/i);
    await expect(pop).toContainText(/difference of the total.energy counter/i);
    const hrefs = await pop.locator("a").evaluateAll((els) => els.map((e) => e.getAttribute("href")));
    expect(hrefs.length).toBeGreaterThan(0);
    for (const h of hrefs) expect(h).toMatch(/^https:\/\/docs\.nvidia\.com\/deploy\/nvml-api\//);
    await page.keyboard.press("Escape");
    await expect(pop).toHaveCount(0);
    await expect(button).toBeFocused();
  });
});
