// T-020-015 [red] · FR-020-06 (each theory page contains the figures listed for it in spec section 7.1), FR-020-08 (a labelled marker for each feature the engine reports, its label equal to the read-out panel) and FR-020-13 (a change of any
// control of any figure changes the plotted data within 100 ms, the digest of the plotted series differing). Unit half: web/src/theory/t_020_015_figures.test.tsx.
//
// Hooks: [data-testid="figure"][data-figure][data-digest] (digest of the plotted series, SHA-256 hex), input[data-control] and select[data-control] (range controls with data-min, data-max, data-unit), [data-testid="chart-marker"][data-feature],
// [data-testid="figure-readout"] [data-feature], and the chart of T-020-010 inside (`[data-testid="chart"]`).
// Oracles: the figure table of spec section 7.1 written out below (id, topic page, number of controls, number of marked features); the 100 ms bound is measured in the page from the input event to the mutation of data-digest.
import { expect, type Locator, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const FIGURES: Array<[string, string, number, number]> = [
  ["haulage-speed-grade", "haulage", 3, 2],
  ["fee-force-depth", "loading-and-terramechanics", 3, 1],
  ["psd-kuzram-swebrec", "drill-and-blast", 3, 3],
  ["inverse-velocity", "slopes-and-monitoring", 2, 2],
  ["fos-cohesion", "slopes-and-monitoring", 2, 1],
  ["beverloo-discharge", "bulk-flow-dem-mpm", 5, 2],
  ["bond-energy", "comminution", 3, 2],
  ["plume-ground-field", "dust", 4, 2],
  ["ritter-dam-break", "tailings", 2, 2],
  ["nested-pits", "planning", 2, 2],
  ["lidar-range-dust", "rtx-sensor-physics", 3, 1],
  ["ppo-clip", "robot-learning", 2, 2],
  ["mcnemar", "vision-language-reasoning", 2, 2],
  ["c2st-auc", "sim-to-real", 1, 1],
  ["paired-ci", "sim-to-real", 3, 1],
];
const fig = (page: Page, id: string) => page.locator(`[data-testid="figure"][data-figure="${id}"]`);

test.describe("figures on their pages (FR-020-06)", () => {
  for (const [id, topic, controls, features] of FIGURES) {
    test(`FR-020-06 · /theory/${topic}/ holds the figure ${id} with ${controls} controls and ${features} marked features`, async ({
      page,
    }) => {
      await open(page, `theory/${topic}/`);
      const f = fig(page, id);
      await expect(f).toBeVisible();
      await expect(f.locator("[data-control]")).toHaveCount(controls);
      await expect(f.locator('[data-testid="chart-marker"]')).toHaveCount(features);
      await expect(f.locator('[data-testid="chart"]').first()).toBeVisible();
      await expect(f).toHaveAttribute("data-digest", /^[0-9a-f]{64}$/);
    });
  }

  test("FR-020-06 · the independent test of US-020-1: on /theory/slopes-and-monitoring/ the predicted failure time is on its marker and in the read-out", async ({
    page,
  }) => {
    await open(page, "theory/slopes-and-monitoring/");
    const f = fig(page, "inverse-velocity");
    const marker = f.locator('[data-testid="chart-marker"]').first();
    const feature = (await marker.getAttribute("data-feature")) ?? "";
    await expect(f.locator(`[data-testid="figure-readout"] [data-feature="${feature}"]`)).toHaveText(
      (await marker.textContent())?.trim() ?? "?",
    );
  });
});

test.describe("markers and read-out (FR-020-08)", () => {
  for (const [id, topic] of FIGURES) {
    test(`FR-020-08 · ${id}: every marker's label equals its read-out item, and a marker is labelled`, async ({
      page,
    }) => {
      await open(page, `theory/${topic}/`);
      const markers = fig(page, id).locator('[data-testid="chart-marker"]');
      const features = await markers.evaluateAll((els) =>
        els.map((e) => [e.getAttribute("data-feature") ?? "", e.textContent?.trim() ?? ""]),
      );
      expect(features.length).toBeGreaterThan(0);
      for (const [feature, label] of features) {
        expect((label as string).length, feature).toBeGreaterThan(0);
        await expect(
          fig(page, id).locator(`[data-testid="figure-readout"] [data-feature="${feature}"]`),
        ).toHaveText(label as string);
      }
    });
  }
});

/** Sets a control to a different valid value and returns how long the digest took to change (ms) in the page. */
async function changeAndTime(control: Locator): Promise<{ changed: boolean; ms: number }> {
  return control.evaluate(async (el) => {
    const figure = el.closest('[data-testid="figure"]') as HTMLElement;
    const before = figure.getAttribute("data-digest");
    const t0 = performance.now();
    const done = new Promise<{ changed: boolean; ms: number }>((resolve) => {
      const mo = new MutationObserver(() => {
        if (figure.getAttribute("data-digest") !== before) {
          mo.disconnect();
          resolve({ changed: true, ms: performance.now() - t0 });
        }
      });
      mo.observe(figure, { attributes: true, attributeFilter: ["data-digest"] });
      setTimeout(() => {
        mo.disconnect();
        resolve({ changed: figure.getAttribute("data-digest") !== before, ms: performance.now() - t0 });
      }, 2000);
    });
    if (el instanceof HTMLSelectElement) {
      const other = Array.from(el.options)
        .map((o) => o.value)
        .find((v) => v !== el.value) as string;
      el.value = other;
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      const input = el as HTMLInputElement;
      const min = Number(input.dataset.min);
      const max = Number(input.dataset.max);
      const current = Number(input.value);
      const target = Math.abs(current - (min + max) / 2) > 1e-9 ? (min + max) / 2 : min + (max - min) * 0.25;
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setter?.call(input, String(target));
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    }
    return done;
  });
}

test.describe("every control of every figure (FR-020-13)", () => {
  for (const [id, topic, controls] of FIGURES) {
    test(`FR-020-13 · ${id}: each of its ${controls} controls changes the digest of the plotted series within 100 ms`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await open(page, `theory/${topic}/`);
      const f = fig(page, id);
      await expect(f).toBeVisible();
      const n = await f.locator("[data-control]").count();
      expect(n).toBe(controls);
      for (let i = 0; i < n; i++) {
        await open(page, `theory/${topic}/`); // a fresh page for every control: the same starting digest
        const result = await changeAndTime(fig(page, id).locator("[data-control]").nth(i));
        expect(result.changed, `control ${i} of ${id}`).toBe(true);
        expect(result.ms, `control ${i} of ${id}`).toBeLessThanOrEqual(100);
      }
    });
  }

  test("FR-020-13 · two different settings give two different digests, and setting the first one again gives the first digest back", async ({
    page,
  }) => {
    await open(page, "theory/robot-learning/");
    const f = fig(page, "ppo-clip");
    const d0 = await f.getAttribute("data-digest");
    const input = f.locator('input[data-control="clip_epsilon"]');
    const original = await input.inputValue();
    await input.fill("0.4");
    await input.press("Enter");
    await expect(f).not.toHaveAttribute("data-digest", d0 ?? "");
    await input.fill(original);
    await input.press("Enter");
    await expect(f).toHaveAttribute("data-digest", d0 ?? "?");
  });
});
