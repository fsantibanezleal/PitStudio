// T-015-063 [red] · FR-015-41, FR-015-07, FR-015-42 (E2E half) on the production build: the Cosmos reason panels.
//
// Spec: specs/015-vlm/spec.md
//   FR-015-41  every web panel, card, chart and results table that shows a Cosmos output or metric shows "Built on NVIDIA Cosmos" and
//              "Zero-shot 2B VLM; not a safety system.", and shows wrong answers as well as right ones.
//   FR-015-07  without the gated terms every Cosmos arm is "not run": the Cosmos panels and the Cosmos tool page show "not run".
//   FR-015-42  no Cosmos metric among the headline KPIs (Explore KPIs and case KPI tiles).
//   FR-015-43  (the DOM half of the unit test web/src/features/reason/records-hostile.test.ts) a baked record file that fails its digest
//              shows "answers unavailable" and none of its text.
//
// Contract the green commit must deliver (assumptions are written here because spec 015 does not fix the page layout; flagged for the maintainer):
//   - Cases B1 (hazard questions) and B2 (captions) carry a reason panel `[data-testid="reason-panel"]` in their "Charts" tab
//     (`<base>cases/<ID>/?tab=charts`), with a heading that names "Cosmos Reason 2".
//   - The panel reads, at run time, the baked answer records `<base>reason/<ID>/records.json` (a `vlm-record` document) and the lower-case hex
//     SHA-256 of that file's bytes in `<base>reason/<ID>/records.sha256` (hex only), and verifies the digest and the schema in the browser
//     (`~/features/reason/records`).
//   - No such files are published in the committed build: the panel then has `data-reason-state="not-run"`, shows the text "not run"
//     (case-insensitive), and renders no `[data-reason-record]`.
//   - With verified records the panel has `data-reason-state="records"`, shows the two notices, and renders one `[data-reason-record]` card per
//     record containing the question, the full output, the parsed answer, the truth and a badge `[data-correct="true" | "false"]`; wrong answers are
//     shown exactly as right ones are.
//   - With a digest mismatch or a schema failure it has `data-reason-state="unavailable"`, shows exactly the text "answers unavailable", and none of the
//     file's text.
//   - The Studio page `<base>studio/` lists the tool as `[data-tool="cosmos-reason-2"]` whose text contains "not run" while no Cosmos run is published.
//   - The Results page `<base>results/?tab=cosmos` shows the two notices whenever a `[data-comparison-row]` is on the tab.
//   - The Explore KPI panel (`<base>?case=B1`) and the case KPI tiles hold no Cosmos metric.
// Oracles: the spec's valid record example (`specs/015-vlm/contracts/examples/vlm-record.valid.json`) with its digest computed here; a corrupted copy
// with a planted canary; the metric names of the metrics contract.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const EXAMPLE = readFileSync(
  resolve(process.cwd(), "../specs/015-vlm/contracts/examples/vlm-record.valid.json"),
  "utf8",
);
const DIGEST = createHash("sha256").update(EXAMPLE, "utf8").digest("hex");
const DOC = JSON.parse(EXAMPLE) as {
  records: { question: string; output: string; parsed: string; truth: string; correct: boolean }[];
};
const COSMOS = "Built on NVIDIA Cosmos";
const HONESTY = "Zero-shot 2B VLM; not a safety system.";
const CANARY = "PWNED-CANARY-7f3a";
const CASES = ["B1", "B2"] as const;

async function serve(page: Page, id: string, records: string, digest: string): Promise<void> {
  await page.route(`**/reason/${id}/records.json`, (r) =>
    r.fulfill({ status: 200, contentType: "application/json", body: records }),
  );
  await page.route(`**/reason/${id}/records.sha256`, (r) =>
    r.fulfill({ status: 200, contentType: "text/plain", body: digest }),
  );
}

test.describe("Cosmos panels without published records (FR-015-07)", () => {
  for (const id of CASES) {
    test(`FR-015-07 · the panel of case ${id} reads "not run" and shows no answer card`, async ({ page }) => {
      await open(page, `cases/${id}/?tab=charts`);
      const panel = page.getByTestId("reason-panel");
      await expect(panel).toBeVisible();
      await expect(panel).toContainText("Cosmos Reason 2");
      await expect(panel).toHaveAttribute("data-reason-state", "not-run");
      await expect(panel).toContainText(/not run/i);
      await expect(panel.locator("[data-reason-record]")).toHaveCount(0);
    });
  }

  test("FR-015-07 · the Cosmos tool on the Studio page reads 'not run'", async ({ page }) => {
    await open(page, "studio/");
    const tool = page.locator('[data-tool="cosmos-reason-2"]');
    await expect(tool).toHaveCount(1);
    await expect(tool).toContainText(/not run/i);
  });
});

test.describe("Cosmos panels with published records (FR-015-41)", () => {
  for (const id of CASES) {
    test(`FR-015-41 · case ${id}: notices, every record with its question, output, parsed answer and truth, wrong answers as well as right ones`, async ({
      page,
    }) => {
      await serve(page, id, EXAMPLE, DIGEST);
      await open(page, `cases/${id}/?tab=charts`);
      const panel = page.getByTestId("reason-panel");
      await expect(panel).toHaveAttribute("data-reason-state", "records");
      await expect(panel).toContainText(COSMOS);
      await expect(panel).toContainText(HONESTY);
      const cards = panel.locator("[data-reason-record]");
      await expect(cards).toHaveCount(DOC.records.length);
      for (const [i, rec] of DOC.records.entries()) {
        const card = cards.nth(i);
        await expect(card).toContainText(rec.question);
        await expect(card).toContainText(rec.output);
        await expect(card).toContainText(rec.parsed);
        await expect(card).toContainText(rec.truth);
        await expect(card.locator(`[data-correct="${rec.correct}"]`)).toHaveCount(1);
      }
      expect(DOC.records.some((r) => r.correct) && DOC.records.some((r) => !r.correct)).toBe(true);
      await expect(panel.locator('[data-correct="false"]').first()).toBeVisible();
      await expect(panel.locator('[data-correct="true"]').first()).toBeVisible();
      await expect(panel).not.toContainText("answers unavailable");
    });
  }

  test("FR-015-41 · record text is rendered as text, never as markup", async ({ page }) => {
    const doc = JSON.parse(EXAMPLE) as { records: { output: string }[] };
    const first = doc.records[0];
    if (!first) throw new Error("the example has no record");
    first.output = '<img src=x onerror="window.__pwned=1"><b id="injected">bold</b>';
    const body = JSON.stringify(doc);
    await serve(page, "B1", body, createHash("sha256").update(body, "utf8").digest("hex"));
    await open(page, "cases/B1/?tab=charts");
    const panel = page.getByTestId("reason-panel");
    await expect(panel).toHaveAttribute("data-reason-state", "records");
    await expect(panel.locator("#injected")).toHaveCount(0);
    await expect(panel.locator("img[src='x']")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
    await expect(panel).toContainText('<img src=x onerror="window.__pwned=1">');
  });

  test("FR-015-43 · a record file whose digest does not match shows 'answers unavailable' and none of its text", async ({
    page,
  }) => {
    const tampered = EXAMPLE.replace('"<answer>no</answer>"', `"${CANARY}"`);
    expect(tampered).not.toBe(EXAMPLE);
    await serve(page, "B1", tampered, DIGEST);
    await open(page, "cases/B1/?tab=charts");
    const panel = page.getByTestId("reason-panel");
    await expect(panel).toHaveAttribute("data-reason-state", "unavailable");
    await expect(panel).toContainText("answers unavailable");
    await expect(panel).not.toContainText(CANARY);
    for (const rec of DOC.records) await expect(panel).not.toContainText(rec.question);
    await expect(panel.locator("[data-reason-record]")).toHaveCount(0);
  });

  test("FR-015-43 · a record file that fails its schema shows 'answers unavailable' even with a matching digest", async ({
    page,
  }) => {
    const doc = JSON.parse(EXAMPLE) as { records: Record<string, unknown>[] };
    doc.records[0] = { ...doc.records[0], output: CANARY, licence_class: "own" };
    const body = JSON.stringify(doc);
    await serve(page, "B2", body, createHash("sha256").update(body, "utf8").digest("hex"));
    await open(page, "cases/B2/?tab=charts");
    const panel = page.getByTestId("reason-panel");
    await expect(panel).toHaveAttribute("data-reason-state", "unavailable");
    await expect(panel).toContainText("answers unavailable");
    await expect(panel).not.toContainText(CANARY);
  });
});

test.describe("Cosmos metrics are never headline KPIs (FR-015-42)", () => {
  const COSMOS_WORDS = /cosmos|vlm|chair|hallucinat|mcnemar|qwen/i;

  for (const id of CASES) {
    test(`FR-015-42 · the Explore KPI panel of ${id} holds no Cosmos metric, also with records published`, async ({
      page,
    }) => {
      await serve(page, id, EXAMPLE, DIGEST);
      await open(page, `?case=${id}`);
      const panel = page.getByTestId("kpi-panel");
      await expect(panel).toHaveAttribute("data-case", id);
      const rows = panel.locator("[data-kpi]");
      const n = await rows.count();
      expect(n).toBeGreaterThan(0);
      for (let i = 0; i < n; i++) {
        const row = rows.nth(i);
        expect(await row.getAttribute("data-kpi")).not.toMatch(COSMOS_WORDS);
        expect((await row.textContent()) ?? "").not.toMatch(COSMOS_WORDS);
      }
    });

    test(`FR-015-42 · the KPI tiles of the case page ${id} hold no Cosmos metric`, async ({ page }) => {
      await serve(page, id, EXAMPLE, DIGEST);
      await open(page, `cases/${id}/`);
      const kpis = page.locator("[data-kpi]");
      const n = await kpis.count();
      for (let i = 0; i < n; i++) {
        const k = kpis.nth(i);
        expect(await k.getAttribute("data-kpi")).not.toMatch(COSMOS_WORDS);
        expect((await k.textContent()) ?? "").not.toMatch(COSMOS_WORDS);
      }
    });
  }
});

test.describe("Cosmos results table (FR-015-41)", () => {
  test("FR-015-41 · the results tab 'Cosmos vs Qwen vs detector' shows both notices whenever it shows a comparison row", async ({
    page,
  }) => {
    await open(page, "results/?tab=cosmos");
    const rows = await page.locator("[data-comparison-row]").count();
    if (rows === 0) {
      await expect(page.getByRole("tabpanel")).toContainText(/not yet run|not run/i);
      return;
    }
    const panel = page.getByRole("tabpanel");
    await expect(panel).toContainText(COSMOS);
    await expect(panel).toContainText(HONESTY);
  });
});
