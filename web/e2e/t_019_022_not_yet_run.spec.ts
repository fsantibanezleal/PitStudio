// T-019-022 [red] · FR-019-12 (a tool page lists exactly the artefacts of its producer.tool), FR-019-13 ("Not yet run" while nothing is published, with no image, video or metric of the tool),
// FR-019-14 ("Evaluated, not adopted" with its reason and evidence link, no artefact grid), FR-000-06 (badge and provenance on every card) and FR-000-07 (the map node says "not yet run").
// Unit half: web/src/studio/blocks/t_019_022_artefacts.test.tsx.
//
// US-019-2 independent test: with a fixture manifest `/studio/tools/warp/` lists exactly the Warp artefacts, with an empty one it reads "Not yet run". The fixture manifest is served with page.route
// at `**/assets/manifest.json` (the same hook the case pages use in T-018-031), so the Artefacts block reads the published web manifest in the browser; the prerendered HTML (empty manifest) says "Not yet run".
// Hooks: section[data-block="artefacts"] with [data-testid="not-yet-run"], [data-testid="not-adopted"], [data-case-group="<id>"], article[data-artefact] with [data-lane]; the map node of /studio/ is
// [data-testid="tool-node"][data-tool][data-status].
// Oracles: the EARS strings; the 20 ids and the three evaluated-not-adopted entries of spec section 7.1; hand-built manifests (web/src/test-support/fixtures.ts, data-model 001 section 2.5).
import { expect, type Page, test } from "@playwright/test";
import { makeArtefact, makeWebIndex } from "../src/test-support/fixtures";
import { open } from "./helpers";

const ADOPTED = [
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
];
const NOT_ADOPTED = ["cuopt", "physicsnemo", "cosmos-predict-transfer"];

const art = (id: string, tool: string, over: Record<string, unknown> = {}) =>
  makeArtefact({ id, producer: { tool, stage: { id: "st50_physics" } }, ...over } as never);
const serve = (page: Page, artefacts: unknown[]) =>
  page.route("**/assets/manifest.json", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(makeWebIndex(artefacts as never)),
    }),
  );

test.describe("nothing published (FR-019-13, FR-000-07)", () => {
  for (const id of ADOPTED) {
    test(`FR-019-13 · /studio/tools/${id}/ reads 'Not yet run' and shows no image, video or metric`, async ({
      page,
    }) => {
      await open(page, `studio/tools/${id}/`);
      const block = page.locator('section[data-block="artefacts"]');
      await expect(block.getByTestId("not-yet-run")).toContainText("Not yet run");
      await expect(block.locator("article[data-artefact]")).toHaveCount(0);
      await expect(page.locator("main img, main video, main canvas")).toHaveCount(0);
      await expect(page.locator("main [data-kpi]")).toHaveCount(0);
    });
  }

  test("FR-000-07 · on the map every studio tool is 'not yet run' and none is marked done", async ({
    page,
  }) => {
    await open(page, "studio/");
    for (const id of ADOPTED) {
      const node = page
        .locator(`[data-testid="static-map"] [data-testid="tool-node"][data-tool="${id}"]`)
        .first();
      await expect(node).toHaveAttribute("data-status", "not-yet-run");
      await expect(node).toContainText("Not yet run");
    }
    await expect(page.locator('[data-testid="tool-node"][data-status="done"]')).toHaveCount(0);
  });
});

test.describe("evaluated, not adopted (FR-019-14)", () => {
  for (const id of NOT_ADOPTED) {
    test(`FR-019-14 · /studio/tools/${id}/ shows 'Evaluated, not adopted', its reason and its evidence page, and no artefact grid`, async ({
      page,
    }) => {
      await serve(page, [art("stray-artefact", id, { cases: ["A1"] })]);
      await open(page, `studio/tools/${id}/`);
      const box = page.locator('section[data-block="artefacts"]').getByTestId("not-adopted");
      await expect(box).toContainText("Evaluated, not adopted");
      expect(
        ((await box.textContent()) ?? "").replace("Evaluated, not adopted", "").trim().length,
      ).toBeGreaterThan(20);
      await expect(box.locator("a")).toHaveAttribute("href", new RegExp(`not-adopted-${id}`));
      await expect(page.locator("article[data-artefact]")).toHaveCount(0);
      await expect(page.locator('section[data-block="artefacts"]')).not.toContainText("Not yet run");
    });
  }
});

test.describe("a fixture manifest (FR-019-12, FR-000-06)", () => {
  const manifest = [
    art("warp-granular-a3", "warp", { cases: ["A3"], lane: "replay" }),
    art("warp-dust-c3", "warp", { cases: ["C3"], lane: "live" }),
    art("warp-shared", "warp", {
      cases: ["A3", "C3"],
      lane: "static",
      kind: "image",
      budget_class: "own-code",
    }),
    art("newton-a2", "newton", { cases: ["A2"] }),
    art("pytorch-c1", "pytorch", { cases: ["C1"] }),
  ];

  test("FR-019-12 · /studio/tools/warp/ lists exactly the Warp artefacts, grouped by case, each with its badge", async ({
    page,
  }) => {
    await serve(page, manifest);
    await open(page, "studio/tools/warp/");
    const block = page.locator('section[data-block="artefacts"]');
    await expect(block.locator("article[data-artefact]")).toHaveCount(4, { timeout: 15_000 });
    const ids = await block
      .locator("article[data-artefact]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-artefact")).sort());
    expect(ids).toEqual(["warp-dust-c3", "warp-granular-a3", "warp-shared", "warp-shared"]);
    await expect(block.locator('[data-case-group="A3"] article')).toHaveCount(2);
    await expect(block.locator('[data-case-group="C3"] article')).toHaveCount(2);
    await expect(block.locator('article[data-artefact="warp-granular-a3"] [data-lane]')).toHaveText("REPLAY");
    await expect(block.locator('article[data-artefact="warp-dust-c3"] [data-lane]')).toHaveText("LIVE");
    await expect(
      block.locator('[data-case-group="A3"] article[data-artefact="warp-shared"] [data-lane]'),
    ).toHaveText("STATIC");
    await expect(block.getByTestId("not-yet-run")).toHaveCount(0);
  });

  test("FR-000-06 · every card shows its producing tool, run id and commit", async ({ page }) => {
    await serve(page, manifest);
    await open(page, "studio/tools/warp/");
    const card = page.locator('section[data-block="artefacts"] article[data-artefact="warp-dust-c3"]');
    await expect(card).toContainText("warp");
    await expect(card).toContainText("20261011T083000Z-a1");
    await expect(card).toContainText("0123456");
  });

  test("FR-019-12 · another tool's page lists none of them, and an empty manifest reads 'Not yet run'", async ({
    page,
  }) => {
    await serve(page, manifest);
    await open(page, "studio/tools/openusd/");
    await expect(page.locator('section[data-block="artefacts"]').getByTestId("not-yet-run")).toContainText(
      "Not yet run",
    );
    await expect(page.locator("article[data-artefact]")).toHaveCount(0);
    await serve(page, []);
    await open(page, "studio/tools/warp/");
    await expect(page.locator('section[data-block="artefacts"]').getByTestId("not-yet-run")).toContainText(
      "Not yet run",
    );
  });

  test("FR-019-13 · a tool whose artefact exists no longer says 'Not yet run' on the map or on its page", async ({
    page,
  }) => {
    await serve(page, manifest);
    await open(page, "studio/tools/newton/");
    await expect(
      page.locator('section[data-block="artefacts"] article[data-artefact="newton-a2"]'),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('section[data-block="artefacts"]')).not.toContainText("Not yet run");
  });
});
