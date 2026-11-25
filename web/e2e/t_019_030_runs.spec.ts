// T-019-030 [red] · FR-019-21 (/studio/runs lists only published runs, newest first, filterable by ?case= and ?tool=), FR-019-41 (hostile filters are ignored with the note "unknown filter ignored" and nothing is requested
// from their value) and FR-019-26 (a run id that is not a published run, unknown, local, malformed or traversing, answers HTTP 404 and requests no run asset). Unit half: web/src/studio/t_019_030_runs_ledger.test.tsx.
//
// The build under test holds the three fixture runs of web/e2e/support/studio-runs.ts (run A 2026-10-07T12:00Z, run B 2026-10-07T21:00Z, run BIG 2026-10-06T12:00Z). Hooks: see the unit half (table[data-testid="runs-table"], tr[data-run],
// td[data-col], [data-testid="filter-note"]).
// Oracles: the facts of the two fixture runs (hand transcription); HTTP status codes; the EARS text.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";
import { LEDGER_ORDER, RUN_A, RUN_B, RUN_BIG, RUNS, UNPUBLISHED_RUN } from "./support/studio-runs";

const rows = (page: import("@playwright/test").Page) =>
  page.locator('[data-testid="runs-table"] tr[data-run]');
const runIds = async (page: import("@playwright/test").Page) =>
  rows(page).evaluateAll((els) => els.map((e) => e.getAttribute("data-run")));

test.describe("the ledger (FR-019-21)", () => {
  test("FR-019-21 · lists exactly the three published runs, newest first, each linked to its page", async ({
    page,
  }) => {
    await open(page, "studio/runs/");
    expect(await runIds(page)).toEqual(LEDGER_ORDER);
    for (const id of LEDGER_ORDER) {
      await expect(page.locator(`tr[data-run="${id}"] a`).first()).toHaveAttribute(
        "href",
        new RegExp(`/studio/runs/${id}/?$`),
      );
    }
    await expect(page.getByTestId("no-runs")).toHaveCount(0);
  });

  test("FR-019-21 · each row shows its cases, producer tools, UTC date, determinism class and artefact count", async ({
    page,
  }) => {
    await open(page, "studio/runs/");
    for (const id of LEDGER_ORDER) {
      const fact = RUNS[id];
      const row = page.locator(`tr[data-run="${id}"]`);
      await expect(row.locator('td[data-col="date"]')).toHaveText(fact?.date ?? "");
      for (const c of fact?.cases ?? []) await expect(row.locator('td[data-col="cases"]')).toContainText(c);
      for (const t of fact?.artefact_tools ?? [])
        await expect(row.locator('td[data-col="tools"]')).toContainText(t);
      await expect(row.locator('td[data-col="artefacts"]')).toHaveText(String(fact?.artefacts.length));
      await expect(row.locator('td[data-col="determinism"]')).toContainText(/bitwise|statistical|none/);
    }
  });

  test("FR-019-21 · ?case=A2 keeps run A, ?case=C2 keeps run B, ?tool=warp keeps run B, ?tool=nvenc-ffmpeg keeps run A", async ({
    page,
  }) => {
    for (const [query, expected] of [
      ["?case=A2", [RUN_A]],
      ["?case=C2", [RUN_B]],
      ["?tool=warp", [RUN_B]],
      ["?tool=nvenc-ffmpeg", [RUN_A]],
      ["?case=C2&tool=warp", [RUN_B]],
      ["?case=A2&tool=warp", []],
      ["?case=E2", [RUN_BIG]],
      ["?tool=pytorch", [RUN_BIG]],
      ["?case=B1", []],
    ] as Array<[string, string[]]>) {
      await open(page, `studio/runs/${query}`);
      expect(await runIds(page), query).toEqual(expected);
      await expect(page.getByTestId("filter-note"), query).toHaveCount(0);
    }
  });

  test("FR-019-21 · no run card of an unpublished run is listed", async ({ page }) => {
    await open(page, "studio/runs/");
    await expect(page.locator(`tr[data-run="${UNPUBLISHED_RUN}"]`)).toHaveCount(0);
  });
});

test.describe("hostile filters (FR-019-41)", () => {
  const HOSTILE: Array<[string, string]> = [
    ["unknown case", "?case=zz-sentinel-5d1c"],
    ["markup as tool", `?tool=${encodeURIComponent("<script>window.__pwned=1</script>")}-sentinel-5d1c`],
    ["20,000 characters", `?case=${"s".repeat(20_000)}`],
    ["a known id padded beyond 2,000 characters", `?tool=warp${"%20".repeat(1100)}`],
    ["encoded separators", "?case=A2%2F..%2Fsentinel-5d1c"],
    ["a null byte", "?tool=warp%00sentinel-5d1c"],
  ];
  for (const [what, query] of HOSTILE) {
    test(`FR-019-41 · ${what}: ignored, all three runs listed, the note is shown, no uncaught error and no request derived from the value`, async ({
      page,
    }) => {
      const errors: string[] = [];
      const urls: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("request", (r) => {
        if (!r.isNavigationRequest())
          urls.push(decodeURIComponent(r.url().replace(/%(?![0-9a-f]{2})/gi, "%25")));
      });
      await open(page, `studio/runs/${query}`);
      expect(await runIds(page)).toEqual(LEDGER_ORDER);
      await expect(page.getByTestId("filter-note")).toContainText("unknown filter ignored");
      await page.waitForLoadState("networkidle");
      expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
      expect(errors).toEqual([]);
      expect(urls.filter((u) => /sentinel-5d1c|s{50}|%20{20}/.test(u))).toEqual([]);
    });
  }
});

test.describe("run ids that are not published runs (FR-019-26)", () => {
  for (const id of [RUN_A, RUN_B, RUN_BIG]) {
    test(`FR-019-26 · /studio/runs/${id}/ is a published run and answers 200`, async ({ request }) => {
      expect((await request.get(`studio/runs/${id}/`)).status()).toBe(200);
    });
  }

  const BAD: Array<[string, string]> = [
    ["a well-formed id that was never published", UNPUBLISHED_RUN],
    ["an unknown id", "no-such-run"],
    ["a local run (no publish)", "20261008T080000Z-local"],
    ["a published id with another case", `${RUN_A.toUpperCase()}`],
    ["a trailing space", `${RUN_A}%20`],
    ["an encoded slash", `${RUN_A}%2Fx`],
    ["a double-encoded separator", `${RUN_A}%252F${RUN_B}`],
    ["a backslash", `${RUN_A}%5Cx`],
    ["markup", "%3Cscript%3Ealert(1)%3C%2Fscript%3E"],
    ["a null byte", `${RUN_A}%00`],
    ["very long", "r".repeat(3000)],
  ];
  for (const [what, id] of BAD) {
    test(`FR-019-26 · ${what}: HTTP 404, the not-found page and no run asset requested`, async ({ page }) => {
      const urls: string[] = [];
      page.on("request", (r) => {
        if (!r.isNavigationRequest()) urls.push(r.url());
      });
      const res = await page.goto(`studio/runs/${id}/`);
      expect(res?.status()).toBe(404);
      await open(page, `studio/runs/${id}/`);
      await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
      await page.waitForLoadState("networkidle");
      expect(urls.filter((u) => /\/assets\/runs\//.test(new URL(u).pathname))).toEqual([]);
    });
  }
});
