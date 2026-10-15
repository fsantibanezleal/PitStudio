// T-018-020 [red] · FR-018-01 (the Explore route renders the Bingham Canyon pit from the LOD-0 terrain tileset with its provenance chip), FR-018-07 (three.js WebGPURenderer
// with automatic WebGL 2 fallback, `?renderer=webgl` forces the WebGL 2 backend, never two renderers on one canvas), NFR-018-01 (first view <= 2 MB encoded bytes) and
// NFR-018-02 (initial JavaScript <= 200,000 bytes gzip for `/`, `/cases` and each `/cases/<id>/`).
//
// Hooks: web/e2e/support/tiles.ts (a valid minimal 3D Tiles 1.1 tileset and glTF tile, served as the LOD-0 tileset of the web manifest) and
//   [data-testid="scene-canvas"][data-renderer="webgpu" | "webgl2"]   the 3D canvas of the scene and the backend its renderer ended up on
//   [data-testid="provenance-chip"]                                    text with the source id `usgs-3dep-bingham`, "public domain (US Government work)" and the badge STATIC
//   window.__pitstudio.renderers = [{ canvasId, kind, purpose }]       one record per renderer created (purpose "scene" or "splat"), canvasId = the canvas element id
// Oracles: the EARS text; `data/sources.yaml` ids and licence names of the spec (FR-018-01); the byte arithmetic of NFR-018-01/02 (gzip of text types, as Pages serves them,
// raw bytes for binary types; the budget 2,000,000 B and 200,000 B).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { injectGpu } from "./support/gpu";
import { routeTiles } from "./support/tiles";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const BASE = process.env.BASE_PATH ?? "/";

test.describe("the pit from the LOD-0 tileset (FR-018-01)", () => {
  test("FR-018-01 · / requests the LOD-0 tileset and its glTF tile and shows the provenance chip: usgs-3dep-bingham, public domain (US Government work), STATIC", async ({
    page,
  }) => {
    const tiles = await routeTiles(page);
    await open(page, "?case=A1");
    await expect.poll(() => tiles.requested(), { timeout: 30_000 }).toContain("tileset");
    await expect.poll(() => tiles.requested(), { timeout: 30_000 }).toContain("glb");
    expect(tiles.requested().indexOf("tileset")).toBeLessThan(tiles.requested().indexOf("glb"));
    const chip = page.getByTestId("provenance-chip").first();
    await expect(chip).toContainText("usgs-3dep-bingham");
    await expect(chip).toContainText("public domain (US Government work)");
    await expect(chip).toContainText("STATIC");
    await expect(page.getByTestId("scene-canvas")).toBeVisible();
  });

  test("FR-018-01 · without a published tileset the chip does not claim one: the scene says 'Not yet run' and no tile is requested", async ({
    page,
  }) => {
    const urls: string[] = [];
    page.on("request", (r) => urls.push(r.url()));
    await open(page, "?case=A1");
    await expect(page.locator("main")).toContainText("Not yet run");
    expect(urls.filter((u) => /tileset\.json|\.glb(\?|$)/.test(u))).toEqual([]);
  });
});

test.describe("renderers (FR-018-07)", () => {
  test("FR-018-07 · headless Chromium without WebGPU falls back to WebGL 2: the scene canvas reports data-renderer webgl2 and holds a WebGL 2 context", async ({
    page,
  }) => {
    await routeTiles(page);
    await open(page, "?case=A1");
    const canvas = page.getByTestId("scene-canvas");
    await expect(canvas).toHaveAttribute("data-renderer", "webgl2", { timeout: 30_000 });
    const kind = await canvas.evaluate((c: HTMLCanvasElement) => ({
      webgl2: !!c.getContext("webgl2"),
      webgpu: c.getContext("webgpu") === null,
    }));
    expect(kind.webgl2).toBe(true);
    expect(kind.webgpu).toBe(true); // a canvas that already has a WebGL 2 context cannot get a WebGPU one: one renderer per canvas
  });

  test("FR-018-07 · ?renderer=webgl uses the WebGL 2 backend even when a WebGPU device is available", async ({
    page,
  }) => {
    await injectGpu(page, "ok");
    await routeTiles(page);
    await open(page, "?case=A1&renderer=webgl");
    await expect(page.getByTestId("scene-canvas")).toHaveAttribute("data-renderer", "webgl2", {
      timeout: 30_000,
    });
  });

  test("FR-018-07 · every renderer owns its canvas: no two renderers share a canvas id, after navigating between pages and back", async ({
    page,
  }) => {
    await routeTiles(page);
    await open(page, "?case=A1");
    await expect(page.getByTestId("scene-canvas")).toBeVisible({ timeout: 30_000 });
    await page
      .getByRole("link", { name: /Cases|Casos/ })
      .first()
      .click();
    await page
      .getByRole("link", { name: /Explore|Explorar/ })
      .first()
      .click();
    await expect(page.getByTestId("scene-canvas")).toBeVisible({ timeout: 30_000 });
    const renderers = await page.evaluate(
      () =>
        (
          window as unknown as {
            __pitstudio: { renderers: Array<{ canvasId: string; kind: string; purpose: string }> };
          }
        ).__pitstudio.renderers,
    );
    expect(renderers.length).toBeGreaterThan(0);
    const ids = renderers.map((r) => r.canvasId);
    expect(new Set(ids).size, "a canvas id appears once").toBe(ids.length);
    for (const r of renderers) expect(["webgpu", "webgl2"]).toContain(r.kind);
    const canvases = await page.locator("canvas").count();
    expect(canvases).toBeGreaterThanOrEqual(1);
  });
});

test.describe("budgets (NFR-018-01, NFR-018-02)", () => {
  test("NFR-018-01 · the first view of / transfers at most 2,000,000 encoded bytes (tileset, 3D chunk and fonts included) until 2 s of network idle", async ({
    page,
  }) => {
    await routeTiles(page);
    let total = 0;
    const pending: Array<Promise<void>> = [];
    let lastActivity = Date.now();
    page.on("request", () => {
      lastActivity = Date.now();
    });
    page.on("response", (res) => {
      lastActivity = Date.now();
      pending.push(
        (async () => {
          try {
            const body = await res.body();
            const type = res.headers()["content-type"] ?? "";
            const text =
              /text|javascript|json|svg|xml|wasm/.test(type) ||
              /\.(js|css|json|svg|html)(\?|$)/.test(res.url());
            total += text ? gzipSync(body).length : body.length;
          } catch {
            // redirects and aborted bodies carry no payload
          }
        })(),
      );
    });
    await open(page, "?case=A1");
    while (Date.now() - lastActivity < 2000) await page.waitForTimeout(250);
    await Promise.all(pending);
    expect(total).toBeGreaterThan(0);
    expect(total).toBeLessThanOrEqual(2_000_000);
  });

  for (const route of ["", "cases", ...CASE_IDS.map((id) => `cases/${id}`)]) {
    test(`NFR-018-02 · /${route}: the scripts referenced by the prerendered HTML weigh at most 200,000 bytes gzip`, () => {
      const dir = route === "" ? "" : `${route}/`;
      const html = readFileSync(resolve("build/client", dir, "index.html"), "utf8");
      const urls = new Set(
        [...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)]
          .map((m) => m[1] as string)
          .filter((u) => u.startsWith(BASE)),
      );
      expect(urls.size, "the page references scripts").toBeGreaterThan(0);
      let bytes = 0;
      for (const u of urls)
        bytes += gzipSync(readFileSync(resolve("build/client", u.slice(BASE.length)))).length;
      expect(bytes).toBeLessThanOrEqual(200_000);
    });
  }
});
