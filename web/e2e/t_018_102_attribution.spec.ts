// T-018-102 · FR-018-79 in a real browser: on the 12 case pages, in English and Spanish, an attribution line under a visual names as
// used only a tool or method that a published run of the case names (the render tools never), a not-run value carries no "used" claim
// and no unit after the not-run text. The expected sets are read from the published run manifests and summaries, never typed.
// Run against a deployed site with LIVE_URL=https://host/ (it must end with a slash).
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const CASES = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const LANGS = {
  en: { used: "Used in the published result", notRun: "Not yet run" },
  es: { used: "Usado en el resultado publicado", notRun: "Aún no ejecutado" },
} as const;
const TABS = ["scene", "simulate", "charts"] as const;

if (process.env.LIVE_URL) test.use({ baseURL: process.env.LIVE_URL });

interface RunTruth {
  verdict: string;
  tools: Set<string>;
  methods: Set<string>;
}
async function readTruth(request: APIRequestContext): Promise<Record<string, RunTruth[]>> {
  const index = await (await request.get("assets/manifest.json")).json();
  const byCase: Record<string, RunTruth[]> = Object.fromEntries(CASES.map((c) => [c, []]));
  for (const a of (
    index.artefacts as Array<{ id: string; run_id: string; path: string; cases?: string[] }>
  ).filter((x) => x.id.endsWith("-results"))) {
    const summary = await (await request.get(a.path)).json();
    const manifest = await (await request.get(`assets/runs/${a.run_id}/manifest.json`)).json();
    const run: RunTruth = {
      verdict: summary.verdict ?? "ok",
      tools: new Set((manifest.stages ?? []).map((s: { tool?: string }) => s.tool).filter(Boolean)),
      methods: new Set(summary.methods ?? []),
    };
    for (const c of a.cases ?? []) byCase[c]?.push(run);
  }
  return byCase;
}

async function render(page: Page, id: string, tab: string, lang: string): Promise<void> {
  await open(page, `cases/${id}/?tab=${tab}&lang=${lang}`);
  await expect(page.getByTestId("case-question")).toBeVisible();
  await expect(page.getByTestId("scene-render")).toHaveCount(1);
  await expect(page.locator('[data-visual="kpi"]').first()).toBeVisible();
}

test.describe("truthful attribution and not-run values (FR-018-79)", () => {
  let truth: Record<string, RunTruth[]>;
  test.beforeAll(async ({ playwright, baseURL }) => {
    const ctx = await playwright.request.newContext({ baseURL });
    truth = await readTruth(ctx);
    await ctx.dispose();
  });

  for (const lang of ["en", "es"] as const)
    for (const id of CASES) {
      test(`FR-018-79 · ${id} · ${lang} · no used claim under a not-run value, no unit after it, every used part is in a published run`, async ({
        page,
      }) => {
        const words = LANGS[lang];
        const runs = (truth[id] ?? []).filter((r) => r.verdict !== "failed");
        const runTools = new Set(runs.flatMap((r) => [...r.tools]));
        const runMethods = new Set(runs.flatMap((r) => [...r.methods]));
        for (const tab of TABS) {
          await render(page, id, tab, lang);

          // a not-run KPI row: the not-run text alone, no unit after it
          const rows = page.locator('[data-visual="kpi"] [data-kpi]');
          let fed = 0;
          for (const row of await rows.all()) {
            const value = (await row.locator("td").first().innerText()).trim();
            if (value.startsWith(words.notRun)) expect(value).toBe(words.notRun);
            else fed += 1;
          }
          // the KPI line under a table with no value fed never says used
          const kpiLine = page.locator('[data-visual="kpi"] [data-producer="kpi"]');
          if (fed === 0) await expect(kpiLine.filter({ hasText: words.used })).toHaveCount(0);

          // the scene caption: not used while the terrain tiles are not run
          const scene = page.locator('[data-visual="scene"]').first();
          if ((await scene.count()) > 0 && (await scene.innerText()).includes(words.notRun))
            await expect(
              scene.locator('[data-producer="scene"]').filter({ hasText: words.used }),
            ).toHaveCount(0);

          // every line that says used names only chips of a published run of the case (the render tools never)
          const chips = await page
            .getByTestId("built-with")
            .locator("[data-chip]")
            .evaluateAll((els) =>
              els.map((e) => ({
                id: e.getAttribute("data-chip") as string,
                group: e.closest("[data-group]")?.getAttribute("data-group") as string,
                text: (e.querySelector("a")?.textContent ?? "").trim(),
              })),
            );
          const lines = await page.locator("[data-producer]").allInnerTexts();
          for (const line of lines) {
            const at = line.indexOf(words.used);
            if (at < 0) continue;
            const usedPart = line.slice(0, at);
            for (const c of chips.filter((x) => x.text.length > 0 && usedPart.includes(x.text))) {
              const known = c.group === "methods" ? runMethods.has(c.id) : runTools.has(c.id);
              expect(known, `${c.id} is named used in "${line}" but no published run of ${id} names it`).toBe(
                true,
              );
            }
          }
        }
      });
    }
});
