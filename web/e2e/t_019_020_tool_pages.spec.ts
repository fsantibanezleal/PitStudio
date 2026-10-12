// T-019-020 [red] · FR-019-08 (for every registry id of spec section 7.1, /studio/tools/<id>/ is a prerendered page answering HTTP 200 with eight blocks in this order: Identity, Role in
// mining, Artefacts it produced, Provenance, Where it ran, Limits and failures, Reproduce, Alternatives rejected) and FR-019-20 (any other id, other spellings, encoded separators and `..`
// included, answers HTTP 404 with the not-found page and requests no tool asset).
//
// Hooks: section[data-block="identity" | "role" | "artefacts" | "provenance" | "where-ran" | "limits" | "reproduce" | "alternatives"] in this order, each with an h2 holding its title;
// main h1 with the tool's name; the not-found page is `main h1` "Page not found" (as in web/e2e/shell.spec.ts).
// Oracles: the 20 ids of spec section 7.1 (17 studio tools and the three evaluated-not-adopted entries); the block titles of FR-019-08; HTTP status codes.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const IDS = [
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
const BLOCKS: Array<[string, string]> = [
  ["identity", "Identity"],
  ["role", "Role in mining"],
  ["artefacts", "Artefacts it produced"],
  ["provenance", "Provenance"],
  ["where-ran", "Where it ran"],
  ["limits", "Limits and failures"],
  ["reproduce", "Reproduce"],
  ["alternatives", "Alternatives rejected"],
];

test.describe("the 20 tool pages (FR-019-08)", () => {
  for (const id of IDS) {
    test(`FR-019-08 · /studio/tools/${id}/ answers 200 and is a prerendered page`, async ({ request }) => {
      const res = await request.get(`studio/tools/${id}/`);
      expect(res.status()).toBe(200);
      expect(res.headers()["content-type"]).toContain("text/html");
      const html = await res.text();
      expect(html).toContain("<title>");
      for (const [block] of BLOCKS)
        expect(html, `block ${block} is in the HTML as served`).toContain(`data-block="${block}"`);
      expect(readFileSync(resolve("build/client", "studio/tools", id, "index.html"), "utf8")).toContain(
        `data-block="identity"`,
      );
    });

    test(`FR-019-08 · /studio/tools/${id}/ has the eight blocks in the order of the spec, each with its title`, async ({
      page,
    }) => {
      await open(page, `studio/tools/${id}/`);
      await expect(page.locator("main h1")).not.toHaveText("Page not found");
      expect(await page.locator("main h1").innerText()).not.toBe("");
      const blocks = await page
        .locator("section[data-block]")
        .evaluateAll((els) =>
          els.map((e) => ({
            block: e.getAttribute("data-block"),
            title: e.querySelector("h2")?.textContent?.trim(),
          })),
        );
      expect(blocks).toEqual(BLOCKS.map(([block, title]) => ({ block, title })));
    });
  }

  test("FR-019-08 · the page of an unknown tool is not one of the 20: exactly the ids of section 7.1 are prerendered", async ({
    request,
  }) => {
    for (const id of ["warp-lang", "cosmos", "tool"])
      expect((await request.get(`studio/tools/${id}/`)).status()).toBe(404);
  });

  test("FR-019-08 · the block titles follow the language and the order is the same in Spanish", async ({
    page,
  }) => {
    await open(page, "studio/tools/warp/?lang=es");
    const titles = await page.locator("section[data-block] h2").allTextContents();
    expect(titles).toHaveLength(8);
    expect(titles).not.toEqual(BLOCKS.map(([, t]) => t));
    expect(
      await page
        .locator("section[data-block]")
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-block"))),
    ).toEqual(BLOCKS.map(([b]) => b));
  });
});

test.describe("other ids are not found (FR-019-20)", () => {
  const HOSTILE: Array<[string, string]> = [
    ["unknown id", "no-such-tool"],
    ["upper case spelling", "Warp"],
    ["all upper case", "WARP"],
    ["trailing space", "warp%20"],
    ["leading space", "%20warp"],
    ["encoded slash", "warp%2Fcuopt"],
    ["encoded dot dot segment inside a name", "wa%2e%2erp"],
    ["encoded backslash", "warp%5Ccuopt"],
    ["double encoded slash", "warp%252Fcuopt"],
    ["nested path", "warp/extra"],
    ["extension", "warp.html"],
    ["null byte", "warp%00"],
    ["underscore spelling", "mujoco_warp"],
    ["fullwidth letters", "%EF%BD%97%EF%BD%81%EF%BD%92%EF%BD%90"],
    ["right-to-left override", "%E2%80%AEwarp"],
    ["markup", "%3Cscript%3Ealert(1)%3C%2Fscript%3E"],
    ["very long", "a".repeat(3000)],
  ];
  for (const [what, id] of HOSTILE) {
    test(`FR-019-20 · ${what}: HTTP 404, the not-found page, and no tool asset requested`, async ({
      page,
    }) => {
      const urls: string[] = [];
      page.on("request", (r) => {
        if (!r.isNavigationRequest()) urls.push(r.url());
      });
      const path = `studio/tools/${id}/`;
      const res = await page.goto(path);
      expect(res?.status()).toBe(404);
      await open(page, path);
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(
        urls.filter((u) =>
          /\/studio\/tools\/|\/assets\/tools\/|studio\/index\.json/.test(new URL(u).pathname),
        ),
      ).toEqual([]);
      expect(await page.locator("section[data-block]").count()).toBe(0);
    });
  }

  test("FR-019-20 · the HTTP status is 404 for the same ids through a plain request too (no soft 404)", async ({
    request,
  }) => {
    for (const id of ["no-such-tool", "Warp", "warp/extra", "warp.html"]) {
      const res = await request.get(`studio/tools/${id}/`);
      expect(res.status(), id).toBe(404);
    }
  });
});
