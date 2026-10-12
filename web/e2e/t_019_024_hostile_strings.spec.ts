// T-019-024 [red] · FR-019-40 (E2E hostile): strings in the web manifest and in published run cards that hold markup, script, control characters or more than 200 characters are shown on the studio pages
// as escaped, truncated text with an expander, and nothing executes. Unit half: web/src/studio/t_019_024_hostile_strings.test.tsx.
//
// The fixture manifest and run card are served with page.route at `**/assets/manifest.json` and `**/assets/runs/<run id>/manifest.json`. Hooks: [data-testid="safe-text"][data-truncated] with
// [data-testid="safe-text-value"] and button[data-testid="expand"]. Executing code would set `window.__pwned`, open a dialog or add an element: none of those may happen.
// Oracles: the EARS text; the payloads written below.
import { expect, type Page, test } from "@playwright/test";
import { makeArtefact, makeWebIndex } from "../src/test-support/fixtures";
import { open } from "./helpers";

const RUN = "20261011T083000Z-evil";
const PAYLOADS = {
  img: `<img src=x onerror="window.__pwned=1">`,
  script: "<script>window.__pwned=1</script>",
  svg: `"><svg onload=window.__pwned=1>`,
  js: "javascript:window.__pwned=1",
  control: `a${String.fromCharCode(0)}b${String.fromCharCode(7)}c${String.fromCharCode(0x202e)}d`,
  long: "L".repeat(20_000),
};

async function hostile(page: Page): Promise<{ dialogs: string[]; errors: string[] }> {
  const dialogs: string[] = [];
  const errors: string[] = [];
  page.on("dialog", (d) => {
    dialogs.push(d.message());
    void d.dismiss();
  });
  page.on("pageerror", (e) => errors.push(e.message));
  const artefact = makeArtefact({
    id: "warp-evil",
    run_id: RUN,
    producer: { tool: "warp", stage: { id: "st50_physics" } },
    cases: ["C2"],
    attribution: `${PAYLOADS.img}${PAYLOADS.script}${PAYLOADS.long}`,
  } as never);
  const index = {
    ...makeWebIndex([artefact] as never),
    runs: [{ run_id: RUN, manifest: `${RUN}/manifest.json`, sha256: "a".repeat(64) }],
  };
  await page.route("**/assets/manifest.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(index) }),
  );
  const card = {
    kind: "run",
    schema_version: "1.0",
    run_id: RUN,
    recipe: { id: "evil", path: "cases/evil.yaml", sha256: "e".repeat(64) },
    git_sha: "c".repeat(40),
    git_dirty: false,
    runner_version: "0.1.0",
    created: "2026-10-11T08:30:00Z",
    profile: "laptop-rtx5000ada",
    seed: 1,
    published: true,
    launcher: "uv",
    gpu: {
      backend: "nvml",
      index: 0,
      name: `${PAYLOADS.svg}${PAYLOADS.control}`,
      driver: "1.0",
      vram_total_bytes: 17171480576,
      power_limit_enforced_w: 175,
    },
    stages: [],
    artefacts: [],
    notes: [PAYLOADS.script, PAYLOADS.js, PAYLOADS.long],
  };
  await page.route(`**/assets/runs/${RUN}/manifest.json`, (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(card) }),
  );
  return { dialogs, errors };
}

const noExecution = async (page: Page, seen: { dialogs: string[]; errors: string[] }) => {
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
  expect(seen.dialogs).toEqual([]);
  expect(seen.errors).toEqual([]);
  await expect(page.locator("main img[src='x'], main svg[onload], main script")).toHaveCount(0);
};

test.describe("hostile strings on the studio pages (FR-019-40)", () => {
  test("FR-019-40 · a tool page shows a hostile attribution as escaped text, cut at 200 characters, with an expander", async ({
    page,
  }) => {
    const seen = await hostile(page);
    await open(page, "studio/tools/warp/");
    const card = page.locator('article[data-artefact="warp-evil"]');
    await expect(card).toBeVisible({ timeout: 15_000 });
    const text = card.getByTestId("safe-text").first();
    await expect(text).toHaveAttribute("data-truncated", "true");
    const value = (await text.getByTestId("safe-text-value").textContent()) ?? "";
    expect([...value].length).toBe(201);
    expect(value.startsWith(PAYLOADS.img)).toBe(true);
    await text.getByTestId("expand").click();
    await expect(text.getByTestId("expand")).toHaveAttribute("aria-expanded", "true");
    expect(((await text.getByTestId("safe-text-value").textContent()) ?? "").length).toBeGreaterThan(20_000);
    await noExecution(page, seen);
  });

  test("FR-019-40 · a run page shows hostile GPU names and notes as escaped text and executes nothing", async ({
    page,
  }) => {
    const seen = await hostile(page);
    await open(page, `studio/runs/${RUN}/`);
    await expect(page.locator("main h1")).toBeVisible();
    await expect(page.getByTestId("safe-text").first()).toBeVisible({ timeout: 15_000 });
    const all = await page.locator("main").innerText();
    expect(
      [...all].some((c) => {
        const n = c.codePointAt(0) ?? 0;
        return (
          (n < 0x20 && n !== 0x09 && n !== 0x0a) || (n >= 0x7f && n <= 0x9f) || (n >= 0x202a && n <= 0x202e)
        );
      }),
    ).toBe(false);
    expect(all.length).toBeLessThan(40_000);
    await noExecution(page, seen);
  });

  test("FR-019-40 · the runs ledger and the GPU page survive the same fixture", async ({ page }) => {
    const seen = await hostile(page);
    for (const route of ["studio/runs/", "studio/gpu/", "studio/"]) {
      await open(page, route);
      await expect(page.locator("main h1")).toBeVisible();
      await page.waitForLoadState("networkidle");
    }
    await noExecution(page, seen);
  });

  test("FR-019-40 · a hostile string is never injected as HTML into the document", async ({ page }) => {
    const seen = await hostile(page);
    await open(page, "studio/tools/warp/");
    await expect(page.locator('article[data-artefact="warp-evil"]')).toBeVisible({ timeout: 15_000 });
    const html = await page.content();
    expect(html).not.toContain(`<img src=x onerror="window.__pwned=1">`);
    expect(html).not.toContain("<script>window.__pwned=1</script>");
    await noExecution(page, seen);
  });
});
