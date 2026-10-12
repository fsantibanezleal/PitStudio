// T-019-023 [red] · FR-019-15 (provenance chips on each artefact of a tool page, with the local-only replacement) and FR-019-37 (cosmos-reason-2 artefacts show "Built on NVIDIA Cosmos" and "display-only"),
// FR-000-08 (no performance number of a local-only stage reaches the page). Unit half: web/src/studio/blocks/t_019_023_provenance.test.tsx.
//
// Fixtures: the web manifest is served at `**/assets/manifest.json` and the run card of each run at `**/assets/runs/<run id>/manifest.json` (spec 019: `web/public/assets/runs/<run_id>/manifest.json`);
// the run card is the valid example of DC-001-01 with its run id replaced. Hooks as in the unit half: [data-testid="provenance"] [data-chip="<id>"] with data-value, article[data-artefact].
// Oracles: the numbers of the valid run card (stage st56_encode: wall 42.5 s, peak VRAM 2 GiB, energy 3034.5 J, GPU "NVIDIA RTX 5000 Ada Generation Laptop GPU", driver 582.78) and of the planted local-only numbers below.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";
import { makeArtefact, makeWebIndex } from "../src/test-support/fixtures";
import { open } from "./helpers";

const CARD = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../specs/001-contracts/contracts/examples/manifest.valid.json",
    ),
    "utf8",
  ),
) as { run_id: string; stages: Array<Record<string, unknown>>; [k: string]: unknown };
const RUN = "20261011T083000Z-prov";
const LOCAL = "20261011T093000Z-loc";

function runCard(runId: string, stages: Array<Record<string, unknown>>) {
  return { ...structuredClone(CARD), run_id: runId, stages };
}
const publicStage = {
  ...(structuredClone(CARD.stages[0]) as Record<string, unknown>),
  key: { id: "st50_physics" },
  tool: "warp",
};
const localStage = {
  ...(structuredClone(CARD.stages[0]) as Record<string, unknown>),
  key: { id: "st55_sdg" },
  tool: "isaac-sim-replicator",
  performance: "local-only",
  wall_s: 913.75,
  telemetry: "measured locally, not published (licence)",
};

async function publish(page: Page): Promise<void> {
  const artefacts = [
    makeArtefact({
      id: "warp-field-c2",
      run_id: RUN,
      producer: { tool: "warp", stage: { id: "st50_physics" } },
      cases: ["C2"],
    } as never),
    makeArtefact({
      id: "isaac-render-b1",
      run_id: LOCAL,
      kind: "image",
      lane: "static",
      budget_class: "own-code",
      producer: { tool: "isaac-sim-replicator", stage: { id: "st55_sdg" } },
      cases: ["B1"],
    } as never),
    makeArtefact({
      id: "cosmos-caption-b1",
      run_id: RUN,
      kind: "text",
      lane: "static",
      budget_class: "own-code",
      producer: { tool: "cosmos-reason-2", stage: { id: "st59c_captions" } },
      cases: ["B1"],
    } as never),
  ];
  const index = {
    ...makeWebIndex(artefacts as never),
    runs: [RUN, LOCAL].map((id) => ({ run_id: id, manifest: `${id}/manifest.json`, sha256: "a".repeat(64) })),
  };
  await page.route("**/assets/manifest.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(index) }),
  );
  await page.route(`**/assets/runs/${RUN}/manifest.json`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        runCard(RUN, [
          publicStage,
          { ...publicStage, key: { id: "st59c_captions" }, tool: "cosmos-reason-2" },
        ]),
      ),
    }),
  );
  await page.route(`**/assets/runs/${LOCAL}/manifest.json`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(runCard(LOCAL, [localStage])) }),
  );
}

test.describe("provenance chips (FR-019-15)", () => {
  test("FR-019-15 · a Warp artefact shows run id, recipe, git SHA, GPU, driver, wall time, peak VRAM and energy", async ({
    page,
  }) => {
    await publish(page);
    await open(page, "studio/tools/warp/");
    const chips = page
      .locator('article[data-artefact="warp-field-c2"]')
      .locator("..")
      .locator('[data-testid="provenance"]')
      .first();
    await expect(chips).toBeVisible({ timeout: 15_000 });
    await expect(chips.locator('[data-chip="run"]')).toContainText(RUN);
    await expect(chips.locator('[data-chip="recipe"]')).toContainText("eeeeeeeeeeee");
    await expect(chips.locator('[data-chip="git"]')).toContainText("0123456");
    await expect(chips.locator('[data-chip="gpu"]')).toContainText(
      "NVIDIA RTX 5000 Ada Generation Laptop GPU",
    );
    await expect(chips.locator('[data-chip="driver"]')).toContainText("582.78");
    await expect(chips.locator('[data-chip="wall"]')).toHaveAttribute("data-value", "42.5");
    await expect(chips.locator('[data-chip="vram"]')).toHaveAttribute("data-value", "2");
    await expect(chips.locator('[data-chip="energy"]')).toHaveAttribute("data-value", "3034.5");
    for (const reason of ["sw_power_cap", "sw_thermal", "hw_thermal", "hw_slowdown", "power_brake"])
      await expect(chips.locator(`[data-chip="throttle-${reason}"]`)).toHaveCount(1);
  });

  test("FR-019-15 · an Isaac Sim + Replicator artefact shows 'measured locally, not published (licence)' instead of wall time, VRAM, energy and throttle, and the page holds no number of that stage", async ({
    page,
  }) => {
    await publish(page);
    await open(page, "studio/tools/isaac-sim-replicator/");
    const chips = page.locator('[data-testid="provenance"]').first();
    await expect(chips.locator('[data-chip="local-only"]')).toContainText(
      "measured locally, not published (licence)",
      { timeout: 15_000 },
    );
    for (const kind of ["wall", "vram", "energy", "throttle-sw_power_cap"])
      await expect(chips.locator(`[data-chip="${kind}"]`)).toHaveCount(0);
    const html = await page.content();
    for (const planted of ["913.75", "3034.5"]) expect(html, planted).not.toContain(planted);
  });
});

test.describe("Built on NVIDIA Cosmos (FR-019-37)", () => {
  test("FR-019-37 · /studio/tools/cosmos-reason-2/ shows the attribution and the display-only label on each of its artefacts", async ({
    page,
  }) => {
    await publish(page);
    await open(page, "studio/tools/cosmos-reason-2/");
    const card = page.locator('article[data-artefact="cosmos-caption-b1"]');
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText("Built on NVIDIA Cosmos");
    await expect(card).toContainText("display-only");
  });

  test("FR-019-37 · the attribution is absent from the artefacts of other tools", async ({ page }) => {
    await publish(page);
    await open(page, "studio/tools/warp/");
    await expect(page.locator('article[data-artefact="warp-field-c2"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator("main")).not.toContainText("Built on NVIDIA Cosmos");
    await expect(page.locator("main")).not.toContainText("display-only");
  });
});
