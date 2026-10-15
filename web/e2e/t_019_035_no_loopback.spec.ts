// T-019-035 [red] · FR-000-11 (E2E hostile): the studio pages make no request to a local service (127.0.0.1, localhost on another port, [::1], 0.0.0.0, any 127.x.y.z) unless the visitor presses the opt-in
// "connect to my local studio" control (FR-019-44, T-019-036). The site itself is served from localhost in these tests, so a loopback request is one whose ORIGIN differs from the page's origin.
//
// Pages visited: /studio/, every tool page, /studio/runs/ and the fixture run pages (web/e2e/support/studio-runs.ts), /studio/gpu/, plus `/`, `/cases/` and a case page, with the interactions that open things up
// (the tool map, the manifest tree, "How measured" popovers) and a wait for the network to settle. Hooks: the connect control is present on the studio pages ([data-testid="connect-port"] and
// [data-testid="connect-button"]) but not pressed here. Requests, WebSocket and EventSource opens are all observed through the browser's request and websocket events.
// Oracles: the EARS text; the loopback address families of RFC 1122 / RFC 4291 (127.0.0.0/8, ::1), "localhost" and the unspecified address 0.0.0.0.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { isLoopbackHost } from "./support/simulate";
import { RUN_A, RUN_B, RUN_BIG } from "./support/studio-runs";

const TOOLS = [
  "openusd",
  "warp",
  "newton",
  "mujoco-warp",
  "physx-ovphysx",
  "ovrtx",
  "isaac-sim-replicator",
  "isaac-lab",
  "kit-usd-composer-explorer",
  "cosmos-reason-2",
  "pytorch",
  "onnx-runtime",
  "tensorrt",
  "nvenc-ffmpeg",
  "nsight-nvml",
  "threejs-r3f-3d-tiles",
  "rapier-webgpu-pyodide",
  "cuopt",
  "physicsnemo",
  "cosmos-predict-transfer",
];

async function watch(page: Page): Promise<{ foreign: () => string[]; sockets: () => string[] }> {
  const foreign: string[] = [];
  const sockets: string[] = [];
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (!["http:", "https:", "ws:", "wss:"].includes(u.protocol)) return;
    if (
      isLoopbackHost(u.hostname) &&
      u.origin !== new URL(page.url() === "about:blank" ? r.url() : page.url()).origin
    )
      foreign.push(r.url());
  });
  page.on("websocket", (ws) => sockets.push(ws.url()));
  return { foreign: () => foreign, sockets: () => sockets };
}

test.describe("studio pages stay on their own origin (FR-000-11)", () => {
  test("FR-000-11 · /studio/ and the tool map: no loopback request, with the connect control present and not pressed", async ({
    page,
  }) => {
    const seen = await watch(page);
    await open(page, "studio/");
    await expect(page.getByTestId("connect-port")).toBeVisible();
    await expect(page.getByTestId("connect-button")).toBeVisible();
    await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
    await page.getByTestId("tool-map").locator('[data-testid="tool-node"]').first().focus();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1500);
    expect(seen.foreign()).toEqual([]);
    expect(seen.sockets()).toEqual([]);
  });

  test("FR-000-11 · all 20 tool pages", async ({ page }) => {
    test.setTimeout(180_000);
    const seen = await watch(page);
    for (const id of TOOLS) {
      await open(page, `studio/tools/${id}/`);
      await page.waitForLoadState("networkidle");
    }
    await page.waitForTimeout(1000);
    expect(seen.foreign()).toEqual([]);
    expect(seen.sockets()).toEqual([]);
  });

  test("FR-000-11 · the ledger and the run pages, with the manifest tree opened", async ({ page }) => {
    const seen = await watch(page);
    await open(page, "studio/runs/");
    for (const id of [RUN_A, RUN_B, RUN_BIG]) {
      await open(page, `studio/runs/${id}/`);
      await page.getByTestId("manifest-tree").locator('[data-path="/recipe"]').focus();
      await page.keyboard.press("ArrowRight");
      await page.waitForLoadState("networkidle");
    }
    await page.waitForTimeout(1000);
    expect(seen.foreign()).toEqual([]);
    expect(seen.sockets()).toEqual([]);
  });

  test("FR-000-11 · the GPU page, with a 'How measured' popover opened", async ({ page }) => {
    const seen = await watch(page);
    await open(page, "studio/gpu/");
    await page.getByTestId("how-measured").first().click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    expect(seen.foreign()).toEqual([]);
    expect(seen.sockets()).toEqual([]);
  });

  test("FR-000-11 · the home page and the case pages do not contact a local service either", async ({
    page,
  }) => {
    const seen = await watch(page);
    for (const route of ["", "cases/", "cases/A1/", "cases/C2/?tab=simulate"]) {
      await open(page, route);
      await page.waitForLoadState("networkidle");
    }
    expect(seen.foreign()).toEqual([]);
    expect(seen.sockets()).toEqual([]);
  });

  test("FR-000-11 · a page loaded with a local-service address in its query string still contacts nothing local", async ({
    page,
  }) => {
    const seen = await watch(page);
    await open(
      page,
      "studio/?console=http://127.0.0.1:8765&port=8765&host=localhost:8765&url=http://localhost:8765/health",
    );
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);
    expect(seen.foreign()).toEqual([]);
  });

  test("FR-000-11 · the guard sees what it is meant to see: a request to a loopback address on another port is recorded (self-check)", async ({
    page,
  }) => {
    const seen = await watch(page);
    await open(page, "studio/");
    await page.evaluate(() => fetch("http://127.0.0.1:9/never", { mode: "no-cors" }).catch(() => undefined));
    await page.waitForTimeout(300);
    expect(seen.foreign().some((u) => u.includes("127.0.0.1:9"))).toBe(true);
  });
});
