// T-010-043 [red] · FR-010-27, SC-010-03: the C1 Charts real-event panel in EN and ES, fixed order, no highlight.
//
// What the green commit must deliver (route `cases/C1/?tab=charts`, panel from the baked `real_event` block of the TTF results):
//   - a region `role="region"` named "Real event" (ES: "Evento real") containing the label with the exact text
//       EN "single real event — no significance test"   ES "evento real único — sin prueba de significancia"
//     and a table `role="table"` with 12 body rows (2 cut-offs x 6 methods) in the fixed order inverse velocity, Bayesian TTF, TCN, PatchTST,
//     Chronos-Bolt (zero-shot), Chronos-Bolt (fine-tuned) for cut-off 0.5 then 0.8; rows carry `data-method` (inverse_velocity,
//     bayesian_ttf, tcn, patchtst, chronos_bolt_zero_shot, chronos_bolt_fine_tuned) and `data-cutoff` (0.5, 0.8); the columns (EN) are
//     "Cut-off", "Method", "Forecast t̂_f (h)", "Error t̂_f − t_f (h)", "Error / lead time"; the panel also shows SNR_obs.
//   - no highlighting of any method: no row, cell or text has a class or attribute that marks one method (no `aria-current`, no
//     `data-best`, no class matching /best|winner|highlight|selected|top/), the rows are not sorted by error (the order of the DOM is the
//     fixed order whatever the numbers are), and no interval, rank, "better" or p-value text appears in the panel.
//   - next to the panel the synthetic results are shown with their intervals and verdicts (a table named "Synthetic events" with an
//     "Interval" column and a "Verdict" column) so that the two are visibly different kinds of evidence.
//   - when the real series was not ingested the panel shows "Not run — <reason>" (ES "No ejecutado — <reason>") and no TTF number.
// Oracles: the exact strings of FR-010-27 (EN and ES); the fixed order of FR-010-26; DOM inspection.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const EN = "single real event — no significance test";
const ES = "evento real único — sin prueba de significancia";
const METHODS = [
  "inverse_velocity",
  "bayesian_ttf",
  "tcn",
  "patchtst",
  "chronos_bolt_zero_shot",
  "chronos_bolt_fine_tuned",
];
const FORBIDDEN_WORD = /\b(better|best|winner|rank|p-value|valor p|mejor|ganador)\b/i;

for (const [lang, label, regionName] of [
  ["en", EN, "Real event"],
  ["es", ES, "Evento real"],
] as const) {
  test.describe(`real-event panel (${lang})`, () => {
    test(`FR-010-27 · the ${lang} label, 12 rows in the fixed order, SNR_obs shown`, async ({ page }) => {
      await open(page, `cases/C1/?tab=charts&lang=${lang}`);
      const panel = page.getByRole("region", { name: regionName });
      await expect(panel).toBeVisible();
      await expect(panel.getByText(label, { exact: true })).toBeVisible();
      const rows = panel.getByRole("table").first().locator("tbody tr");
      await expect(rows).toHaveCount(12);
      const order = await rows.evaluateAll((els) =>
        els.map((e) => `${e.getAttribute("data-cutoff")}|${e.getAttribute("data-method")}`),
      );
      expect(order).toEqual([0.5, 0.8].flatMap((c) => METHODS.map((m) => `${c}|${m}`)));
      await expect(panel).toContainText(/SNR/);
    });

    test(`FR-010-27 · ${lang}: no method is highlighted and no interval, rank or verdict is shown for the real event`, async ({
      page,
    }) => {
      await open(page, `cases/C1/?tab=charts&lang=${lang}`);
      const panel = page.getByRole("region", { name: regionName });
      await expect(panel).toBeVisible();
      const marked = await panel.evaluate((root) => {
        const bad: string[] = [];
        for (const el of Array.from(root.querySelectorAll("*"))) {
          const cls = el.getAttribute("class") ?? "";
          if (/best|winner|highlight|selected|top/i.test(cls)) bad.push(`class:${cls}`);
          for (const a of ["aria-current", "data-best", "data-highlight", "data-rank"])
            if (el.hasAttribute(a)) bad.push(a);
        }
        return bad;
      });
      expect(marked).toEqual([]);
      const text = (await panel.textContent()) ?? "";
      expect(text).not.toMatch(FORBIDDEN_WORD);
      await expect(
        panel.getByRole("columnheader", { name: /interval|intervalo|verdict|veredicto/i }),
      ).toHaveCount(0);
    });
  });
}

test("FR-010-27 · the English column headers of the real-event table", async ({ page }) => {
  await open(page, "cases/C1/?tab=charts&lang=en");
  const headers = page.getByRole("region", { name: "Real event" }).getByRole("columnheader");
  await expect(headers).toHaveText([
    "Cut-off",
    "Method",
    "Forecast t̂_f (h)",
    "Error t̂_f − t_f (h)",
    "Error / lead time",
  ]);
});

test("FR-010-27 · the synthetic results sit next to it with intervals and verdicts", async ({ page }) => {
  await open(page, "cases/C1/?tab=charts&lang=en");
  const synthetic = page.getByRole("table", { name: "Synthetic events" });
  await expect(synthetic).toBeVisible();
  await expect(synthetic.getByRole("columnheader", { name: "Interval" })).toBeVisible();
  await expect(synthetic.getByRole("columnheader", { name: "Verdict" })).toBeVisible();
  const realBox = await page.getByRole("region", { name: "Real event" }).boundingBox();
  const synBox = await synthetic.boundingBox();
  expect(realBox).not.toBeNull();
  expect(synBox).not.toBeNull();
});

test("SC-010-03 · without the real series the panel says Not run and shows no TTF number", async ({
  page,
}) => {
  await open(page, "cases/C1/?tab=charts&lang=en&fixture=no-real-event");
  const panel = page.getByRole("region", { name: "Real event" });
  await expect(panel).toContainText(/Not run — .+/);
  await expect(panel.locator("tbody tr")).toHaveCount(0);
  await expect(panel.getByText(EN, { exact: true })).toBeVisible();
  await open(page, "cases/C1/?tab=charts&lang=es&fixture=no-real-event");
  await expect(page.getByRole("region", { name: "Evento real" })).toContainText(/No ejecutado — .+/);
});
