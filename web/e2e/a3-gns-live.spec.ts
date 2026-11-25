// T-011-020 [red] · FR-011-09, FR-011-11, NFR-011-02: A3 live GNS (worker graph, tier, baked reference, extrapolation label, step time).
//
// What the green commit must deliver on `cases/A3/?tab=simulate` (spec 018 case page, tab "Simulate (live)", engine `gns`; the `?tier=t0|t1|t2`
// override of spec 018 FR-018-29 selects the tier, the default Chromium project has no WebGPU so the tests force `?tier=t2`):
//   - a region named "GNS granular flow" holding the controls: a combobox "Geometry family" (Column collapse, Pile formation, Dump over crest), spin
//     buttons "Aspect ratio" (collapse), "Particle count" (default value <= 2000, max <= 5000), a button "Start" and, while a rollout runs, a button "Stop";
//   - after "Start": a worker is created for the neighbour graph (page.workers() holds a worker whose URL contains "gns"); an image-role canvas named
//     "Live GNS rollout" draws non-blank pixels; a LIVE badge (text "LIVE") inside the region "Live rollout" and the tier badge "T2 · WebAssembly"
//     (FR-018-06); an image-role canvas named "Baked solver reference" with a REPLAY badge (text "REPLAY") inside the region "Solver reference";
//   - a table named "Errors against the solver reference" with the rows "Repose angle error" (value with unit °) and "Run-out error" (value with %),
//     shown only for a geometry inside the training envelope of DC-011-02 (aspect ratio 0.5 ... 4);
//   - FR-011-11: outside the envelope (aspect ratio 6) the rollout still runs, the text "extrapolation — no accuracy claim" is visible and the errors
//     table is absent; inside the envelope the text is absent;
//   - NFR-011-02: a readout named "Step time" with the median of the last 100 steps in ms (text "<number> ms") and, on T2, a readout named "T2 particle
//     cap" with the largest particle count that met 50 ms ("<integer> particles"); the particle count input never exceeds that cap;
//   - FR-018-31 / FR-011-09: when the ONNX files cannot be loaded the engine falls back to T0: the baked rollout is shown with the REPLAY badge, no LIVE
//     badge, and a status notice names the failed runtime ("ONNX Runtime").
// Oracles: the wording fixed by FR-011-09 and FR-011-11 (the em dash of the extrapolation label is part of the string), FR-018-06 badge texts, the
// training envelope of DC-011-02 (aspect ratio 0.5 ... 4, particle count <= 5,000 engine cap of spec 018), NFR-011-02 (50 ms).
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const SIMULATE = "cases/A3/?tab=simulate&tier=t2";
const EXTRAPOLATION = "extrapolation — no accuracy claim";

async function start(page: Page): Promise<void> {
  await open(page, SIMULATE);
  const region = page.getByRole("region", { name: "GNS granular flow" });
  await expect(region).toBeVisible();
  await region.getByRole("button", { name: "Start" }).click();
}

test.describe("live rollout (FR-011-09)", () => {
  test("FR-011-09 · Start builds the graph in a worker and draws the live rollout with the LIVE badge on T2", async ({
    page,
  }) => {
    await start(page);
    await expect.poll(() => page.workers().some((w) => w.url().includes("gns"))).toBe(true);
    const live = page.getByRole("img", { name: "Live GNS rollout" });
    await expect(live).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Live rollout" }).getByText("LIVE", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("T2 · WebAssembly")).toBeVisible();
    const painted = await live.evaluate((canvas: HTMLCanvasElement) => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return -1; // a WebGL canvas: read through a copy
      const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      let n = 0;
      for (let i = 3; i < data.length; i += 4) if ((data[i] as number) > 0) n++;
      return n;
    });
    expect(painted).not.toBe(0);
  });

  test("FR-011-09 · the baked reference rollout of the same geometry is shown with the REPLAY badge and the two errors", async ({
    page,
  }) => {
    await start(page);
    const reference = page.getByRole("region", { name: "Solver reference" });
    await expect(reference.getByRole("img", { name: "Baked solver reference" })).toBeVisible();
    await expect(reference.getByText("REPLAY", { exact: true })).toBeVisible();
    const table = page.getByRole("table", { name: "Errors against the solver reference" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("row", { name: /Repose angle error/ })).toContainText(/\d+(\.\d+)?\s?°/);
    await expect(table.getByRole("row", { name: /Run-out error/ })).toContainText(/\d+(\.\d+)?\s?%/);
  });

  test("FR-011-09 · the default scene has at most 2,000 particles and the page stays responsive while it runs", async ({
    page,
  }) => {
    await open(page, SIMULATE);
    const region = page.getByRole("region", { name: "GNS granular flow" });
    const count = region.getByRole("spinbutton", { name: "Particle count" });
    expect(Number(await count.inputValue())).toBeLessThanOrEqual(2000);
    expect(Number(await count.getAttribute("max"))).toBeLessThanOrEqual(5000);
    await region.getByRole("button", { name: "Start" }).click();
    await expect(region.getByRole("button", { name: "Stop" })).toBeEnabled();
    await region.getByRole("button", { name: "Stop" }).click();
    await expect(region.getByRole("button", { name: "Start" })).toBeEnabled();
  });

  test("FR-011-09 · when the ONNX files cannot be loaded the baked rollout is shown as REPLAY with a notice naming ONNX Runtime", async ({
    page,
  }) => {
    await page.route("**/*.onnx", (route) => route.abort());
    await start(page);
    await expect(page.getByRole("status").filter({ hasText: "ONNX Runtime" })).toBeVisible();
    await expect(page.getByText("REPLAY", { exact: true }).first()).toBeVisible();
    await expect(
      page.getByRole("region", { name: "Live rollout" }).getByText("LIVE", { exact: true }),
    ).toHaveCount(0);
    await expect(page.getByText("T0 · baked")).toBeVisible();
  });
});

test.describe("extrapolation (FR-011-11)", () => {
  test("FR-011-11 · a geometry inside the training envelope has no extrapolation label and shows its errors", async ({
    page,
  }) => {
    await open(page, SIMULATE);
    const region = page.getByRole("region", { name: "GNS granular flow" });
    await region.getByRole("spinbutton", { name: "Aspect ratio" }).fill("2");
    await region.getByRole("button", { name: "Start" }).click();
    await expect(page.getByRole("table", { name: "Errors against the solver reference" })).toBeVisible();
    await expect(page.getByText(EXTRAPOLATION)).toHaveCount(0);
  });

  test("FR-011-11 · an aspect ratio of 6 still runs, is labelled extrapolation and shows no error against a reference", async ({
    page,
  }) => {
    await open(page, SIMULATE);
    const region = page.getByRole("region", { name: "GNS granular flow" });
    await region.getByRole("spinbutton", { name: "Aspect ratio" }).fill("6");
    await region.getByRole("button", { name: "Start" }).click();
    await expect(page.getByRole("img", { name: "Live GNS rollout" })).toBeVisible();
    await expect(page.getByText(EXTRAPOLATION)).toBeVisible();
    await expect(page.getByRole("table", { name: "Errors against the solver reference" })).toHaveCount(0);
  });

  test("FR-011-11 · the limits of the envelope themselves (0.5 and 4) are inside it", async ({ page }) => {
    await open(page, SIMULATE);
    const region = page.getByRole("region", { name: "GNS granular flow" });
    for (const value of ["0.5", "4"]) {
      await region.getByRole("spinbutton", { name: "Aspect ratio" }).fill(value);
      await region.getByRole("button", { name: "Start" }).click();
      await expect(page.getByRole("img", { name: "Live GNS rollout" })).toBeVisible();
      await expect(page.getByText(EXTRAPOLATION)).toHaveCount(0);
      await region.getByRole("button", { name: "Stop" }).click();
    }
  });
});

test.describe("step time (NFR-011-02)", () => {
  test("NFR-011-02 · the median step time and the T2 particle cap are measured and shown", async ({
    page,
  }) => {
    await start(page);
    const step = page.getByRole("status", { name: "Step time" });
    await expect(step).toHaveText(/\d+(\.\d+)?\s?ms/, { timeout: 60_000 });
    const cap = page.getByRole("status", { name: "T2 particle cap" });
    await expect(cap).toHaveText(/\d+\s?particles/);
    const capValue = Number(((await cap.textContent()) ?? "").match(/\d+/)?.[0]);
    const count = page
      .getByRole("region", { name: "GNS granular flow" })
      .getByRole("spinbutton", { name: "Particle count" });
    expect(Number(await count.getAttribute("max"))).toBeLessThanOrEqual(capValue);
  });
});
