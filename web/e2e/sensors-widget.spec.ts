// T-013-034 · FR-013-40 · FR-013-41 · FR-013-24 · NFR-013-03 · the sensor-comparison widget, the local-only card, the radar-immunity label and the "not yet run" states.
//
// Oracle: the literal texts of the spec ("REPLAY", "measured locally, not published (licence)", "radar dust immunity assumed (UNVERIFIED)", "not yet run") and the
// asset budget of NFR-013-03 (each web sensor shard at most 10 MB), read from the served production build with Playwright.
//
// Expected page contract:
//   - case B1, tab "Studio replay" (`/cases/B1/?tab=studio-replay`): a region named "Sensor comparison" with four views named "RGB", "Semantic", "Lidar" and "Radar"
//     (role "tab" or "region"), each carrying the badge text "REPLAY" and a provenance line naming the producing tool, the run id and the 7-hex commit; the Radar view
//     has a diverging colour-map legend (role "img", name containing "diverging" and "0 m/s") whose centre is 0 m/s; a card with the text
//     "measured locally, not published (licence)" and no rendering-performance number anywhere in the widget;
//   - case B1, tab "Charts" (`/cases/B1/?tab=charts`): the lidar-versus-radar chart region (role "region", name "Lidar versus radar") shows the label
//     "radar dust immunity assumed (UNVERIFIED)";
//   - without any published S1 to S4a artefact (the web index `assets/manifest.json` has no sensor artefact) the sensor panels of cases B1, B2 and E2 and the
//     tool page `/studio/tools/ovrtx/` show "not yet run" (any case) and no `<img>` placeholder inside the sensor panel.

import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const SHARD_LIMIT = 10_000_000;

const emptyIndex = {
  kind: "web-index",
  schema_version: "1.0",
  generated: "2026-10-11",
  git_sha: "0000000",
  runs: [],
  artefacts: [],
};

test.describe("sensor comparison widget", () => {
  test("FR-013-40 · shows RGB, semantic, lidar and radar views with REPLAY badges and provenance", async ({
    page,
  }) => {
    await open(page, "cases/B1/?tab=studio-replay");
    const widget = page.getByRole("region", { name: "Sensor comparison" });
    await expect(widget).toBeVisible();
    for (const view of ["RGB", "Semantic", "Lidar", "Radar"]) {
      const v = widget.getByRole("tab", { name: view }).or(widget.getByRole("region", { name: view }));
      await expect(v.first(), view).toBeVisible();
    }
    for (const view of ["RGB", "Semantic", "Lidar", "Radar"]) {
      const tab = widget.getByRole("tab", { name: view });
      if (await tab.count()) await tab.click();
      const panel = widget
        .getByRole("tabpanel")
        .or(widget.getByRole("region", { name: view }))
        .first();
      await expect(panel.getByText("REPLAY", { exact: true }), `${view}: REPLAY badge`).toBeVisible();
      await expect(panel.getByText(/ovrtx|isaac/i), `${view}: producing tool`).toBeVisible();
      await expect(panel.getByText(/\b[0-9a-f]{7}\b/), `${view}: 7-hex commit`).toBeVisible();
      await expect(panel.getByText(/\b\d{8}T\d{6}Z-[a-z0-9-]+\b/), `${view}: run id`).toBeVisible();
    }
  });

  test("FR-013-40 · the radar view has a diverging Doppler colour map centred on 0 m/s", async ({ page }) => {
    await open(page, "cases/B1/?tab=studio-replay");
    const widget = page.getByRole("region", { name: "Sensor comparison" });
    const radar = widget.getByRole("tab", { name: "Radar" });
    if (await radar.count()) await radar.click();
    const legend = widget.getByRole("img", { name: /diverging/i });
    await expect(legend).toBeVisible();
    await expect(legend).toHaveAccessibleName(/0\s*m\/s/);
    await expect(widget.getByText("0 m/s").first()).toBeVisible();
  });

  test("FR-013-40 · rendering performance appears only as the local-only card, never as a number", async ({
    page,
  }) => {
    await open(page, "cases/B1/?tab=studio-replay");
    const widget = page.getByRole("region", { name: "Sensor comparison" });
    await expect(widget.getByText("measured locally, not published (licence)")).toBeVisible();
    const text = (await widget.innerText()).toLowerCase();
    expect(text).not.toMatch(
      /\b\d+(\.\d+)?\s*(fps|frames\/s|ms\s*\/\s*frame|rays\/s|rays per second|gb\/s)\b/,
    );
    expect(text).not.toMatch(/\b(frame time|throughput|latency)\b\s*[:=]?\s*\d/);
  });

  test("FR-013-24 · the lidar-versus-radar chart carries the radar-immunity label", async ({ page }) => {
    await open(page, "cases/B1/?tab=charts");
    const chart = page.getByRole("region", { name: "Lidar versus radar" });
    await expect(chart).toBeVisible();
    await expect(chart.getByText("radar dust immunity assumed (UNVERIFIED)")).toBeVisible();
  });

  test("NFR-013-03 · every web sensor shard the page loads is at most 10 MB", async ({ page }) => {
    const sizes: { url: string; bytes: number }[] = [];
    page.on("response", async (res) => {
      if (!/sensors\/.*\.(bin|json)(\?|$)/.test(res.url()) || !res.ok()) return;
      sizes.push({ url: res.url(), bytes: (await res.body().catch(() => Buffer.alloc(0))).length });
    });
    await open(page, "cases/B1/?tab=studio-replay");
    await page.waitForLoadState("networkidle");
    expect(sizes.length, "the page loaded at least one sensor shard").toBeGreaterThanOrEqual(1);
    for (const s of sizes) expect(s.bytes, s.url).toBeLessThanOrEqual(SHARD_LIMIT);
  });
});

test.describe("honesty states without published sensor artefacts (FR-000-07)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/assets\/manifest\.json(\?|$)/, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(emptyIndex) }),
    );
  });

  for (const id of ["B1", "B2", "E2"]) {
    test(`FR-013-41 · the ${id} sensor panel says "not yet run" and shows no placeholder image`, async ({
      page,
    }) => {
      await open(page, `cases/${id}/?tab=studio-replay`);
      const panel = page.getByRole("region", { name: /sensor/i }).first();
      await expect(panel.getByText(/not yet run/i)).toBeVisible();
      await expect(panel.locator("img")).toHaveCount(0);
      await expect(panel.locator("canvas")).toHaveCount(0);
    });
  }

  test("FR-013-41 · the ovrtx tool page says 'not yet run' and shows no placeholder image", async ({
    page,
  }) => {
    await open(page, "studio/tools/ovrtx/");
    await expect(page.getByText(/not yet run/i).first()).toBeVisible();
    await expect(page.getByRole("region", { name: /artefacts/i }).locator("img")).toHaveCount(0);
  });
});
