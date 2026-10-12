// T-018-017 [red] · FR-018-32: while the active tier is T2, the engines that need GPU compute (granular, shallow water, dust
// particles) show their baked replay with the REPLAY badge and the note "needs WebGPU to compute live" instead of computing.
//
// Hooks: web/e2e/support/simulate.ts. Spec 018 section 7.1: granular (A3), swe (C2) and dust-particles (C3) are WGSL compute,
// "T1 only", with a replay-shard / baked-aggregate T0 fallback. Oracles: the EARS text and that table.
import { expect, test } from "@playwright/test";
import { injectGpu } from "./support/gpu";
import { enginePanel, openSimulate } from "./support/simulate";

const GPU_ENGINES: Array<[caseId: string, engine: string]> = [
  ["A3", "granular"],
  ["C2", "swe"],
  ["C3", "dust-particles"],
];

for (const [caseId, engine] of GPU_ENGINES) {
  test(`FR-018-32 · forced T2: ${caseId} ${engine} shows its baked replay, the REPLAY badge and the WebGPU note`, async ({
    page,
  }) => {
    await openSimulate(page, caseId, "&tier=t2");
    const panel = enginePanel(page, engine);
    await expect(panel).toHaveAttribute("data-state", "replay");
    await expect(panel).toHaveAttribute("data-tier", "t2");
    await expect(panel.getByTestId("lane-badge")).toHaveText("REPLAY");
    await expect(panel.getByTestId("engine-notice")).toContainText("needs WebGPU to compute live");
    // nothing was computed: no engine request was sent for it
    await expect(panel).toHaveAttribute("data-requests", "0");
  });
}

test("FR-018-32 · a page without WebGPU (no navigator.gpu) behaves the same as forced T2", async ({
  page,
}) => {
  await injectGpu(page, "none");
  await openSimulate(page, "C3", "");
  const panel = enginePanel(page, "dust-particles");
  await expect(panel.getByTestId("engine-notice")).toContainText("needs WebGPU to compute live");
  await expect(panel.getByTestId("lane-badge")).toHaveText("REPLAY");
});

test("FR-018-32 · the other engines of the same page are not affected: C3 plume still computes live on T2", async ({
  page,
}) => {
  await openSimulate(page, "C3", "&tier=t2");
  const plume = enginePanel(page, "plume");
  await expect(plume.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
  await expect(plume.getByTestId("engine-notice")).not.toContainText("needs WebGPU");
});

test("FR-018-32 · with a working GPU (T1) the note is not shown", async ({ page }) => {
  await injectGpu(page, "ok");
  await openSimulate(page, "C3", "");
  await expect(page.getByTestId("tier-badge")).toHaveAttribute("data-tier", "t1");
  const panel = enginePanel(page, "dust-particles");
  await expect(panel).toBeVisible();
  await expect(panel).not.toContainText("needs WebGPU to compute live");
});
