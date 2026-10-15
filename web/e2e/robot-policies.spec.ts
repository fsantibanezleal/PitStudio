// T-014-054 [red] · FR-014-43, FR-014-45, FR-014-03, FR-014-24, NFR-014-04: live panels, "sim-to-sim" labels, replay fallback, "evaluated, not adopted" and
// "not run" states, frame time.
//
// Spec: specs/014-robot-learning/spec.md FR-014-43: "When a visitor opens the A2 or A3 policy panel, the web app shall run the policy live on its TypeScript twin with a LIVE
// badge and the label 'sim-to-sim', offer the Isaac Lab rollouts as REPLAY, and fall back to the replay if ORT-web cannot initialise (FR-000-02)." FR-014-44 (E2E half): an
// out-of-range or non-finite twin input is clamped with the message "clamped to the training range"; an ONNX file that fails its SHA-256 is not loaded and the replay is shown.
// FR-014-45: "Every IL result card and panel shall state 'simulation only - compared with a classical controller on the same simulator; no field claim', and field results from the
// literature shall appear only as context, never as comparison targets." FR-014-03: when the lane is not adopted the A2/A3 policy panels show "evaluated, not adopted" with the reason.
// FR-014-24: the IL-3 panel shows metrics or "not run". NFR-014-04: the live twin step (5 physics substeps and one ONNX inference per frame) takes <= 16 ms per animation frame.
//
// Oracle: the DOM states of the requirement (badge text, label text, the literal sentences); the clamp ranges (payload [0, 1], light-vehicle speed [20, 40] km/h, cohesion [0, 20] kPa,
// friction angle [25, 40] deg); a corrupted body served for the ONNX request (its SHA-256 cannot match the bundle); the WASM binaries blocked at the network layer to force the ORT-web
// initialisation failure; the frame-time samples the panel records in `window.__pitstudio.robots.stepMs` (see below).
//
// What the green commit must deliver (A2 = IL-1 haul truck, A3 = IL-2 excavator; the panels sit in the "Simulate (live)" tab of the case page):
//   - `[data-testid="policy-panel-il1"]` on cases/A2/ and `[data-testid="policy-panel-il2"]` on cases/A3/, and `[data-testid="policy-panel-il3"]` on cases/A3/;
//   - inside a panel: `[data-testid="mode-badge"]` with the text LIVE or REPLAY; `[data-testid="sim-to-sim-label"]` with the text "sim-to-sim"; a `button` named "Replay Isaac Lab rollouts"
//     that switches the badge to REPLAY; `[data-testid="clamp-message"]` (present only while an input is clamped); `[data-testid="fallback-reason"]` (present only in the replay
//     fallback, naming "SHA-256" or "ORT-web"); the statement of FR-014-45; inputs labelled "Payload fraction" and "Light-vehicle speed (km/h)" (A2), "Cohesion (kPa)" and "Friction angle (deg)" (A3);
//   - the models are requested from `<base>assets/models/onnx/il1-haul-truck.onnx` and `.../il2-excavator.onnx`; the lane state from `<base>assets/il/lane.json`
//     ({ "adopted": boolean, "reason"?: string, "il3": { "status": "complete" | "not run" } }); while the lane is not adopted the panels show the text "evaluated, not adopted" and the reason,
//     no badge LIVE and no policy inputs;
//   - `window.__pitstudio.robots.stepMs: number[]`: the compute time in ms of each animation frame of a live panel (5 substeps and one inference), the last 600 frames.
import { expect, test } from "@playwright/test";
import { open } from "./helpers";

const SENTENCE =
  "simulation only — compared with a classical controller on the same simulator; no field claim";
const CLAMPED = "clamped to the training range";

async function openLive(page: import("@playwright/test").Page, id: "A2" | "A3") {
  await open(page, `cases/${id}/?tab=simulate`);
  return page.getByTestId(id === "A2" ? "policy-panel-il1" : "policy-panel-il2");
}

test.describe("live panels (FR-014-43)", () => {
  test("FR-014-43 · the A2 panel runs the IL-1 policy live on the TS twin with the LIVE badge and the sim-to-sim label", async ({
    page,
  }) => {
    const panel = await openLive(page, "A2");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("mode-badge")).toHaveText("LIVE");
    await expect(panel.getByTestId("sim-to-sim-label")).toHaveText("sim-to-sim");
  });

  test("FR-014-43 · the A3 panel runs the IL-2 policy live with the LIVE badge and the sim-to-sim label", async ({
    page,
  }) => {
    const panel = await openLive(page, "A3");
    await expect(panel.getByTestId("mode-badge")).toHaveText("LIVE");
    await expect(panel.getByTestId("sim-to-sim-label")).toHaveText("sim-to-sim");
  });

  test("FR-014-43 · the Isaac Lab rollouts are offered as REPLAY", async ({ page }) => {
    const panel = await openLive(page, "A2");
    await expect(panel.getByTestId("mode-badge")).toHaveText("LIVE");
    await panel.getByRole("button", { name: "Replay Isaac Lab rollouts" }).click();
    await expect(panel.getByTestId("mode-badge")).toHaveText("REPLAY");
    await expect(panel.getByTestId("sim-to-sim-label")).toHaveText("sim-to-sim");
  });

  test("FR-014-43 · when ORT-web cannot initialise the panel falls back to the replay", async ({ page }) => {
    await page.route("**/*.wasm", (route) => route.abort());
    const panel = await openLive(page, "A2");
    await expect(panel.getByTestId("mode-badge")).toHaveText("REPLAY");
    await expect(panel.getByTestId("fallback-reason")).toContainText(/ORT-web/);
    await expect(panel.getByTestId("mode-badge")).not.toHaveText("LIVE");
  });
});

test.describe("hostile inputs (FR-014-44)", () => {
  const cases: { id: "A2" | "A3"; label: string; raw: string; shown: string }[] = [
    { id: "A2", label: "Payload fraction", raw: "9", shown: "1" },
    { id: "A2", label: "Payload fraction", raw: "-3", shown: "0" },
    { id: "A2", label: "Light-vehicle speed (km/h)", raw: "200", shown: "40" },
    { id: "A2", label: "Light-vehicle speed (km/h)", raw: "5", shown: "20" },
    { id: "A3", label: "Cohesion (kPa)", raw: "1e9", shown: "20" },
    { id: "A3", label: "Friction angle (deg)", raw: "90", shown: "40" },
    { id: "A3", label: "Friction angle (deg)", raw: "-5", shown: "25" },
  ];
  for (const c of cases) {
    test(`FR-014-44 · ${c.id} ${c.label} = ${c.raw} is clamped to ${c.shown} and says so`, async ({
      page,
    }) => {
      const panel = await openLive(page, c.id);
      const input = panel.getByLabel(c.label);
      await input.fill(c.raw);
      await input.blur();
      await expect(input).toHaveValue(c.shown);
      await expect(panel.getByTestId("clamp-message")).toHaveText(CLAMPED);
    });
  }

  test("FR-014-44 · a non-numeric value is replaced by a value inside the range and the message appears", async ({
    page,
  }) => {
    const panel = await openLive(page, "A2");
    const input = panel.getByLabel("Payload fraction");
    await input.fill("abc");
    await input.blur();
    const v = Number(await input.inputValue());
    expect(Number.isFinite(v)).toBe(true);
    expect(v).toBeGreaterThanOrEqual(0);
    expect(v).toBeLessThanOrEqual(1);
    await expect(panel.getByTestId("clamp-message")).toHaveText(CLAMPED);
  });

  test("FR-014-44 · an in-range value shows no clamp message", async ({ page }) => {
    const panel = await openLive(page, "A2");
    const input = panel.getByLabel("Payload fraction");
    await input.fill("0.4");
    await input.blur();
    await expect(input).toHaveValue("0.4");
    await expect(panel.getByTestId("clamp-message")).toHaveCount(0);
  });

  test("FR-014-44 · an ONNX file that fails its SHA-256 is not loaded and the replay is shown", async ({
    page,
  }) => {
    await page.route("**/il1-haul-truck.onnx", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/octet-stream",
        body: Buffer.from("corrupted policy bytes"),
      }),
    );
    const panel = await openLive(page, "A2");
    await expect(panel.getByTestId("mode-badge")).toHaveText("REPLAY");
    await expect(panel.getByTestId("fallback-reason")).toContainText(/SHA-256/);
  });

  test("FR-014-44 · a corrupted IL-2 policy file also gives the replay", async ({ page }) => {
    await page.route("**/il2-excavator.onnx", (route) =>
      route.fulfill({ status: 200, contentType: "application/octet-stream", body: Buffer.alloc(2048, 7) }),
    );
    const panel = await openLive(page, "A3");
    await expect(panel.getByTestId("mode-badge")).toHaveText("REPLAY");
    await expect(panel.getByTestId("fallback-reason")).toContainText(/SHA-256/);
  });
});

test.describe("honesty statements (FR-014-45)", () => {
  for (const [id, testId] of [
    ["A2", "policy-panel-il1"],
    ["A3", "policy-panel-il2"],
  ] as const) {
    test(`FR-014-45 · the ${id} panel states that it is simulation only, compared on the same simulator, no field claim`, async ({
      page,
    }) => {
      await open(page, `cases/${id}/?tab=simulate`);
      await expect(page.getByTestId(testId)).toContainText(SENTENCE);
    });
  }

  test("FR-014-45 · every IL result card on the replay tab states it too", async ({ page }) => {
    await open(page, "cases/A2/?tab=replay");
    const cards = page.getByTestId("il-result-card");
    expect(await cards.count()).toBeGreaterThan(0);
    for (const card of await cards.all()) await expect(card).toContainText(SENTENCE);
  });

  test("FR-014-45 · field results appear only as context, never as comparison targets", async ({ page }) => {
    await open(page, "cases/A2/?tab=context");
    const field = page.getByTestId("il-field-context");
    await expect(field).toBeVisible();
    await expect(field).toContainText(/context/i);
    await expect(page.getByTestId("policy-panel-il1")).toHaveCount(0); // the context tab holds no comparison panel
    await open(page, "cases/A2/?tab=simulate");
    await expect(
      page
        .getByTestId("policy-panel-il1")
        .getByText(/field/i)
        .filter({ hasText: /target|compared with (the )?field/i }),
    ).toHaveCount(0);
  });
});

test.describe("lane gating states (FR-014-03, FR-014-24)", () => {
  const reason = "kit-less smoke failed: torch sees no CUDA device on this host";

  for (const id of ["A2", "A3"] as const) {
    test(`FR-014-03 · ${id}: a lane that is not adopted shows "evaluated, not adopted" with the reason and no live policy`, async ({
      page,
    }) => {
      await page.route("**/assets/il/lane.json", (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ adopted: false, reason, il3: { status: "not run" } }),
        }),
      );
      const panel = await openLive(page, id);
      await expect(panel).toContainText("evaluated, not adopted");
      await expect(panel).toContainText(reason);
      await expect(panel.getByTestId("mode-badge")).toHaveCount(0);
      await expect(panel.getByRole("spinbutton")).toHaveCount(0);
    });
  }

  test("FR-014-03 · an unreadable lane file is treated as not adopted", async ({ page }) => {
    await page.route("**/assets/il/lane.json", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: "{not json" }),
    );
    const panel = await openLive(page, "A2");
    await expect(panel).toContainText("evaluated, not adopted");
  });

  test("FR-014-03 · a missing lane file (404) is treated as not adopted", async ({ page }) => {
    await page.route("**/assets/il/lane.json", (route) => route.fulfill({ status: 404, body: "" }));
    const panel = await openLive(page, "A3");
    await expect(panel).toContainText("evaluated, not adopted");
  });

  test("FR-014-24 · an IL-3 that was not trained shows 'not run'", async ({ page }) => {
    await page.route("**/assets/il/lane.json", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ adopted: true, il3: { status: "not run" } }),
      }),
    );
    await open(page, "cases/A3/?tab=simulate");
    const il3 = page.getByTestId("policy-panel-il3");
    await expect(il3).toContainText("not run");
    await expect(il3.getByTestId("mode-badge")).toHaveCount(0);
  });

  test("FR-014-24 · a trained IL-3 shows its metrics with IL-2's metric names", async ({ page }) => {
    await page.route("**/assets/il/lane.json", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ adopted: true, il3: { status: "complete" } }),
      }),
    );
    await open(page, "cases/A3/?tab=simulate");
    const il3 = page.getByTestId("policy-panel-il3");
    await expect(il3).not.toContainText("not run");
    for (const name of ["fill factor", "cycle time", "productivity", "stall"])
      await expect(il3).toContainText(new RegExp(name, "i"));
  });
});

test.describe("frame time (NFR-014-04)", () => {
  test("NFR-014-04 · the live twin step (5 substeps and one inference) takes at most 16 ms per frame at the 95th percentile", async ({
    page,
  }) => {
    const panel = await openLive(page, "A2");
    await expect(panel.getByTestId("mode-badge")).toHaveText("LIVE");
    await page.waitForTimeout(4000);
    const samples = await page.evaluate(() => {
      const w = window as unknown as { __pitstudio?: { robots?: { stepMs?: number[] } } };
      return w.__pitstudio?.robots?.stepMs ?? [];
    });
    expect(samples.length).toBeGreaterThanOrEqual(120);
    expect(samples.every((v) => Number.isFinite(v) && v >= 0)).toBe(true);
    const sorted = [...samples].sort((a, b) => a - b);
    const p95 = sorted[Math.floor(0.95 * (sorted.length - 1))] as number;
    expect(p95).toBeLessThanOrEqual(16);
  });
});
