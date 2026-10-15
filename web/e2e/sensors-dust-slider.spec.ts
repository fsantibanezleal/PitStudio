// T-013-033 · NFR-013-01 · NFR-013-02 · FR-013-38 · FR-013-39 · the live dust slider in the browser: timing, asset and worker budgets, fallback.
//
// Oracle: the thresholds of the spec (one level change on a baked frame of at most 150,000 returns in at most 16 ms; baked slider asset at most 10 MB per frame;
// dust worker JavaScript at most 50 KB gzip) measured on the served production build (Playwright, the reference browser); the clean-frame fallback text of FR-013-39.
//
// Expected page contract (case B1, tab "Simulate (live)": `/cases/B1/?tab=simulate`):
//   - a region named "Dust slider" holding: a slider (role "slider", min 0, max 40, step 1, the baked level), the badge text "LIVE", the label text
//     "own Beer–Lambert dust model", and a live status region (role "status") whose text matches "kept <n> of <m>" with n the kept clean returns at the current level;
//   - every level change runs `attenuate` in the Web Worker and records `performance.measure("dust-slider-apply", ...)` around the apply (request to updated frame);
//   - the baked asset is requested as `.../dust-slider-<frame>.json` (header) and `.../dust-slider-<frame>.bin` (payload); the worker script URL contains "dust";
//   - when the asset fails its checks the region shows "dust model unavailable — clean frame shown" and the clean frame stays.

import { gzipSync } from "node:zlib";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const PAGE = "cases/B1/?tab=simulate";
const LIMIT_BYTES = 10_000_000;
const WORKER_GZIP_BYTES = 50 * 1024;

test.describe("dust slider (live)", () => {
  test("FR-013-38 · the panel shows the LIVE badge and the model label and moving the slider re-attenuates the frame", async ({
    page,
  }) => {
    await open(page, PAGE);
    const panel = page.getByRole("region", { name: "Dust slider" });
    await expect(panel).toBeVisible();
    await expect(panel.getByText("LIVE", { exact: true })).toBeVisible();
    await expect(panel.getByText("own Beer–Lambert dust model")).toBeVisible();
    const slider = panel.getByRole("slider");
    await expect(slider).toHaveAttribute("min", "0");
    await expect(slider).toHaveAttribute("max", "40");
    const status = panel.getByRole("status");
    const kept = async (): Promise<number> => {
      const m = /kept\s+(\d+)\s+of\s+(\d+)/i.exec((await status.textContent()) ?? "");
      expect(m, "the status region reads 'kept N of M'").not.toBeNull();
      return Number(m?.[1]);
    };
    await slider.focus();
    await page.keyboard.press("Home");
    const clean = await kept();
    await page.keyboard.press("End");
    await expect.poll(kept).toBeLessThan(clean); // at T1 = 0.02 dust has removed returns
    await page.keyboard.press("Home");
    await expect.poll(kept).toBe(clean); // and level 0 restores the clean frame
  });

  test("NFR-013-01 · one level change takes at most 16 ms on a baked frame of at most 150,000 returns", async ({
    page,
  }) => {
    await open(page, PAGE);
    const panel = page.getByRole("region", { name: "Dust slider" });
    await panel.getByRole("slider").focus();
    await page.keyboard.press("Home");
    for (let i = 0; i < 30; i++) await page.keyboard.press("ArrowRight");
    for (let i = 0; i < 10; i++) await page.keyboard.press("ArrowLeft");
    await expect
      .poll(() => page.evaluate(() => performance.getEntriesByName("dust-slider-apply").length), {
        timeout: 15_000,
      })
      .toBeGreaterThanOrEqual(30);
    const durations = await page.evaluate(() =>
      performance.getEntriesByName("dust-slider-apply").map((e) => e.duration),
    );
    const sorted = [...durations].sort((a, b) => a - b);
    const p95 = sorted[Math.min(sorted.length - 1, Math.floor(0.95 * sorted.length))] as number;
    expect(p95, `p95 of ${durations.length} level changes (ms)`).toBeLessThanOrEqual(16);
  });

  test("NFR-013-02 · the baked slider asset is at most 10 MB per frame and the dust worker at most 50 KB gzip", async ({
    page,
  }) => {
    const sizes: { url: string; bytes: number; gzip: number }[] = [];
    page.on("response", async (res) => {
      const url = res.url();
      if (!/dust/i.test(url) || !res.ok()) return;
      const body = await res.body().catch(() => Buffer.alloc(0));
      sizes.push({ url, bytes: body.length, gzip: gzipSync(body).length });
    });
    await open(page, PAGE);
    await page.getByRole("region", { name: "Dust slider" }).waitFor();
    await page.waitForLoadState("networkidle");
    const assets = sizes.filter((s) => /dust-slider-[^/]*\.(json|bin)$/.test(s.url));
    const workers = sizes.filter((s) => /\.js(\?|$)/.test(s.url));
    expect(assets.length, "the page requested the baked slider header and payload").toBeGreaterThanOrEqual(2);
    for (const a of assets) expect(a.bytes, a.url).toBeLessThanOrEqual(LIMIT_BYTES);
    expect(workers.length, "the page requested a dust worker script").toBeGreaterThanOrEqual(1);
    for (const w of workers) expect(w.gzip, w.url).toBeLessThanOrEqual(WORKER_GZIP_BYTES);
  });

  test("FR-013-39 · a corrupted baked asset leaves the clean frame and shows the unavailable message", async ({
    page,
  }) => {
    await page.route(/dust-slider-[^/]*\.bin$/, (route) =>
      route.fulfill({ status: 200, contentType: "application/octet-stream", body: "corrupted" }),
    );
    await open(page, PAGE);
    const panel = page.getByRole("region", { name: "Dust slider" });
    await expect(panel.getByText("dust model unavailable — clean frame shown")).toBeVisible();
    await expect(panel.getByRole("slider")).toBeDisabled();
    await expect(page.locator("main")).toBeVisible(); // the page did not crash
  });
});
