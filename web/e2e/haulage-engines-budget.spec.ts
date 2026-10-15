// T-007-023 · budgets of the haulage engines in the built app: NFR-007-01, NFR-007-02 (and NFR-000-01 for the initial JS).
//
// Spec: specs/007-haulage-dispatch/spec.md NFR-007-01 (one 8 h shift, about 10^4 events and at most 40 trucks, in the TypeScript twin on tier T2 (WASM) takes at most 1 s, `lane_gate.run_s_max`;
// otherwise the lane is precompute, FR-000-15; measured by Playwright timing on the reference machine) and NFR-007-02 (the TypeScript analytical ports (M1, M6 energy, A*, LP) are at most 50 KB gzip
// together; all haulage engines are lazy-loaded and none is in the initial JS, NFR-000-01; measured by the build report); plan.md (the engines run in web workers).
//
// Oracle: the production build on disk (`build/client`, `pnpm build`): file names and gzip sizes by `node:zlib` (reference compressor); the network log of Playwright for what the start of the A1
// page loads; the stopwatch of the test for the shift.
//
// Contract with the build and the page (spec 018 hosts the case page): (1) Vite names every chunk of `web/src/engines/<name>/` `assets/engine-<name>-<hash>.js` (names: random, des, lp, haulage,
// routing); (2) the A1 case page `cases/a1/` offers a button named "Run shift" (accessible name) that runs the default 8 h shift in the twin and shows the result in the element with
// `data-testid="a1-kpi-tph"` (text: the t/h figure), and any element of the page carries `data-running="true"` while a run is in progress; (3) the tier is T2 (WASM) in a headless Chromium. Build first: `BASE_PATH=/PitStudio/ pnpm build`.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";
import { expect, test } from "@playwright/test";

const ASSETS = join("build", "client", "assets");
const ENGINE = /^engine-(random|des|lp|haulage|routing)-.+\.js$/;
const PORTS = new Set(["haulage", "lp", "routing"]); // M1 and M6 energy (haulage), the LP (lp), A* (routing)

function engineChunks(): { name: string; engine: string; gz: number }[] {
  if (!existsSync(ASSETS)) return [];
  return readdirSync(ASSETS)
    .map((f) => ({ f, m: ENGINE.exec(f) }))
    .filter((x): x is { f: string; m: RegExpExecArray } => x.m !== null)
    .map(({ f, m }) => ({
      name: f,
      engine: m[1] as string,
      gz: gzipSync(readFileSync(join(ASSETS, f))).length,
    }));
}

test("NFR-007-02 · the build has one lazy chunk per haulage engine", () => {
  const engines = new Set(engineChunks().map((c) => c.engine));
  for (const e of ["random", "des", "lp", "haulage", "routing"])
    expect(engines.has(e), `no engine-${e}-*.js chunk in ${ASSETS}`).toBe(true);
});

test("NFR-007-02 · the analytical ports (M1, M6 energy, A*, LP) are at most 50 KB gzip together", () => {
  const ports = engineChunks().filter((c) => PORTS.has(c.engine));
  expect(ports.length).toBeGreaterThan(0);
  const total = ports.reduce((s, c) => s + c.gz, 0);
  expect(total, JSON.stringify(ports)).toBeLessThanOrEqual(50 * 1024);
});

test("NFR-007-02 · no haulage engine is in the initial JS of the A1 page", async ({ page }) => {
  const loaded: string[] = [];
  page.on("response", (r) => {
    const u = new URL(r.url()).pathname;
    if (u.endsWith(".js")) loaded.push(u.split("/").pop() as string);
  });
  await page.goto("cases/a1/", { waitUntil: "networkidle" });
  expect(loaded.length).toBeGreaterThan(0);
  expect(loaded.filter((f) => ENGINE.test(f))).toEqual([]);
});

test("NFR-007-01 · an 8 h shift in the twin takes at most one second after the engines are loaded", async ({
  page,
}) => {
  const loaded: string[] = [];
  page.on("response", (r) => {
    const u = new URL(r.url()).pathname;
    if (u.endsWith(".js")) loaded.push(u.split("/").pop() as string);
  });
  await page.goto("cases/a1/", { waitUntil: "networkidle" });
  const run = page.getByRole("button", { name: "Run shift" });
  const out = page.getByTestId("a1-kpi-tph");
  await run.click();
  await expect(out).toHaveText(/\d/, { timeout: 30_000 }); // the first run loads the engines (lazy chunks arrive now, not before)
  expect(loaded.some((f) => /^engine-des-/.test(f))).toBe(true);
  const first = await out.textContent();
  await run.click();
  const t0 = Date.now();
  await expect(out).not.toHaveText("", { timeout: 5_000 });
  await page.waitForFunction(() => !document.querySelector("[data-running='true']"), undefined, {
    timeout: 5_000,
  });
  const ms = Date.now() - t0;
  expect(ms).toBeLessThanOrEqual(1000);
  expect(await out.textContent()).toBe(first); // the same seed gives the same shift
});
