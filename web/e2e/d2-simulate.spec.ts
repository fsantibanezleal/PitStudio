// T-017-016 [red] · FR-017-08, FR-017-09, NFR-017-02: the D2 Simulate tab (mine-to-mill), chain and meta-model side by side.
//
// Spec: specs/017-planning-survey/spec.md
//   FR-017-08: the D2 Simulate tab shows, for the same inputs, the chain result (engine `comminution`) and the
//     meta-model result (engine `meta-model`) side by side with the held-out R^2 of each output, and the label
//     "calibrated synthetic -- not validated against real data" (FR-000-09);
//   FR-017-09: if any meta-model input lies outside the sweep box, the meta-model answer is labelled "extrapolation --
//     outside the training box" and the chain answer is still shown;
//   FR-017-11 (web side): an input that is not a finite number gives "no answer -- <reason>" for the meta-model;
//   NFR-017-02: meta-model batch evaluation on T2 reaches at least 200 scenarios per second (batch of 256).
//
// Oracles (written in the test): the identity t/h x kWh/t = eta P_mill on the displayed chain answer (the display keeps
// at least 4 significant digits, so the product is within 0.2 %); lowering the target P80 raises the chain kWh/t
// (spec section 7 monotonicity, hand-checked on the Bond formula 10 W_i (1/sqrt(P80) - 1/sqrt(F80))); the training box of
// section 7 (burden 3 to 6 m); the label texts above, with the em dash written as the escape --.
//
// What the green commit must deliver (route `cases/D2/?tab=simulate`, see web/src/cases/d2/):
//   - number inputs `data-testid="d2-input-<name>"` for the 15 inputs of section 7 (names as DC-017-01, e.g.
//     `d2-input-burden_m`, `d2-input-target_p80_um`, `d2-input-mill_power_kw`, `d2-input-efficiency`);
//   - `data-testid="d2-chain-answer"` and `data-testid="d2-meta-answer"`, each containing three `data-testid`
//     children `<prefix>-kwh_per_t`, `<prefix>-t_per_h`, `<prefix>-cost_per_t` whose text starts with the number;
//   - `data-testid="d2-r2-kwh_per_t"`, `-t_per_h`, `-cost_per_t`: the held-out R^2 of the meta-model per output (text
//     contains a decimal number between 0 and 1);
//   - `data-testid="d2-label-synthetic"` with the honesty label;
//   - `data-testid="d2-meta-note"` showing the extrapolation label or the "no answer -- <reason>" label (empty when the
//     inputs are in the box and finite);
//   - `data-testid="d2-batch-run"` (button, runs a batch of 256 scenarios in the `meta-model` worker) and
//     `data-testid="d2-batch-rate"` whose text contains "<n> scenarios/s".
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const EM_DASH = "--";
const SYNTHETIC = `calibrated synthetic ${EM_DASH} not validated against real data`;
const EXTRAPOLATION = `extrapolation ${EM_DASH} outside the training box`;
const OUTPUTS = ["kwh_per_t", "t_per_h", "cost_per_t"] as const;

async function openSimulate(page: Page): Promise<void> {
  await open(page, "cases/D2/?tab=simulate");
  await expect(page.getByTestId("d2-chain-answer")).toBeVisible();
}

async function number(page: Page, testId: string): Promise<number> {
  const text = (await page.getByTestId(testId).innerText()).trim();
  const match = text.match(/-?\d+(?:[.,]\d+)?(?:e[+-]?\d+)?/i);
  expect(match, `no number in ${testId}: "${text}"`).not.toBeNull();
  return Number((match as RegExpMatchArray)[0].replace(",", "."));
}

async function set(page: Page, name: string, value: string): Promise<void> {
  await page.getByTestId(`d2-input-${name}`).fill(value);
}

test("FR-017-08 · the chain and the meta-model answers are shown side by side for the same inputs", async ({
  page,
}) => {
  await openSimulate(page);
  for (const side of ["d2-chain-answer", "d2-meta-answer"]) {
    await expect(page.getByTestId(side)).toBeVisible();
    for (const output of OUTPUTS) {
      const value = await number(page, `${side.replace("-answer", "")}-${output}`);
      expect(Number.isFinite(value)).toBe(true);
      expect(value).toBeGreaterThan(0);
    }
  }
  const chain = await page.getByTestId("d2-chain-answer").boundingBox();
  const meta = await page.getByTestId("d2-meta-answer").boundingBox();
  expect(chain && meta).toBeTruthy();
  expect(Math.abs((chain as { y: number }).y - (meta as { y: number }).y)).toBeLessThan(40); // side by side
});

test("FR-017-08 · the held-out R^2 of every output is shown next to the meta-model answer", async ({
  page,
}) => {
  await openSimulate(page);
  for (const output of OUTPUTS) {
    const r2 = await number(page, `d2-r2-${output}`);
    expect(r2).toBeGreaterThan(0);
    expect(r2).toBeLessThanOrEqual(1);
  }
});

test("FR-017-08 · the tab carries the calibrated-synthetic label", async ({ page }) => {
  await openSimulate(page);
  await expect(page.getByTestId("d2-label-synthetic")).toHaveText(SYNTHETIC);
});

test("FR-017-08 · the chain answer obeys t/h x kWh/t = eta P_mill for the shown inputs", async ({ page }) => {
  await openSimulate(page);
  await set(page, "mill_power_kw", "8000");
  await set(page, "efficiency", "0.85");
  const kwh = await number(page, "d2-chain-kwh_per_t");
  const tph = await number(page, "d2-chain-t_per_h");
  expect(Math.abs((kwh * tph) / (0.85 * 8000) - 1)).toBeLessThan(0.002);
});

test("FR-017-08 · lowering the target P80 raises the chain specific energy", async ({ page }) => {
  await openSimulate(page);
  await set(page, "target_p80_um", "200");
  const coarse = await number(page, "d2-chain-kwh_per_t");
  await set(page, "target_p80_um", "100");
  const fine = await number(page, "d2-chain-kwh_per_t");
  expect(fine).toBeGreaterThan(coarse);
});

test("FR-017-08 · both answers update together when an input moves", async ({ page }) => {
  await openSimulate(page);
  const before = await page.getByTestId("d2-meta-answer").innerText();
  await set(page, "bond_work_index_kwh_per_t", "20");
  await expect.poll(async () => page.getByTestId("d2-meta-answer").innerText()).not.toBe(before);
});

test("FR-017-09 · an input outside the sweep box labels the meta-model answer as extrapolation and keeps the chain answer", async ({
  page,
}) => {
  await openSimulate(page);
  await expect(page.getByTestId("d2-meta-note")).not.toContainText("extrapolation");
  await set(page, "burden_m", "20"); // the training box is 3 to 6 m
  await expect(page.getByTestId("d2-meta-note")).toHaveText(EXTRAPOLATION);
  const chain = await number(page, "d2-chain-kwh_per_t");
  expect(chain).toBeGreaterThan(0); // the chain answer is still shown
  await set(page, "burden_m", "4.5");
  await expect(page.getByTestId("d2-meta-note")).not.toContainText("extrapolation");
});

test("FR-017-11 · an input that is not a finite number gives 'no answer' for the meta-model and no output", async ({
  page,
}) => {
  await openSimulate(page);
  await set(page, "efficiency", ""); // an empty field is not a number
  await expect(page.getByTestId("d2-meta-note")).toHaveText(new RegExp(`^no answer ${EM_DASH} .+`));
  for (const output of OUTPUTS) {
    await expect(page.getByTestId(`d2-meta-${output}`)).not.toHaveText(/\d/);
  }
});

test("NFR-017-02 · a batch of 256 scenarios runs at 200 scenarios per second or more", async ({ page }) => {
  await openSimulate(page);
  await page.getByTestId("d2-batch-run").click();
  const rate = page.getByTestId("d2-batch-rate");
  await expect(rate).toContainText("scenarios/s");
  const value = await number(page, "d2-batch-rate");
  expect(value).toBeGreaterThanOrEqual(200);
});
