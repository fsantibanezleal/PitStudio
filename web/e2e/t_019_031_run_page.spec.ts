// T-019-031 [red] · FR-019-22 (/studio/runs/<run id>/ is a prerendered page answering 200 with a manifest viewer, telemetry charts of its open-runtime stages, the stage DAG with cache hits, the determinism
// block and its artefacts) and FR-019-23 (the manifest viewer is a collapsible tree with the WAI-ARIA tree keys, shows each SHA-256 in full with a copy control, and renders a 200 KB run card within 500 ms
// on CI Chromium). Unit half of the tree: web/src/studio/t_019_031_manifest_tree.test.tsx.
//
// Fixture runs: web/e2e/support/studio-runs.ts (A, B and the 199,866-byte card BIG); the build holds them as published runs.
// Hooks: [data-testid="manifest-tree"] (role tree, as in the unit half; it carries a User Timing measure `studio:manifest-render` whose duration in ms is the time its first render took),
// [data-testid="telemetry-charts"] with [data-testid="chart"][data-stage="<stage id>"] per public stage that has published telemetry, [data-testid="stage-dag"], [data-testid="determinism"],
// [data-testid="run-artefacts"] with article[data-artefact].
// Oracles: the facts of the fixture runs (hand transcription: public stages, artefact ids, digests); the WAI-ARIA tree keys; the 500 ms bound of FR-019-23.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { RUN_A, RUN_B, RUN_BIG, RUNS } from "./support/studio-runs";

const D64 = "d".repeat(64);

test.describe("the run page (FR-019-22)", () => {
  for (const id of [RUN_A, RUN_B, RUN_BIG]) {
    test(`FR-019-22 · /studio/runs/${id}/ answers 200 and holds the five blocks`, async ({
      page,
      request,
    }) => {
      expect((await request.get(`studio/runs/${id}/`)).status()).toBe(200);
      await open(page, `studio/runs/${id}/`);
      await expect(page.getByTestId("manifest-tree")).toBeVisible();
      await expect(page.getByTestId("telemetry-charts")).toBeVisible();
      await expect(page.getByTestId("stage-dag")).toBeVisible();
      await expect(page.getByTestId("determinism")).toBeVisible();
      await expect(page.getByTestId("run-artefacts")).toBeVisible();
      await expect(page.locator("main h1")).toContainText(id);
    });
  }

  for (const id of [RUN_A, RUN_B, RUN_BIG]) {
    test(`FR-019-22 · ${id}: the artefacts block has one card per artefact of the run card`, async ({
      page,
    }) => {
      await open(page, `studio/runs/${id}/`);
      const facts = RUNS[id];
      await expect(page.getByTestId("run-artefacts").locator("article[data-artefact]")).toHaveCount(
        facts?.artefacts.length ?? -1,
      );
      const first = facts?.artefacts[0] ?? "";
      await expect(
        page.getByTestId("run-artefacts").locator(`article[data-artefact="${first}"]`),
      ).toHaveCount(1);
    });
  }

  test("FR-019-22 · telemetry charts exist for the public stages with published telemetry and for no local-only stage", async ({
    page,
  }) => {
    await open(page, `studio/runs/${RUN_A}/`);
    const charts = page.getByTestId("telemetry-charts");
    await expect(charts.locator('[data-testid="chart"][data-stage="st56_encode"]')).not.toHaveCount(0);
    await expect(charts.locator('[data-stage="st53_sensors"]')).toHaveCount(0);
    await expect(charts.locator('[data-stage="st45b_kit_validate"]')).toHaveCount(0);
    await open(page, `studio/runs/${RUN_B}/`);
    await expect(
      page.getByTestId("telemetry-charts").locator('[data-testid="chart"][data-stage="st50_physics"]'),
    ).not.toHaveCount(0);
    await expect(page.getByTestId("telemetry-charts").locator('[data-stage="st55_sdg"]')).toHaveCount(0);
  });

  test("FR-019-22 · the stage DAG names every stage of the run card, with its cache result as text", async ({
    page,
  }) => {
    await open(page, `studio/runs/${RUN_B}/`);
    const dag = page.getByTestId("stage-dag");
    for (const s of RUNS[RUN_B]?.stages ?? []) {
      const node = dag.locator(`[data-stage="${s.id}"]${s.variant ? `[data-variant="${s.variant}"]` : ""}`);
      await expect(node).toHaveCount(1);
      await expect(node).toContainText(s.cache === "hit" ? /cache hit/i : /cache miss/i);
    }
  });

  test("FR-019-22 · the determinism block names the class of the run's stages", async ({ page }) => {
    await open(page, `studio/runs/${RUN_A}/`);
    await expect(page.getByTestId("determinism")).toContainText(/statistical/);
  });
});

test.describe("the manifest viewer (FR-019-23)", () => {
  test("FR-019-23 · is a tree: Tab enters it, the arrow keys open and move, and a digest is shown in full", async ({
    page,
  }) => {
    await open(page, `studio/runs/${RUN_A}/`);
    const tree = page.getByTestId("manifest-tree");
    await expect(tree).toHaveAttribute("role", "tree");
    await tree.locator('[role="treeitem"][data-path="/artefacts"]').focus();
    await page.keyboard.press("ArrowRight"); // opens the array
    await expect(tree.locator('[data-path="/artefacts"]')).toHaveAttribute("aria-expanded", "true");
    await page.keyboard.press("ArrowDown"); // first artefact: a2-haul-clip
    await page.keyboard.press("ArrowDown"); // second artefact: a2-encode-report
    await expect(tree.locator('[data-path="/artefacts/1"]')).toBeFocused();
    await page.keyboard.press("ArrowRight"); // opens it
    const sha = tree.locator('[data-path="/artefacts/1/sha256"]');
    await expect(sha.locator('[data-testid="leaf-value"]')).toHaveText(D64);
  });

  test("FR-019-23 · the copy control puts the whole digest on the clipboard", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await open(page, `studio/runs/${RUN_A}/`);
    const tree = page.getByTestId("manifest-tree");
    await tree.locator('[data-path="/recipe"]').focus();
    await page.keyboard.press("ArrowRight");
    await tree.locator('[data-path="/recipe/sha256"] [data-testid="copy-sha"]').click();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("e".repeat(64));
  });

  test("FR-019-23 · every string of the card is text: nothing in the viewer is parsed as markup", async ({
    page,
  }) => {
    await open(page, `studio/runs/${RUN_A}/`);
    const tree = page.getByTestId("manifest-tree");
    await tree.locator('[data-path="/notes"]').focus();
    await page.keyboard.press("ArrowRight");
    await expect(tree.locator('[data-path="/notes/0"]')).toContainText(
      "scrubbed note: outputs under <repo>/runs/",
    );
    await expect(tree.locator("img, script")).toHaveCount(0);
  });

  test("FR-019-23 · a 199,866-byte run card is rendered by the viewer in at most 500 ms on Chromium", async ({
    page,
  }) => {
    await open(page, `studio/runs/${RUN_BIG}/`);
    await expect(page.getByTestId("manifest-tree")).toBeVisible();
    const ms = await page.evaluate(
      () => performance.getEntriesByName("studio:manifest-render", "measure").at(-1)?.duration ?? Number.NaN,
    );
    expect(Number.isFinite(ms), "the viewer records a User Timing measure 'studio:manifest-render'").toBe(
      true,
    );
    expect(ms).toBeLessThanOrEqual(500);
    // the whole card is reachable: opening the artefact list shows all 285 entries
    const tree = page.getByTestId("manifest-tree");
    await tree.locator('[data-path="/artefacts"]').focus();
    await page.keyboard.press("ArrowRight");
    await expect(tree.locator('[data-path="/artefacts/284"]')).toBeAttached();
  });
});
