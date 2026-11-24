// T-018-113 [red] · NFR-018-01: the first view of every case page (the Scene tab, until 2 s of network idle) transfers at most 2,000,000
// encoded bytes, with the 3D chunk and the LOD-0 tileset included; and what is not in the first view is not requested before it is
// wanted: the manifest once, the chart files of the published runs when a run's chart list opens or the Charts tab shows, the stills of
// the rendered scene when they come near the viewport.
// Oracle: the byte arithmetic of NFR-018-01 over the built files (gzip of the text types, as Pages serves them, raw bytes for the binary
// types), summed over the URLs the browser requested; the Playwright response body of a module preload is empty, so the sizes are read
// from build/client, not from the response.
import { readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const BASE = process.env.BASE_PATH ?? "/";
const TEXT = /\.(js|css|json|svg|html|txt|wasm)$/;

function encodedBytes(urlText: string): number {
  const url = new URL(urlText);
  let path = decodeURIComponent(url.pathname);
  if (!path.startsWith(BASE)) return 0;
  path = path.slice(BASE.length);
  if (path === "" || path.endsWith("/")) path += "index.html";
  const file = resolve("build/client", path);
  try {
    if (!statSync(file).isFile()) return 0;
    const body = readFileSync(file);
    return TEXT.test(file) ? gzipSync(body).length : body.length;
  } catch {
    return 0;
  }
}

async function firstView(page: Page, path: string): Promise<{ total: number; urls: string[] }> {
  const urls: string[] = [];
  let last = Date.now();
  page.on("request", (r) => {
    urls.push(r.url());
    last = Date.now();
  });
  page.on("requestfinished", () => {
    last = Date.now();
  });
  await open(page, path);
  while (Date.now() - last < 2000) await page.waitForTimeout(250);
  return { total: urls.reduce((sum, u) => sum + encodedBytes(u), 0), urls };
}

test.describe("NFR-018-01 · the first view of a case page", () => {
  for (const id of CASE_IDS) {
    test(`NFR-018-01 · /cases/${id}/ transfers at most 2,000,000 encoded bytes until 2 s of network idle`, async ({
      page,
    }) => {
      const { total } = await firstView(page, `cases/${id}/`);
      expect(total).toBeGreaterThan(100_000);
      expect(total).toBeLessThanOrEqual(2_000_000);
    });
  }

  test("NFR-018-01 · the manifest is requested once and no chart file or still before they are wanted (C1)", async ({
    page,
  }) => {
    const { urls } = await firstView(page, "cases/C1/");
    expect(urls.filter((u) => /assets\/manifest\.json/.test(u))).toHaveLength(1);
    expect(urls.filter((u) => /\/charts\/[^/]+\.json/.test(u))).toEqual([]);
    expect(urls.filter((u) => /flyover-\d+s\.webp/.test(u))).toEqual([]);
  });

  test("NFR-018-01 · the Charts tab requests the chart files of the case when it opens (C1)", async ({ page }) => {
    const urls: string[] = [];
    page.on("request", (r) => urls.push(r.url()));
    await open(page, "cases/C1/?tab=charts");
    await expect.poll(() => urls.filter((u) => /\/charts\/[^/]+\.json/.test(u)).length, { timeout: 30_000 }).toBeGreaterThan(0);
    await expect(page.getByTestId("chart-series").first()).toBeVisible({ timeout: 30_000 });
  });

  test("NFR-018-01 · scrolling the rendered scene into view requests its three stills", async ({ page }) => {
    await open(page, "cases/D2/");
    const stills = page.locator("figure[data-still] img");
    await expect(stills).toHaveCount(3);
    await stills.first().scrollIntoViewIfNeeded();
    for (let i = 0; i < 3; i++) await stills.nth(i).scrollIntoViewIfNeeded();
    await expect
      .poll(() => stills.evaluateAll((els) => els.map((e) => (e as HTMLImageElement).naturalWidth)), { timeout: 30_000 })
      .toEqual([1920, 1920, 1920]);
  });
});
