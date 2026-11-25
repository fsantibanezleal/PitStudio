// T-018-101 · FR-018-74 to FR-018-78 in a real browser: the 12 case pages agree with the published run manifests. Whatever a page
// shows as published in one place (Published results card, KPI table, footer, Built with, Reproduce) is never "Not yet run" in
// another; a KPI is fed only through the explicit `kpi` field of a headline; the footer counts the published runs; a vendor mark
// is written once; the Omniverse and NVIDIA group is never empty. The expected values are read from the published files, never typed.
// Run against a deployed site with LIVE_URL=https://host/ (it must end with a slash).
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const CASES = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const NONE = "No data, models or simulation results are published yet.";

if (process.env.LIVE_URL) test.use({ baseURL: process.env.LIVE_URL });

interface Artefact {
  id: string;
  run_id: string;
  path: string;
  cases?: string[];
}
interface Headline {
  name: string;
  value: number;
  unit: string;
  kpi?: string;
}
interface Published {
  runId: string;
  verdict: string;
  headline: Headline[];
  partial: boolean;
  imported: boolean;
}
interface Truth {
  runCount: number;
  byCase: Record<string, Published[]>;
}

async function readTruth(request: APIRequestContext): Promise<Truth> {
  const index = await (await request.get("assets/manifest.json")).json();
  const artefacts: Artefact[] = index.artefacts;
  const runs = new Set<string>([
    ...index.runs.map((r: { run_id: string }) => r.run_id),
    ...artefacts.map((a) => a.run_id),
  ]);
  const byCase: Record<string, Published[]> = Object.fromEntries(CASES.map((c) => [c, []]));
  for (const a of artefacts.filter((x) => x.id.endsWith("-results"))) {
    const summary = await (await request.get(a.path)).json();
    const manifest = await (await request.get(`assets/runs/${a.run_id}/manifest.json`)).json();
    const notes: string[] = manifest.notes ?? [];
    for (const c of a.cases ?? []) {
      byCase[c]?.push({
        runId: a.run_id,
        verdict: summary.verdict ?? "ok",
        headline: summary.headline,
        partial: notes.some((n) => n.startsWith("partial:")),
        imported: manifest.profile === "imported",
      });
    }
  }
  return { runCount: runs.size, byCase };
}

async function openCase(page: Page, id: string): Promise<void> {
  await open(page, `cases/${id}/`);
  await expect(page.getByTestId("case-question")).toBeVisible();
  await expect(page.getByTestId("scene-render")).toHaveCount(1);
}

const num = (v: number) =>
  new Intl.NumberFormat("en", { maximumSignificantDigits: 4, useGrouping: false }).format(v);

test.describe("consistent case pages (FR-018-78)", () => {
  let truth: Truth;
  test.beforeAll(async ({ playwright, baseURL }) => {
    const ctx = await playwright.request.newContext({ baseURL });
    truth = await readTruth(ctx);
    await ctx.dispose();
    expect(truth.runCount).toBeGreaterThan(0);
  });

  for (const id of CASES) {
    test(`FR-018-78 · ${id} · the KPI table, the results card, the footer, Built with and Reproduce agree with the published runs`, async ({
      page,
    }) => {
      const published = truth.byCase[id] ?? [];
      await openCase(page, id);

      // KPI table (FR-018-74): a headline that names a KPI feeds exactly that row; every other row says Not yet run
      const kpiPanel = page.locator('[data-testid="kpi-panel"]').first();
      await expect(kpiPanel).toBeVisible();
      const fed = new Map<string, { value: number; run: Published }>();
      for (const run of [...published].sort((a, b) => a.runId.localeCompare(b.runId)))
        if (run.verdict !== "failed")
          for (const h of run.headline) if (h.kpi) fed.set(h.kpi, { value: h.value, run });
      const rows = kpiPanel.locator("[data-kpi]");
      const ids = await rows.evaluateAll((els) => els.map((e) => e.getAttribute("data-kpi") as string));
      expect(ids.length).toBeGreaterThan(0);
      for (const kpi of fed.keys()) expect(ids).toContain(kpi);
      for (const kpi of ids) {
        const row = kpiPanel.locator(`[data-kpi="${kpi}"]`);
        const f = fed.get(kpi);
        if (f) {
          await expect(row).toContainText(num(f.value));
          await expect(row).toContainText(f.run.runId);
          await expect(row).not.toContainText("Not yet run");
          await expect(row.locator(`a[href$="/studio/runs/${f.run.runId}/"]`)).toHaveCount(1);
          if (f.run.partial) await expect(row).toContainText("Partial provenance");
        } else {
          await expect(row).toContainText("Not yet run");
        }
      }

      // the Published results card shows every headline value of the case
      const card = page.getByTestId("published-results");
      if (published.length === 0) await expect(card).toHaveCount(0);
      for (const run of published)
        for (const h of run.headline)
          await expect(card.locator(`[data-result="${run.runId}"]`)).toContainText(String(h.value));

      // footer (FR-018-75)
      const footer = page.getByRole("contentinfo");
      await expect(footer).toContainText(`${truth.runCount} published runs`);
      await expect(footer).not.toContainText(NONE);

      // Built with (FR-018-76): the vendor once, a non-empty Omniverse and NVIDIA group, no empty "None listed" there
      const built = page.getByTestId("built-with");
      const omni = built.locator('[data-group="omniverse"]');
      expect(await omni.locator("[data-chip]").count()).toBeGreaterThan(0);
      await expect(omni).not.toContainText("None listed");
      expect(await page.locator("main").innerText()).not.toMatch(/NVIDIA\s+NVIDIA\s+(?!tools)/);
      for (const run of published.filter((r) => r.verdict !== "failed")) {
        const producer = page.locator(`[data-result="${run.runId}"] [data-producer="result"]`);
        await expect(producer).toContainText("Used in the published result");
      }

      // Reproduce (FR-018-77): a case with a published imported run never says "Not yet run" there
      const reproduce = page.locator("section[aria-labelledby='reproduce-title']");
      const imported = published.filter((r) => r.imported);
      if (imported.length > 0) {
        await expect(reproduce).not.toContainText("Not yet run");
        for (const run of imported) await expect(reproduce).toContainText(run.runId);
        if (imported.some((r) => r.partial)) await expect(reproduce).toContainText("Partial provenance");
      } else if (published.length === 0) {
        await expect(reproduce).toContainText(/Not yet run|studio plan/);
      }
    });
  }

  test("FR-018-76 · C1 · the Omniverse and NVIDIA group lists ovrtx as planned for RTX sensor simulation", async ({
    page,
  }) => {
    await openCase(page, "C1");
    const chip = page.getByTestId("built-with").locator('[data-group="omniverse"] [data-chip="ovrtx"]');
    await expect(chip).toHaveCount(1);
    await expect(chip).toHaveAttribute("data-nvidia", "true");
  });

  test("FR-018-75 · the footer and a KPI row are written in Spanish", async ({ page }) => {
    await open(page, "cases/C1/?lang=es");
    await expect(page.getByRole("contentinfo")).toContainText(`${truth.runCount} ejecuciones publicadas`);
    await expect(page.locator('[data-testid="kpi-panel"]').first().locator('[data-kpi="fos"]')).toContainText(
      "Aún no ejecutado",
    );
  });
});
