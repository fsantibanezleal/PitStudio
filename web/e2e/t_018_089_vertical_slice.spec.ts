// T-018-089 [red] · SC-018-02: the vertical slice A1 + C1 works end to end on the preview build before any NVIDIA-runtime work: DES, limit equilibrium, inverse velocity and the
// Bingham terrain, on the open lane. The pages must pass their E2E and parity tasks (the parity report must list their engines as passing).
//
// Hooks: web/e2e/support/simulate.ts (engine panels, lane badge, numeric controls with data-min / data-max, data-requests) and the Explore/KPI hooks of T-018-021/022
// (`[data-testid="kpi-panel"]`, `[data-kpi]`). Preview build = the production build served like Pages (scripts/serve-static.mjs), tier forced to T2 (CI has no GPU).
// Oracles: the EARS text of SC-018-02 and of FR-018-14 (LIVE badge for an output computed in this browser); the headline KPIs of A1 and C1 of the case registry example
// (A1 throughput, queue_time, match_factor, cost_per_tonne; C1 fos, pof, forecast_error, lead_time); the engines of the vertical slice (A1 des, haulage, lp; C1 geotech).
import { expect, type Page, test } from "@playwright/test";
import { enginePanel, openSimulate, recordRequests } from "./support/simulate";

async function change(page: Page, engine: string): Promise<{ before: number; after: number }> {
  const panel = enginePanel(page, engine);
  await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
  const before = Number(await panel.getAttribute("data-requests"));
  const input = panel.locator("input[data-control]").first();
  const min = Number(await input.getAttribute("data-min"));
  const max = Number(await input.getAttribute("data-max"));
  const current = Number(await input.inputValue());
  const target = Math.abs(current - (min + max) / 2) > 1e-9 ? (min + max) / 2 : min + (max - min) * 0.25;
  await input.fill(String(target));
  await input.press("Enter");
  await expect
    .poll(async () => Number(await panel.getAttribute("data-requests")), { timeout: 30_000 })
    .toBeGreaterThan(before);
  await expect(panel).toHaveAttribute("data-state", "done", { timeout: 30_000 });
  return { before, after: Number(await panel.getAttribute("data-requests")) };
}

test.describe("A1 (DES, haulage, LP) on the open lane (SC-018-02)", () => {
  test("SC-018-02 · /cases/A1/ page: Simulate computes the KPIs in the browser with the LIVE badge and a changed fleet size changes them", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await openSimulate(page, "A1", "&tier=t2");
    const kpis = page.locator('[data-testid="kpi-panel"] [data-kpi]');
    await expect(kpis.first()).toBeVisible();
    for (const id of ["throughput", "queue_time", "match_factor"])
      await expect(page.locator(`[data-kpi="${id}"]`)).not.toContainText("Not yet run", { timeout: 60_000 });
    const before = await kpis.allTextContents();
    await change(page, "des");
    await expect
      .poll(async () => (await kpis.allTextContents()).join("|"), { timeout: 30_000 })
      .not.toBe(before.join("|"));
    for (const id of ["des", "haulage"]) {
      await expect(enginePanel(page, id).getByTestId("lane-badge")).toHaveText("LIVE");
      await expect(enginePanel(page, id)).not.toContainText("parity not confirmed");
    }
    expect(errors).toEqual([]);
  });

  test("SC-018-02 · the A1 scene shows the real Bingham terrain from the LOD-0 tileset with its public-domain provenance and the STATIC badge", async ({
    page,
  }) => {
    await page.goto("cases/A1/?tab=scene&tier=t2");
    const chip = page.getByTestId("provenance-chip").first();
    await expect(chip).toContainText("usgs-3dep-bingham");
    await expect(chip).toContainText("public domain (US Government work)");
    await expect(chip).toContainText("STATIC");
  });
});

test.describe("C1 (limit equilibrium, inverse velocity) on the open lane (SC-018-02)", () => {
  test("SC-018-02 · /cases/C1/ page: the factor of safety is computed live by the geotech engine, changes with the section and keeps its LIVE badge", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const rec = recordRequests(page);
    await openSimulate(page, "C1", "&tier=t2");
    await expect(page.locator('[data-kpi="fos"]')).not.toContainText("Not yet run", { timeout: 60_000 });
    const before = await page.locator('[data-kpi="fos"]').textContent();
    await change(page, "geotech");
    await expect
      .poll(async () => page.locator('[data-kpi="fos"]').textContent(), { timeout: 30_000 })
      .not.toBe(before);
    await expect(enginePanel(page, "geotech").getByTestId("lane-badge")).toHaveText("LIVE");
    // the open lane needs no NVIDIA runtime and no loopback or foreign request
    expect(
      rec.urls().filter((u) => !u.startsWith(new URL(page.url()).origin) && !/^(data|blob):/.test(u)),
    ).toEqual([]);
    expect(errors).toEqual([]);
  });

  test("SC-018-02 · the inverse-velocity forecast of the C1 record is shown with its predicted failure time and a 'Run in Python' parity check that passes", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openSimulate(page, "C1", "&tier=t2");
    const panel = enginePanel(page, "geotech");
    await expect(panel.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    await expect(page.getByTestId("inverse-velocity")).toBeVisible();
    await expect(page.getByTestId("inverse-velocity")).toContainText(/\d/);
    await panel.getByRole("button", { name: "Run in Python" }).click();
    await expect(panel.getByTestId("python-result")).toHaveAttribute("data-verdict", "pass", {
      timeout: 60_000,
    });
  });
});

test.describe("the parity gate of the slice (SC-018-01, SC-018-02)", () => {
  test("SC-018-02 · the parity report of the build lists the slice's engines (des, haulage, lp, geotech) as passing", async ({
    request,
    baseURL,
  }) => {
    const res = await request.get(new URL("assets/parity-report.json", baseURL as string).toString());
    expect(res.status(), "assets/parity-report.json exists").toBe(200);
    const report = (await res.json()) as { engines: Array<{ engine: string; verdict: string }> };
    for (const id of ["des", "haulage", "lp", "geotech"]) {
      const entries = report.engines.filter((e) => e.engine === id);
      expect(entries.length, id).toBeGreaterThan(0);
      for (const e of entries) expect(e.verdict, id).toBe("pass");
    }
  });
});
