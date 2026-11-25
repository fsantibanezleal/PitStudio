// T-018-050 [red] · FR-018-63: if the parity report of the deployed commit (DC-018-05, `<base>assets/parity-report.json`) marks an
// engine as failing or does not list it, that engine runs in T0 and shows "parity not confirmed — showing precomputed results"
// instead of the LIVE badge. Unit half: web/src/engines/t_018_050_registry.test.ts.
//
// Hooks: web/e2e/support/simulate.ts (engine panels: data-state, lane-badge, engine-notice). The report is served with page.route;
// it is the valid example of the spec (contracts/examples/parity-report.valid.json) edited by hand. Case C1 has the TypeScript
// engine geotech and the ORT-web engine forecasters; the example report lists geotech (pass) and not forecasters.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page, test } from "@playwright/test";
import { enginePanel, openSimulate } from "./support/simulate";

const NOTICE = "parity not confirmed — showing precomputed results";
const EXAMPLE = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../specs/018-web-cases/contracts/examples/parity-report.valid.json",
);
const baseReport = () =>
  JSON.parse(readFileSync(EXAMPLE, "utf8")) as { engines: Array<{ engine: string; verdict: string }> };

async function serveReport(page: Page, body: string, status = 200): Promise<void> {
  await page.route("**/assets/parity-report.json", (route) =>
    route.fulfill({ status, contentType: "application/json", body }),
  );
}

test.describe("parity gate on the case page (FR-018-63)", () => {
  test("FR-018-63 · a passing engine is LIVE and a listed-nowhere engine is REPLAY with the notice", async ({
    page,
  }) => {
    await serveReport(page, JSON.stringify(baseReport()));
    await openSimulate(page, "C1", "&tier=t2");
    const geotech = enginePanel(page, "geotech");
    await expect(geotech.getByTestId("lane-badge")).toHaveText("LIVE", { timeout: 60_000 });
    await expect(geotech.getByTestId("engine-notice")).toHaveCount(0);
    const forecasters = enginePanel(page, "forecasters");
    await expect(forecasters.getByTestId("lane-badge")).toHaveText("REPLAY", { timeout: 60_000 });
    await expect(forecasters.getByTestId("engine-notice")).toContainText(NOTICE);
    await expect(forecasters).toHaveAttribute("data-state", "replay");
  });

  test("FR-018-63 · an engine marked failing in the report runs in T0 and shows the notice", async ({
    page,
  }) => {
    const report = baseReport();
    for (const e of report.engines) if (e.engine === "geotech") e.verdict = "fail";
    await serveReport(page, JSON.stringify(report));
    await openSimulate(page, "C1", "&tier=t2");
    const geotech = enginePanel(page, "geotech");
    await expect(geotech.getByTestId("lane-badge")).toHaveText("REPLAY", { timeout: 60_000 });
    await expect(geotech.getByTestId("engine-notice")).toContainText(NOTICE);
    await expect(geotech).toHaveAttribute("data-tier", "t0");
    await expect(geotech).toHaveAttribute("data-requests", "0");
  });

  test("FR-018-63 · an engine whose verdict is not_run (swe) is not LIVE", async ({ page }) => {
    await serveReport(page, JSON.stringify(baseReport()));
    await openSimulate(page, "C2", "&tier=t1");
    await expect(enginePanel(page, "swe").getByTestId("lane-badge")).toHaveText("REPLAY");
  });

  test("FR-018-63 · a missing report (HTTP 404) confirms nothing: every engine is REPLAY, no error is raised", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await serveReport(page, "not found", 404);
    await openSimulate(page, "C1", "&tier=t2");
    for (const id of ["geotech", "forecasters"]) {
      await expect(enginePanel(page, id).getByTestId("lane-badge")).toHaveText("REPLAY", { timeout: 60_000 });
      await expect(enginePanel(page, id).getByTestId("engine-notice")).toContainText(NOTICE);
    }
    expect(errors).toEqual([]);
  });

  test("FR-018-63 · a malformed report (not JSON, wrong shape) confirms nothing and raises no error", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await serveReport(page, '{"engines": [{"engine": "geotech", "verdict": "pass"');
    await openSimulate(page, "C1", "&tier=t2");
    await expect(enginePanel(page, "geotech").getByTestId("lane-badge")).toHaveText("REPLAY", {
      timeout: 60_000,
    });
    await page.unroute("**/assets/parity-report.json");
    await serveReport(page, JSON.stringify({ engines: "geotech" }));
    await page.reload();
    await expect(enginePanel(page, "geotech").getByTestId("lane-badge")).toHaveText("REPLAY", {
      timeout: 60_000,
    });
    expect(errors).toEqual([]);
  });

  test("FR-018-63 · the build ships a parity report of its own, and without a passing verdict the page never shows LIVE", async ({
    request,
    baseURL,
  }) => {
    const res = await request.get(new URL("assets/parity-report.json", baseURL as string).toString());
    expect(res.status(), "the Pages artifact holds assets/parity-report.json (DC-018-05)").toBe(200);
    const report = (await res.json()) as { engines: unknown[] };
    expect(Array.isArray(report.engines)).toBe(true);
    expect(report.engines.length).toBeGreaterThan(0);
  });
});
