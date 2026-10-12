// T-018-052 [red] · FR-018-48 on the built artifact: the parity report (`<base>assets/parity-report.json`, DC-018-05) holds the verdicts
// of the owning suites of the hosted engines (specs 007, 013, 014), class "hosted" with the owning requirement, in Chromium, Firefox
// and WebKit. Unit half: web/src/engines/host/t_018_052_hosted_engines.test.ts.
//
// Oracles: the owning requirement per engine (list of FR-018-48); the entry shape of the spec's valid example report (a "hosted"
// entry has tolerance { class, defined_by }); the three browsers of SC-018-01. A hosted engine whose suite has not produced a
// verdict yet must still be LISTED (verdict not_run with a reason), otherwise FR-018-63 cannot show why it is replayed.
import { expect, test } from "@playwright/test";
import { enginePanel, openSimulate } from "../support/simulate";

const OWNER: Record<string, string> = {
  des: "FR-007-10",
  policies: "FR-007-32",
  haulage: "FR-007-15",
  lp: "FR-007-20",
  routing: "FR-007-39",
  "dust-lidar": "P-013-15",
  "il1-twin": "FR-014-42",
  "il2-twin": "FR-014-42",
};
const BROWSERS = ["chromium", "firefox", "webkit"];

interface Entry {
  engine: string;
  tolerance: { class: string; defined_by?: string };
  browsers: string[];
  verdict: string;
  reason?: string;
}

async function report(
  request: import("@playwright/test").APIRequestContext,
  baseURL: string,
): Promise<Entry[]> {
  const res = await request.get(new URL("assets/parity-report.json", baseURL).toString());
  expect(res.status(), "the Pages artifact holds assets/parity-report.json").toBe(200);
  return ((await res.json()) as { engines: Entry[] }).engines;
}

test.describe("hosted verdicts in the parity report (FR-018-48)", () => {
  test("FR-018-48 · the report lists each of the eight hosted engines once, with class hosted and the owning requirement", async ({
    request,
    baseURL,
  }) => {
    const engines = await report(request, baseURL as string);
    for (const [id, req] of Object.entries(OWNER)) {
      const entries = engines.filter((e) => e.engine === id);
      expect(entries, `entries for ${id}`).toHaveLength(1);
      expect(entries[0]?.tolerance.class).toBe("hosted");
      expect(entries[0]?.tolerance.defined_by).toBe(req);
    }
  });

  test("FR-018-48 · a passing hosted verdict was reached in Chromium, Firefox and WebKit; an entry without a verdict says why", async ({
    request,
    baseURL,
  }) => {
    const engines = await report(request, baseURL as string);
    for (const id of Object.keys(OWNER)) {
      const e = engines.find((x) => x.engine === id) as Entry;
      if (e.verdict === "pass") expect([...e.browsers].sort()).toEqual([...BROWSERS].sort());
      else if (e.verdict === "not_run") expect((e.reason ?? "").length).toBeGreaterThan(0);
      else expect(e.verdict).toBe("fail");
    }
  });

  test("FR-018-63 · a hosted engine with a failing or missing verdict is shown in T0 on its case page and never LIVE", async ({
    page,
    request,
    baseURL,
  }) => {
    const engines = await report(request, baseURL as string);
    const caseOf: Record<string, string> = {
      des: "A1",
      policies: "A1",
      haulage: "A1",
      lp: "A1",
      routing: "A2",
      "dust-lidar": "B1",
      "il1-twin": "A2",
      "il2-twin": "A3",
    };
    for (const id of Object.keys(OWNER)) {
      if (engines.find((e) => e.engine === id)?.verdict === "pass") continue;
      await openSimulate(page, caseOf[id] as string, "&tier=t2");
      await expect(enginePanel(page, id).getByTestId("lane-badge"), id).toHaveText("REPLAY", {
        timeout: 60_000,
      });
      await expect(enginePanel(page, id), id).toHaveAttribute("data-tier", "t0");
    }
  });
});
