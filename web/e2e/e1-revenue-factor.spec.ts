// T-017-027 [red] · FR-017-25, FR-017-26, NFR-017-03: the E1 revenue-factor slider, live cap and baked fallback.
//
// Spec: specs/017-planning-survey/spec.md
//   FR-017-25: when the visitor moves the E1 revenue-factor slider the web app recomputes the ultimate pit of the loaded
//     block model (<= 10^5 blocks) in the `mincut` worker and redraws the shell, the pit value and the strip ratio;
//   FR-017-26: a block model with more than 10^5 blocks is not computed live: the E1 tab shows its baked shells with the
//     REPLAY badge and the reason;
//   NFR-017-03: the live ultimate pit takes at most 1 s for 10^5 blocks with the 1:5 precedence (median of 5 runs, forced T2).
//
// Oracles (written in the test): the four-block example of the spec (one ore block, 1,000 t, over three waste blocks;
// value 6 lambda - 1 USD for the ore block and -1 USD for each waste block): the pit is empty up to lambda = 0.65 and full from
// the first grid value above 2/3, 0.675, where the pit value is (6 x 0.675 - 1) - 3 = 0.05 USD; at lambda = 1 the value is
// 5 - 3 = 2 USD and the strip ratio 3,000 t / 1,000 t = 3.0; nesting (the block count never decreases as lambda grows);
// the live cap 10^5 blocks (thresholds `web.mincut_blocks_live_max`).
//
// What the green commit must deliver (route `cases/E1/?tab=simulate&fixture=<name>`; fixtures are baked block models):
//   - slider `data-testid="e1-lambda-slider"` (range 0.025 to 1, step 0.025), outputs `e1-block-count`, `e1-pit-value` (USD),
//     `e1-strip-ratio` (text "-" when the pit has no ore), `e1-compute-ms`, `e1-mode` ("LIVE" or "REPLAY"), and for REPLAY the
//     badge `e1-replay-badge` and the reason `e1-replay-reason` (mentions the blocks count and the 100000 cap);
//   - fixtures: `four-block` (the example), `large` (100,001 blocks, baked shells), `live-large` (50 x 50 x 40 = 100,000 blocks with
//     the 1:5 precedence, live).
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

async function openFixture(page: Page, name: string): Promise<void> {
  await open(page, `cases/E1/?tab=simulate&fixture=${name}`);
  await expect(page.getByTestId("e1-lambda-slider")).toBeVisible();
}

async function value(page: Page, testId: string): Promise<number> {
  const text = (await page.getByTestId(testId).innerText()).replace(/,/g, "").trim();
  const match = text.match(/-?\d+(?:\.\d+)?/);
  expect(match, `no number in ${testId}: "${text}"`).not.toBeNull();
  return Number((match as RegExpMatchArray)[0]);
}

async function setLambda(page: Page, lambda: number): Promise<void> {
  await page.getByTestId("e1-lambda-slider").fill(String(lambda));
}

test("FR-017-25 · the four-block pit is empty at lambda 0.5 and full at 1.0 with value 2 and strip ratio 3", async ({
  page,
}) => {
  await openFixture(page, "four-block");
  await expect(page.getByTestId("e1-mode")).toHaveText("LIVE");
  await setLambda(page, 0.5);
  await expect.poll(() => value(page, "e1-block-count")).toBe(0);
  await setLambda(page, 1);
  await expect.poll(() => value(page, "e1-block-count")).toBe(4);
  expect(await value(page, "e1-pit-value")).toBeCloseTo(2, 6);
  expect(await value(page, "e1-strip-ratio")).toBeCloseTo(3, 6);
});

test("FR-017-25 · the pit switches on at the first grid value above 2/3 with value 0.05 USD", async ({
  page,
}) => {
  await openFixture(page, "four-block");
  await setLambda(page, 0.65);
  await expect.poll(() => value(page, "e1-block-count")).toBe(0);
  await setLambda(page, 0.675);
  await expect.poll(() => value(page, "e1-block-count")).toBe(4);
  expect(await value(page, "e1-pit-value")).toBeCloseTo(0.05, 6);
});

test("FR-017-25 · moving the slider up never shrinks the pit (nesting) and the pit value never drops below zero", async ({
  page,
}) => {
  await openFixture(page, "four-block");
  let previous = -1;
  for (let k = 1; k <= 40; k += 3) {
    await setLambda(page, k * 0.025);
    await expect.poll(() => value(page, "e1-block-count")).toBeGreaterThanOrEqual(previous);
    previous = await value(page, "e1-block-count");
    expect(await value(page, "e1-pit-value")).toBeGreaterThanOrEqual(0);
  }
});

test("FR-017-25 · an empty pit shows no strip ratio", async ({ page }) => {
  await openFixture(page, "four-block");
  await setLambda(page, 0.025);
  await expect(page.getByTestId("e1-strip-ratio")).toHaveText(/^\s*[-–]\s*$/);
});

test("FR-017-26 · a block model above 100,000 blocks is not computed live and shows its baked shells with the REPLAY badge and the reason", async ({
  page,
}) => {
  await openFixture(page, "large");
  await expect(page.getByTestId("e1-mode")).toHaveText("REPLAY");
  await expect(page.getByTestId("e1-replay-badge")).toBeVisible();
  await expect(page.getByTestId("e1-replay-reason")).toContainText(/100,?000/);
  await expect(page.getByTestId("e1-replay-reason")).toContainText(/blocks/i);
  await setLambda(page, 0.5);
  await expect(page.getByTestId("e1-block-count")).toBeVisible(); // the baked shell of that lambda is shown
  await expect(page.getByTestId("e1-compute-ms")).toHaveCount(0); // nothing was computed in the browser
});

test("NFR-017-03 · the live ultimate pit of 100,000 blocks takes at most one second (median of 5 runs)", async ({
  page,
}) => {
  await openFixture(page, "live-large");
  await expect(page.getByTestId("e1-mode")).toHaveText("LIVE");
  const times: number[] = [];
  for (const lambda of [0.4, 0.55, 0.7, 0.85, 1]) {
    await setLambda(page, lambda);
    await expect(page.getByTestId("e1-compute-ms")).toBeVisible();
    times.push(await value(page, "e1-compute-ms"));
  }
  times.sort((a, b) => a - b);
  expect(times[2]).toBeLessThanOrEqual(1000);
});
