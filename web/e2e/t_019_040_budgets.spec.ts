// T-019-040 [red] · NFR-019-01 (initial JavaScript of /studio, the tool pages, /studio/runs, a run page and /studio/gpu is at most 200,000 bytes gzip each; the React Flow chunk loads after hydration), NFR-019-02 (the tool map is
// interactive, nodes focusable and clickable, within 1.5 s of load on CI Chromium) and NFR-019-03 (published telemetry per run <= 200,000 bytes, the generated studio index <= 1,000,000 bytes, the studio showcase class within
// its 25 MB budget).
//
// Initial JavaScript is measured as in T-018-020: the scripts and module preloads referenced by the prerendered HTML, gzip of each file, summed. The build under test holds the fixture runs of web/e2e/support/studio-runs.ts.
// Hooks: the map marks `performance.mark("studio:map-interactive")` when its nodes are focusable and clickable; its start time (ms since navigation start) is the readiness time. The studio index is at
// `build/client/studio/index.json` (DC-019-03), the published telemetry at `build/client/assets/runs/<run id>/telemetry.json`, the web manifest at `build/client/assets/manifest.json` (budget_class of each artefact).
// Oracles: the thresholds of the NFR rows (200,000 B; 1.5 s; 200,000 B; 1,000,000 B; 25,000,000 B with MB = 10^6 bytes) and the byte arithmetic of gzip.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { gzipSync } from "node:zlib";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { RUN_A, RUN_B, RUN_BIG } from "./support/studio-runs";

const BASE = process.env.BASE_PATH ?? "/";
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
const ROUTES = [
  "studio",
  "studio/runs",
  "studio/gpu",
  `studio/runs/${RUN_A}`,
  `studio/runs/${RUN_B}`,
  `studio/runs/${RUN_BIG}`,
  ...TOOLS.map((id) => `studio/tools/${id}`),
];

const initialJs = (route: string): number => {
  const html = readFileSync(resolve("build/client", route, "index.html"), "utf8");
  const urls = new Set(
    [...html.matchAll(/(?:src|href)="([^"]+\.js)"/g)]
      .map((m) => m[1] as string)
      .filter((u) => u.startsWith(BASE)),
  );
  expect(urls.size, `${route} references scripts`).toBeGreaterThan(0);
  let bytes = 0;
  for (const u of urls) bytes += gzipSync(readFileSync(resolve("build/client", u.slice(BASE.length)))).length;
  return bytes;
};

test.describe("initial JavaScript (NFR-019-01)", () => {
  for (const route of ROUTES) {
    test(`NFR-019-01 · /${route}/: the scripts of the prerendered HTML weigh at most 200,000 bytes gzip`, () => {
      expect(initialJs(route)).toBeLessThanOrEqual(200_000);
    });
  }

  test("NFR-019-01 · the React Flow chunk is not among the initial scripts of /studio/ and is requested after the page is up", async ({
    page,
  }) => {
    const html = readFileSync(resolve("build/client", "studio", "index.html"), "utf8");
    for (const m of html.matchAll(/(?:src|href)="([^"]+\.js)"/g)) {
      const u = m[1] as string;
      if (u.startsWith(BASE))
        expect(
          readFileSync(resolve("build/client", u.slice(BASE.length)), "utf8").includes("react-flow__"),
          u,
        ).toBe(false);
    }
    await open(page, "studio/");
    await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
  });
});

test.describe("the map is interactive soon (NFR-019-02)", () => {
  test("NFR-019-02 · the nodes are focusable and clickable within 1.5 s of navigation start on Chromium", async ({
    page,
  }) => {
    await open(page, "studio/");
    await expect(page.getByTestId("tool-map")).toHaveAttribute("data-ready", "true", { timeout: 30_000 });
    const ms = await page.evaluate(
      () => performance.getEntriesByName("studio:map-interactive", "mark").at(-1)?.startTime ?? Number.NaN,
    );
    expect(Number.isFinite(ms), "the map sets the mark 'studio:map-interactive'").toBe(true);
    expect(ms).toBeLessThanOrEqual(1500);
    const node = page.getByTestId("tool-map").locator('[data-testid="tool-node"][data-tool="warp"]');
    await node.focus();
    await expect(node).toBeFocused();
    await node.click();
    await expect(page).toHaveURL(/\/studio\/tools\/warp\/?$/);
  });
});

test.describe("studio data sizes (NFR-019-03)", () => {
  test("NFR-019-03 · the published telemetry of every run is at most 200,000 bytes", () => {
    const dir = resolve("build/client", "assets", "runs");
    expect(existsSync(dir), "the build holds the published runs").toBe(true);
    const runs = readdirSync(dir).filter((d) => statSync(resolve(dir, d)).isDirectory());
    expect(runs.sort()).toEqual([RUN_BIG, RUN_A, RUN_B].sort());
    for (const run of runs) {
      const file = resolve(dir, run, "telemetry.json");
      expect(existsSync(file), `${run} has published telemetry`).toBe(true);
      expect(statSync(file).size, run).toBeLessThanOrEqual(200_000);
    }
  });

  test("NFR-019-03 · the generated studio index is at most 1,000,000 bytes", () => {
    const file = resolve("build/client", "studio", "index.json");
    expect(existsSync(file), "the build generates studio/index.json").toBe(true);
    expect(statSync(file).size).toBeLessThanOrEqual(1_000_000);
    expect(() => JSON.parse(readFileSync(file, "utf8"))).not.toThrow();
  });

  test("NFR-019-03 · the artefacts of class studio-showcase weigh at most 25,000,000 bytes in total", () => {
    const file = resolve("build/client", "assets", "manifest.json");
    expect(existsSync(file)).toBe(true);
    const manifest = JSON.parse(readFileSync(file, "utf8")) as {
      artefacts: Array<{ budget_class: string; bytes: number }>;
    };
    const total = manifest.artefacts
      .filter((a) => a.budget_class === "studio-showcase")
      .reduce((sum, a) => sum + a.bytes, 0);
    expect(total).toBeLessThanOrEqual(25_000_000);
  });
});
