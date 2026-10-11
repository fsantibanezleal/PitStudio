// T-018-022 [red] · FR-018-04 (layers) and FR-018-05 (KPIs with "Not yet run") on the production build, route `/`.
//
// Observation hooks the green commit must provide on `/` (the rail and the KPI panel are fixed by t_018_021):
//   [data-testid="kpi-panel"][data-case="<id>"]   one `[data-kpi="<kpi id>"]` row per headline KPI (see t_018_022_kpis.test.tsx)
//   [data-testid="layers"]                        container of the layer toggles of the selected case; one `button[data-layer="<layer id>"]`
//                                                 per layer id of DC-018-01 (`terrain-2018`, `terrain-2023`, `roads`, `pit-shells`, `fleet`,
//                                                 `fields`, `sensors`) listed in the case's `layers` (extra toggles are allowed);
//                                                 `aria-pressed` = visible; `disabled` and containing the text "Not yet run" when the layer
//                                                 has no published artefact
//   [data-testid="scene-state"][data-visible-layers="<ids, comma separated, canonical order>"]   the scene's current layer set
// Assumption written into the tests (spec 018 does not define the layer -> artefact mapping; flagged for the maintainer):
//   a layer L is "published" for case C iff the web manifest (runtime fetch of `<base>assets/manifest.json`) holds an artefact whose
//   `id` starts with `layer-<L>` and whose `cases` is absent, empty or contains C.
// Oracles: the valid case registry example (headline KPIs, layers, units); hand-written fixture manifest; FR-018-04 / FR-018-05 text.
import { createHash } from "node:crypto";
import { expect, test } from "@playwright/test";
import {
  CASE_IDS,
  headlineKpis,
  loadCaseRegistry,
  makeArtefact,
  makeWebIndex,
  UNIT_SYMBOLS,
} from "../src/test-support/fixtures";
import { open } from "./helpers";

const registry = loadCaseRegistry();

test.describe("KPIs without a published artefact (FR-018-05)", () => {
  test("FR-018-05 · every headline KPI of every case shows 'Not yet run' in place of its value, with its unit and no badge", async ({
    page,
  }) => {
    for (const id of CASE_IDS) {
      await open(page, `?case=${id}`);
      const panel = page.getByTestId("kpi-panel");
      await expect(panel).toHaveAttribute("data-case", id);
      const kpis = headlineKpis(registry, id);
      await expect(panel.locator("[data-kpi]")).toHaveCount(kpis.length);
      for (const kpi of kpis) {
        const row = panel.locator(`[data-kpi="${kpi.id}"]`);
        await expect(row).toContainText(kpi.name.en);
        await expect(row).toContainText("Not yet run");
        const symbol = UNIT_SYMBOLS[kpi.unit];
        if (symbol) await expect(row).toContainText(symbol);
        await expect(row).not.toContainText(/\bLIVE\b|\bREPLAY\b|\bSTATIC\b/);
        await expect(row).not.toContainText(/NaN|Infinity|undefined|null/);
      }
    }
  });
});

test.describe("layers (FR-018-04)", () => {
  test("FR-018-04 · with nothing published every layer of the case is disabled and says 'Not yet run'", async ({
    page,
  }) => {
    await open(page, "?case=A1");
    const layers = page.getByTestId("layers");
    await expect(layers).toBeVisible();
    for (const layer of registry.cases.A1?.layers ?? []) {
      const toggle = layers.locator(`button[data-layer="${layer}"]`);
      await expect(toggle).toHaveCount(1);
      await expect(toggle).toBeDisabled();
      await expect(toggle).toContainText("Not yet run");
    }
  });

  test("FR-018-04 · a published layer is enabled, exposes aria-pressed and shows or hides the layer within 100 ms; unpublished layers stay disabled", async ({
    page,
  }) => {
    const body = JSON.stringify({ type: "FeatureCollection", features: [] });
    const sha256 = createHash("sha256").update(body).digest("hex");
    const bytes = Buffer.byteLength(body);
    const artefacts = [
      makeArtefact({
        id: "layer-terrain-2023",
        kind: "mesh",
        path: "assets/layers/terrain-2023.json",
        bytes,
        sha256,
        cases: [],
        lane: "replay",
      }),
      makeArtefact({
        id: "layer-roads",
        kind: "mesh",
        path: "assets/layers/roads.json",
        bytes,
        sha256,
        cases: ["A1"],
        lane: "replay",
      }),
    ];
    await page.route("**/assets/manifest.json", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(makeWebIndex(artefacts)) }),
    );
    await page.route("**/assets/layers/*.json", (route) =>
      route.fulfill({ contentType: "application/json", body }),
    );

    await open(page, "?case=A1");
    const layers = page.getByTestId("layers");
    for (const layer of ["terrain-2023", "roads"]) {
      const toggle = layers.locator(`button[data-layer="${layer}"]`);
      await expect(toggle).toBeEnabled();
      await expect(toggle).not.toContainText("Not yet run");
      const state = await toggle.getAttribute("aria-pressed");
      expect(["true", "false"]).toContain(state);
    }
    const fleet = layers.locator('button[data-layer="fleet"]');
    await expect(fleet).toBeDisabled();
    await expect(fleet).toContainText("Not yet run");

    const roads = layers.locator('button[data-layer="roads"]');
    const before = await roads.getAttribute("aria-pressed");
    const visibleBefore = (await page.getByTestId("scene-state").getAttribute("data-visible-layers")) ?? "";
    const result = await page.evaluate(async () => {
      const button = document.querySelector<HTMLButtonElement>(
        '[data-testid="layers"] button[data-layer="roads"]',
      );
      if (!button) throw new Error("no roads toggle");
      const t0 = performance.now();
      button.click();
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      return {
        elapsed: performance.now() - t0,
        pressed: button.getAttribute("aria-pressed"),
        visible:
          document.querySelector('[data-testid="scene-state"]')?.getAttribute("data-visible-layers") ?? "",
      };
    });
    expect(result.elapsed).toBeLessThan(100);
    expect(result.pressed).toBe(before === "true" ? "false" : "true");
    const had = visibleBefore.split(",").includes("roads");
    expect(result.visible.split(",").includes("roads")).toBe(!had);
    expect(result.pressed === "true").toBe(!had);

    await roads.click();
    await expect(roads).toHaveAttribute("aria-pressed", before as string);
    await expect(page.getByTestId("scene-state")).toHaveAttribute("data-visible-layers", visibleBefore);
  });

  test("FR-018-04 · a layer artefact of another case does not enable the layer", async ({ page }) => {
    const artefacts = [
      makeArtefact({
        id: "layer-roads",
        kind: "mesh",
        path: "assets/layers/roads.json",
        cases: ["B1"],
        lane: "replay",
      }),
    ];
    await page.route("**/assets/manifest.json", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(makeWebIndex(artefacts)) }),
    );
    await open(page, "?case=A1");
    const roads = page.getByTestId("layers").locator('button[data-layer="roads"]');
    await expect(roads).toBeDisabled();
    await expect(roads).toContainText("Not yet run");
  });

  test("FR-018-04 · a malformed manifest leaves every layer disabled and the page usable", async ({
    page,
  }) => {
    await page.route("**/assets/manifest.json", (route) =>
      route.fulfill({ contentType: "application/json", body: '{"kind":"web-index","artefacts":"nope"' }),
    );
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await open(page, "?case=A1");
    const layers = page.getByTestId("layers");
    for (const layer of registry.cases.A1?.layers ?? []) {
      await expect(layers.locator(`button[data-layer="${layer}"]`)).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
});
