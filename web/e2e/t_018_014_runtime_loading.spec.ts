// T-018-014 [red] · FR-018-33 (runtimes load lazily, after a user action), FR-018-34 / FR-000-11 (same origin only, no loopback),
// FR-018-35 (no cross-origin isolation, no SharedArrayBuffer, single-threaded ORT) and FR-018-37 (progress and Abort).
//
// Hooks: see web/e2e/support/simulate.ts (engine panels, runtime progress and Abort, "Run in Python", window.__pitstudio).
// Runtime files are requested under `<base>assets/runtimes/<ort|rapier|pyodide>/`; the runtime files and their byte sizes are
// listed in the web manifest (`assets/manifest.json`, artefacts with budget_class "runtimes"), which is where the progress
// total comes from (FR-018-37: "bytes received over the manifest size").
// Oracles: the EARS text; the runtime-per-case table of spec 018 section 7.1 (ORT-web: A1 policies, A2 il1-twin, A3 il2-twin and
// gns, B2 detector, C1 forecasters, C2 fno, D1 unet, D2 meta-model; Rapier: B1 traffic; Pyodide: "Run in Python" on analytical
// engines, e.g. C1 geotech).
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { enginePanel, isLoopbackHost, openSimulate, RUNTIME_URL, recordRequests } from "./support/simulate";

const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const ROUTES = ["", "cases/", "studio/", "theory/", "methods/", "results/", "knowledge/"];

test.describe("lazy runtime loading (FR-018-33)", () => {
  test("FR-018-33 · no ORT-web, Rapier or Pyodide file, model or wheel is requested while browsing every route and case page", async ({
    page,
  }) => {
    const rec = recordRequests(page);
    for (const route of ROUTES) await open(page, `${route}?tier=t2`);
    for (const id of CASE_IDS) await open(page, `cases/${id}/?tier=t2`);
    await page.waitForLoadState("networkidle");
    expect(rec.runtime()).toEqual([]);
    expect(rec.urls().filter((u) => /\.(onnx|whl)(\?|$)/.test(u))).toEqual([]);
  });

  test("FR-018-33 · opening the Simulate tab of C1 (forecasters, ORT-web) requests ORT-web files, and nothing of Pyodide or Rapier", async ({
    page,
  }) => {
    const rec = recordRequests(page);
    await open(page, "cases/C1/?tier=t2");
    expect(rec.runtime()).toEqual([]);
    await page.getByRole("tab", { name: /Simulate/ }).click();
    await expect
      .poll(() => rec.runtime().filter((u) => /\/ort\//.test(u)).length, { timeout: 30_000 })
      .toBeGreaterThan(0);
    expect(rec.runtime().filter((u) => /\/(pyodide|rapier)\//.test(u))).toEqual([]);
  });

  test("FR-018-33 · opening the Simulate tab of B1 (traffic, Rapier) requests the Rapier file", async ({
    page,
  }) => {
    const rec = recordRequests(page);
    await open(page, "cases/B1/?tier=t2");
    expect(rec.runtime()).toEqual([]);
    await page.getByRole("tab", { name: /Simulate/ }).click();
    await expect
      .poll(() => rec.runtime().filter((u) => /\/rapier\//.test(u)).length, { timeout: 30_000 })
      .toBeGreaterThan(0);
  });

  test("FR-018-33 · Pyodide, numpy, PyYAML and the minephys wheel load only after 'Run in Python' is pressed", async ({
    page,
  }) => {
    const rec = recordRequests(page);
    await openSimulate(page, "C1", "&tier=t2");
    await expect(enginePanel(page, "geotech")).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(rec.runtime().filter((u) => /\/pyodide\//.test(u))).toEqual([]);
    await enginePanel(page, "geotech").getByRole("button", { name: "Run in Python" }).click();
    await expect
      .poll(() => rec.runtime().filter((u) => /\/pyodide\//.test(u)).length, { timeout: 60_000 })
      .toBeGreaterThan(0);
    for (const name of [/numpy/i, /pyyaml/i, /minephys/i]) {
      await expect
        .poll(() => rec.urls().filter((u) => /\.whl(\?|$)/.test(u) && name.test(u)).length, {
          timeout: 60_000,
        })
        .toBeGreaterThan(0);
    }
  });
});

test.describe("same origin only (FR-018-34, FR-000-11)", () => {
  test("FR-018-34 · a full session makes zero requests to other origins and zero to loopback addresses other than the app", async ({
    page,
    context,
    baseURL,
  }) => {
    const app = new URL(baseURL as string);
    const all: string[] = [];
    context.on("request", (r) => all.push(r.url()));
    for (const route of ROUTES) await open(page, route);
    for (const id of CASE_IDS) {
      for (const tab of ["scene", "replay", "charts", "context"]) await open(page, `cases/${id}/?tab=${tab}`);
      await openSimulate(page, id, "&tier=t2");
      await page.waitForTimeout(500);
    }
    await openSimulate(page, "C1", "&tier=t2");
    await enginePanel(page, "geotech").getByRole("button", { name: "Run in Python" }).click();
    await page.waitForTimeout(3000);
    expect(all.length).toBeGreaterThan(20);
    const foreign: string[] = [];
    for (const raw of all) {
      const url = new URL(raw);
      if (url.protocol === "data:" || url.protocol === "blob:" || url.protocol === "about:") continue;
      if (url.origin !== app.origin) foreign.push(raw);
    }
    expect(foreign).toEqual([]);
    const loopback = all.filter((raw) => {
      const url = new URL(raw);
      return isLoopbackHost(url.hostname) && url.origin !== app.origin;
    });
    expect(loopback).toEqual([]);
  });

  test("FR-018-34 · runtime and model files that are requested come from the app origin", async ({
    page,
    baseURL,
  }) => {
    const app = new URL(baseURL as string);
    const rec = recordRequests(page);
    await openSimulate(page, "C1", "&tier=t2");
    await expect.poll(() => rec.runtime().length, { timeout: 30_000 }).toBeGreaterThan(0);
    for (const raw of rec.runtime()) expect(new URL(raw).origin).toBe(app.origin);
    expect(RUNTIME_URL.test(rec.runtime()[0] as string)).toBe(true);
  });
});

test.describe("no cross-origin isolation, no SharedArrayBuffer (FR-018-35)", () => {
  test("FR-018-35 · with engines running the page is not cross-origin isolated, has no SharedArrayBuffer and ORT runs on one thread", async ({
    page,
  }) => {
    const res = await page.goto("cases/C1/?tab=simulate&tier=t2");
    const headers = res?.headers() ?? {};
    expect(headers["cross-origin-opener-policy"]).toBeUndefined();
    expect(headers["cross-origin-embedder-policy"]).toBeUndefined();
    await open(page, "cases/C1/?tab=simulate&tier=t2");
    await expect(enginePanel(page, "forecasters")).toBeVisible();
    await expect
      .poll(() => enginePanel(page, "forecasters").getAttribute("data-state"), { timeout: 60_000 })
      .toMatch(/done|replay|error/);
    const info = await page.evaluate(() => ({
      isolated: crossOriginIsolated,
      sab: typeof SharedArrayBuffer,
      threads: (window as unknown as { __pitstudio?: { runtime?: { ort?: { numThreads?: number } } } })
        .__pitstudio?.runtime?.ort?.numThreads,
    }));
    expect(info.isolated).toBe(false);
    expect(info.sab).toBe("undefined");
    expect(info.threads).toBe(1);
  });
});

test.describe("progress and Abort (FR-018-37)", () => {
  test("FR-018-37 · a slow runtime download shows bytes received over the manifest size, and Abort stops it within 500 ms and restores the view", async ({
    page,
    context,
    baseURL,
  }) => {
    // The sizes come from the manifest of the build under test.
    const manifestUrl = new URL("assets/manifest.json", baseURL as string).toString();
    const manifestRes = await page.request.get(manifestUrl);
    expect(manifestRes.status(), "the build serves assets/manifest.json").toBe(200);
    const manifest = (await manifestRes.json()) as {
      artefacts: Array<{ path: string; bytes: number; budget_class: string }>;
    };
    const ortFiles = manifest.artefacts.filter(
      (a) => a.budget_class === "runtimes" && /\/ort\/|^runtimes\/ort/.test(a.path),
    );
    expect(
      ortFiles.length,
      "the web manifest lists the ORT-web runtime files (budget class runtimes)",
    ).toBeGreaterThan(0);
    const sizes = new Set(ortFiles.map((f) => f.bytes));

    const failed: string[] = [];
    page.on("requestfailed", (r) => {
      if (RUNTIME_URL.test(r.url())) failed.push(r.url());
    });
    await open(page, "cases/C1/?tier=t2");
    const cdp = await context.newCDPSession(page);
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 20,
      downloadThroughput: 150 * 1024,
      uploadThroughput: 150 * 1024,
    });
    await page.getByRole("tab", { name: /Simulate/ }).click();
    const progress = page.getByTestId("runtime-progress").first();
    await expect(progress).toBeVisible({ timeout: 30_000 });
    await expect(progress).toHaveAttribute("role", "progressbar");
    const max = Number(await progress.getAttribute("aria-valuemax"));
    expect(sizes.has(max)).toBe(true);
    const first = Number(await progress.getAttribute("aria-valuenow"));
    await page.waitForTimeout(1500);
    const second = Number(await progress.getAttribute("aria-valuenow"));
    expect(second).toBeGreaterThan(first);
    expect(second).toBeLessThanOrEqual(max);
    await expect(progress).toContainText(/\d/);

    const t0 = Date.now();
    await page.getByTestId("runtime-abort").first().click();
    await expect(progress).toBeHidden({ timeout: 500 });
    expect(Date.now() - t0).toBeLessThan(1500); // click round trip included; the visible stop is bounded by the 500 ms wait above
    await expect.poll(() => failed.length, { timeout: 500 }).toBeGreaterThan(0);
    await expect(enginePanel(page, "forecasters")).toHaveAttribute("data-state", "idle");
    await expect(page.getByTestId("tier-badge")).toBeVisible();
  });
});
