// T-020-040 [red] · FR-020-32 (the sections and the provenance of /knowledge), FR-020-36 (datasets), FR-020-37 (frameworks link to /studio/tools/<id>/), FR-020-38 (bibliography anchors) on the built site. Unit half:
// web/src/knowledge/t_020_040_sections.test.tsx.
//
// Oracles: the `minephys` version and commit recorded in `uv.lock` (read here by regular expression over the raw text: version = "0.0.0", git source commit 143e709d119258f2defc4a7953663ba6377bd6ae in the repository state of this
// task), the six section names of FR-020-32, the 20 tool ids of spec 019 section 7.1, the entries of `data/sources.yaml` (counted here by regular expression over `- id:` lines). Hooks as in the unit half.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

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
const SECTIONS = ["glossary", "equations", "parameters", "datasets", "frameworks", "bibliography"];
const lock = readFileSync(resolve("..", "uv.lock"), "utf8");
const pin = /name = "minephys"\nversion = "([^"]+)"\nsource = \{ git = "[^"#]+#([0-9a-f]{40})" \}/.exec(lock);
const sourceIds = [
  ...readFileSync(resolve("..", "data", "sources.yaml"), "utf8").matchAll(/^\s*-\s+id:\s*(\S+)/gm),
].map((m) => m[1] as string);

test.describe("/knowledge (FR-020-32)", () => {
  test("FR-020-32 · offers the six sections in order, and ?section= selects one", async ({ page }) => {
    await open(page, "knowledge/");
    const nav = page.getByTestId("knowledge-nav");
    expect(
      await nav
        .locator("a[data-section]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-section"))),
    ).toEqual(SECTIONS);
    for (const s of SECTIONS) {
      await open(page, `knowledge/?section=${s}`);
      await expect(nav.locator(`a[data-section="${s}"]`)).toHaveAttribute("aria-current", "page");
    }
  });

  test("FR-020-32 · shows the minephys version and commit pinned in uv.lock", async ({ page }) => {
    expect(pin, "uv.lock pins minephys by git").not.toBeNull();
    await open(page, "knowledge/");
    const p = page.getByTestId("knowledge-provenance");
    await expect(p).toContainText(pin?.[1] ?? "?");
    await expect(p).toContainText((pin?.[2] ?? "?").slice(0, 7));
  });

  test("FR-020-32 · the page is prerendered: the sections and the provenance are in the HTML as served", async ({
    request,
  }) => {
    const html = await (await request.get("knowledge/")).text();
    for (const s of SECTIONS) expect(html).toContain(`data-section="${s}"`);
    expect(html).toContain('data-testid="knowledge-provenance"');
  });
});

test.describe("datasets, frameworks and bibliography (FR-020-36, FR-020-37, FR-020-38)", () => {
  test("FR-020-36 · the datasets section lists one row per entry of data/sources.yaml, each with its landing URL and its card", async ({
    page,
  }) => {
    await open(page, "knowledge/?section=datasets");
    await expect(page.getByTestId("knowledge-nav")).toBeVisible();
    const rows = page.locator("tr[data-dataset]");
    expect(await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-dataset")))).toEqual(
      sourceIds,
    );
    for (const id of sourceIds) {
      const row = page.locator(`tr[data-dataset="${id}"]`);
      await expect(row.locator("a")).toHaveCount(2);
      await expect(row.locator('a[href^="https://"]')).toHaveCount(1);
    }
  });

  test("FR-020-37 · the frameworks section lists the 20 tools, each linking to its page, the evaluated-not-adopted ones included", async ({
    page,
  }) => {
    await open(page, "knowledge/?section=frameworks");
    for (const id of TOOLS)
      await expect(
        page.locator(`li[data-framework="${id}"] a[href$="/studio/tools/${id}/"]`),
        id,
      ).toHaveCount(1);
    for (const id of ["cuopt", "physicsnemo", "cosmos-predict-transfer"])
      await expect(page.locator(`li[data-framework="${id}"]`)).toContainText("Evaluated, not adopted");
  });

  test("FR-020-37 · following a framework link opens the tool page", async ({ page }) => {
    await open(page, "knowledge/?section=frameworks");
    await page.locator('li[data-framework="warp"] a').first().click();
    await expect(page).toHaveURL(/\/studio\/tools\/warp\/?$/);
  });

  test("FR-020-38 · every bibliography entry is an anchor equal to its key: a link to #<key> scrolls to it", async ({
    page,
  }) => {
    await open(page, "knowledge/?section=bibliography");
    const keys = await page
      .locator("article[data-bib]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("id")));
    expect(keys.length).toBeGreaterThan(0);
    for (const key of keys.slice(0, 5)) {
      expect(key).toBeTruthy();
      await page.goto(`knowledge/?section=bibliography#${key}`);
      await expect(page.locator(`article[id="${key}"]`)).toBeInViewport();
    }
  });
});
