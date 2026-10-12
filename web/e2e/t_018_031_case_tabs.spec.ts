// T-018-031 [red] · FR-018-14 (Simulate tab: every engine of the registry runs on the active tier and updates the KPIs after each accepted input change; LIVE for a result
// computed in this browser, REPLAY for the T0 fallback) and FR-018-15 (Studio replay tab: artefact cards of the replay artefacts of the page's case, "Not yet run" otherwise).
// Unit half: web/src/routes/t_018_031_case_tabs.test.tsx.
//
// Hooks: web/e2e/support/simulate.ts (engine panels, lane badge, numeric controls with data-min / data-max, data-requests) and the KPI hooks of T-018-021/022
// (`[data-testid="kpi-panel"] [data-kpi]`); replay artefact cards are `article[data-artefact="<id>"]`. The parity report is served with page.route from the valid example of the spec
// (contracts/examples/parity-report.valid.json: blasting, geotech, mincut, des, gns pass) so the engines that pass run LIVE.
// Oracles: the EARS text; the engines of every case in the case registry example; hand-built manifest fixtures.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";
import { loadCaseRegistry, makeArtefact, makeWebIndex } from "../src/test-support/fixtures";
import { open } from "./helpers";
import { enginePanel, openSimulate } from "./support/simulate";

const registry = loadCaseRegistry();
const REPORT = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../specs/018-web-cases/contracts/examples/parity-report.valid.json",
);
const CASE_IDS = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
/** Cases whose headline KPIs come from a TypeScript engine that the example parity report lists as passing. */
const TS_LIVE: Array<[string, string]> = [
  ["A1", "des"],
  ["C1", "geotech"],
  ["D1", "blasting"],
  ["E1", "mincut"],
];

async function serveParity(page: Page): Promise<void> {
  await page.route("**/assets/parity-report.json", (route) =>
    route.fulfill({ contentType: "application/json", body: readFileSync(REPORT, "utf8") }),
  );
}

test.describe("Simulate tab (FR-018-14)", () => {
  for (const id of CASE_IDS) {
    test(`FR-018-14 · ${id}: the Simulate tab shows one engine panel per engine of the registry, in registry order`, async ({
      page,
    }) => {
      await openSimulate(page, id, "&tier=t2");
      const shown = await page
        .locator('[data-testid="engine-panel"]')
        .evaluateAll((els) => els.map((e) => e.getAttribute("data-engine")));
      expect(shown).toEqual((registry.cases[id] as { engines: string[] }).engines);
    });
  }

  for (const [id, engine] of TS_LIVE) {
    test(`FR-018-14 · ${id}: after an accepted change of a ${engine} input the engine runs again, the KPIs change, and the panel is LIVE`, async ({
      page,
    }) => {
      await serveParity(page);
      await openSimulate(page, id, "&tier=t2");
      const panel = enginePanel(page, engine);
      await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
      await expect(panel).toHaveAttribute("data-state", "done", { timeout: 60_000 });
      const kpis = page.locator('[data-testid="kpi-panel"] [data-kpi]');
      const before = (await kpis.allTextContents()).join("|");
      const requests = Number(await panel.getAttribute("data-requests"));
      const input = panel.locator("input[data-control]").first();
      const min = Number(await input.getAttribute("data-min"));
      const max = Number(await input.getAttribute("data-max"));
      const current = Number(await input.inputValue());
      await input.fill(
        String(Math.abs(current - (min + max) / 2) > 1e-9 ? (min + max) / 2 : min + (max - min) * 0.25),
      );
      await input.press("Enter");
      await expect
        .poll(async () => Number(await panel.getAttribute("data-requests")), { timeout: 30_000 })
        .toBeGreaterThan(requests);
      await expect
        .poll(async () => (await kpis.allTextContents()).join("|"), { timeout: 30_000 })
        .not.toBe(before);
      await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE");
    });
  }

  test("FR-018-14 · on tier T0 every panel shows its baked result with the REPLAY badge and computes nothing", async ({
    page,
  }) => {
    await serveParity(page);
    await openSimulate(page, "A1", "&tier=t0");
    for (const engine of (registry.cases.A1 as { engines: string[] }).engines) {
      const panel = enginePanel(page, engine);
      await expect(panel.getByTestId("lane-badge")).toHaveText("REPLAY");
      await expect(panel).toHaveAttribute("data-tier", "t0");
      await expect(panel).toHaveAttribute("data-requests", "0");
    }
  });

  test("FR-018-14 · the badge follows what is shown: LIVE and REPLAY never appear together in one panel", async ({
    page,
  }) => {
    await serveParity(page);
    await openSimulate(page, "C1", "&tier=t2");
    for (const engine of (registry.cases.C1 as { engines: string[] }).engines) {
      const badges = await enginePanel(page, engine).getByTestId("lane-badge").allTextContents();
      expect(badges).toHaveLength(1);
      expect(["LIVE", "REPLAY"]).toContain(badges[0]);
    }
  });
});

test.describe("Studio replay tab (FR-018-15)", () => {
  const manifest = makeWebIndex([
    makeArtefact({ id: "c2-flood-arrival", cases: ["C2"], lane: "replay" }),
    makeArtefact({ id: "c2-flood-depth", cases: ["C2"], lane: "replay" }),
    makeArtefact({ id: "c2-live-chart", cases: ["C2"], lane: "live" }),
    makeArtefact({ id: "c2-poster", cases: ["C2"], lane: "static", kind: "image", budget_class: "own-code" }),
    makeArtefact({ id: "c3-replay-dust", cases: ["C3"], lane: "replay" }),
    makeArtefact({ id: "shared-replay", cases: ["C2", "C3"], lane: "replay" }),
  ]);
  const serve = (page: Page) =>
    page.route("**/assets/manifest.json", (route) =>
      route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }),
    );

  test("FR-018-15 · /cases/C2/?tab=replay lists exactly the replay artefacts that name C2 as cards", async ({
    page,
  }) => {
    await serve(page);
    await open(page, "cases/C2/?tab=replay");
    const ids = page.locator("article[data-artefact]");
    await expect(ids).toHaveCount(3);
    const shown = await ids.evaluateAll((els) => els.map((e) => e.getAttribute("data-artefact")).sort());
    expect(shown).toEqual(["c2-flood-arrival", "c2-flood-depth", "shared-replay"]);
    for (const card of await ids.all())
      await expect(card.locator('[data-lane="replay"]')).toHaveText("REPLAY");
  });

  test("FR-018-15 · a case with no replay artefact says 'Not yet run' and shows no card", async ({
    page,
  }) => {
    await serve(page);
    await open(page, "cases/D2/?tab=replay");
    await expect(page.getByRole("tabpanel")).toContainText("Not yet run");
    await expect(page.locator("article[data-artefact]")).toHaveCount(0);
  });

  test("FR-018-15 · with no published manifest every case's replay tab says 'Not yet run'", async ({
    page,
  }) => {
    for (const id of CASE_IDS) {
      await open(page, `cases/${id}/?tab=replay`);
      await expect(page.getByRole("tabpanel")).toContainText("Not yet run");
      await expect(page.locator("article[data-artefact]")).toHaveCount(0);
    }
  });
});
