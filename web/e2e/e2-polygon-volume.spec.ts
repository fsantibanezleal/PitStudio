// T-017-060 [red] · FR-017-46, FR-017-47, NFR-017-04: the E2 polygon tool: live cut and fill between two epochs.
//
// Spec: specs/017-planning-survey/spec.md
//   FR-017-46: closing a polygon on the E2 map computes V_cut, V_fill and V_net over the 4 m web grids of the two epochs in the
//     `volume` worker and shows them with the no-data fraction and the uncertainty bounds;
//   FR-017-47: a polygon with fewer than 3 vertices, more than 10^4 vertices, a self-intersection, a non-finite coordinate, or
//     entirely outside the grid is rejected with the reason and no volume is shown;
//   NFR-017-04: the live polygon volume takes at most 1 s for a 2,048 x 2,048 grid and a 10^4-vertex polygon (forced T2).
//
// Oracles (written in the test): the fixture polygon volumes of the Python reference (tests/unit/test_t_017_060_polygon_guards.py):
// in the known-volume scene at the 4 m web grid the polygon (40, 80)-(80, 120) holds the frustum, whose gridded fill is
// 2,369.684 m^3 (closed form 2 pi 379 = 2,381.327 m^3, -0.489 % gridding floor), cut 0, 100 valid cells, uncertainty 16 x
// sqrt(100) x sqrt(0.02) = 22.627 m^3 (uncorrelated) and 16 x 100 x sqrt(0.02) = 226.274 m^3 (fully correlated) for RMSEz 0.1 m
// on both epochs; the polygon (130, 60)-(170, 140) holds the trench, cut 2,880 m^3 exactly, fill 0; invalid polygons written
// by hand; a 10,000-vertex circle for the speed check.
//
// What the green commit must deliver (route `cases/E2/?tab=simulate&fixture=known-volume`, a fixture mode of the E2 tab that
// loads the known-volume scene as two 4 m grids with RMSEz 0.1 m, and `&fixture=stress` that loads two 2,048 x 2,048 grids):
//   - the map `data-testid="e2-map"` (canvas or SVG, coordinates in metres of the grid frame: x right, y up, 0..200 m for the
//     known-volume scene); clicks add vertices; `data-testid="e2-close-polygon"` closes the polygon;
//   - a coordinates field for scripted input: `data-testid="e2-polygon-input"` (a textarea taking a JSON array of [x, y]) and
//     `data-testid="e2-polygon-apply"` (a button that closes and evaluates it);
//   - results `data-testid` `e2-volume-cut`, `e2-volume-fill`, `e2-volume-net` (text starts with the number in m^3),
//     `e2-nodata-fraction`, `e2-uncertainty-uncorrelated`, `e2-uncertainty-correlated`, `e2-compute-ms`;
//   - an error line `data-testid="e2-polygon-error"` with the reason and no result texts when the polygon is rejected.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

async function openFixture(page: Page, fixture = "known-volume"): Promise<void> {
  await open(page, `cases/E2/?tab=simulate&fixture=${fixture}`);
  await expect(page.getByTestId("e2-map")).toBeVisible();
}

async function number(page: Page, testId: string): Promise<number> {
  const text = (await page.getByTestId(testId).innerText()).replace(/,/g, "").trim();
  const match = text.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/i);
  expect(match, `no number in ${testId}: "${text}"`).not.toBeNull();
  return Number((match as RegExpMatchArray)[0]);
}

async function apply(page: Page, polygon: unknown): Promise<void> {
  await page.getByTestId("e2-polygon-input").fill(JSON.stringify(polygon));
  await page.getByTestId("e2-polygon-apply").click();
}

const FRUSTUM = [
  [40, 80],
  [80, 80],
  [80, 120],
  [40, 120],
];
const TRENCH = [
  [130, 60],
  [170, 60],
  [170, 140],
  [130, 140],
];

test("FR-017-46 · a polygon around the stockpile gives the Python reference fill, no cut and the uncertainty bounds", async ({
  page,
}) => {
  await openFixture(page);
  await apply(page, FRUSTUM);
  expect(await number(page, "e2-volume-fill")).toBeCloseTo(2369.684, 2);
  expect(await number(page, "e2-volume-cut")).toBeCloseTo(0, 6);
  expect(await number(page, "e2-volume-net")).toBeCloseTo(2369.684, 2);
  expect(await number(page, "e2-nodata-fraction")).toBeCloseTo(0, 6);
  expect(await number(page, "e2-uncertainty-uncorrelated")).toBeCloseTo(22.627, 1);
  expect(await number(page, "e2-uncertainty-correlated")).toBeCloseTo(226.274, 1);
});

test("FR-017-46 · a polygon around the trench gives the exact cut and no fill", async ({ page }) => {
  await openFixture(page);
  await apply(page, TRENCH);
  expect(await number(page, "e2-volume-cut")).toBeCloseTo(2880, 3);
  expect(await number(page, "e2-volume-fill")).toBeCloseTo(0, 6);
  expect(await number(page, "e2-volume-net")).toBeCloseTo(-2880, 3);
});

test("FR-017-46 · drawing the polygon on the map by clicks and closing it gives the same volumes as the scripted input", async ({
  page,
}) => {
  await openFixture(page);
  const map = page.getByTestId("e2-map");
  const box = await map.boundingBox();
  expect(box).not.toBeNull();
  const { x, y, width, height } = box as { x: number; y: number; width: number; height: number };
  // the map shows 0 .. 200 m on both axes, y up: metres (40, 80) -> pixel (x + 0.2 w, y + (1 - 0.4) h)
  for (const [mx, my] of FRUSTUM) await page.mouse.click(x + (mx / 200) * width, y + (1 - my / 200) * height);
  await page.getByTestId("e2-close-polygon").click();
  expect(await number(page, "e2-volume-fill")).toBeCloseTo(2369.684, -1); // pixel picking is coarser than the scripted input
});

test("FR-017-47 · a polygon with fewer than 3 vertices is rejected and no volume is shown", async ({
  page,
}) => {
  await openFixture(page);
  await apply(page, [
    [40, 80],
    [80, 80],
  ]);
  await expect(page.getByTestId("e2-polygon-error")).toContainText(/at least 3/i);
  await expect(page.getByTestId("e2-volume-fill")).toHaveCount(0);
});

test("FR-017-47 · a self-intersecting polygon is rejected", async ({ page }) => {
  await openFixture(page);
  await apply(page, [
    [40, 80],
    [80, 120],
    [80, 80],
    [40, 120],
  ]); // a bow-tie
  await expect(page.getByTestId("e2-polygon-error")).toContainText(/self-intersect/i);
  await expect(page.getByTestId("e2-volume-cut")).toHaveCount(0);
});

test("FR-017-47 · a polygon entirely outside the grid is rejected", async ({ page }) => {
  await openFixture(page);
  await apply(page, [
    [500, 500],
    [520, 500],
    [520, 520],
    [500, 520],
  ]);
  await expect(page.getByTestId("e2-polygon-error")).toContainText(/outside/i);
  await expect(page.getByTestId("e2-volume-net")).toHaveCount(0);
});

test("FR-017-47 · non-finite coordinates are rejected", async ({ page }) => {
  await openFixture(page);
  await page.getByTestId("e2-polygon-input").fill("[[40, 80], [80, null], [80, 120]]");
  await page.getByTestId("e2-polygon-apply").click();
  await expect(page.getByTestId("e2-polygon-error")).toContainText(/finite|number/i);
  await expect(page.getByTestId("e2-volume-fill")).toHaveCount(0);
});

test("FR-017-47 · more than 10,000 vertices are rejected", async ({ page }) => {
  await openFixture(page);
  const n = 10_001;
  const circle = Array.from({ length: n }, (_, i) => [
    100 + 90 * Math.cos((2 * Math.PI * i) / n),
    100 + 90 * Math.sin((2 * Math.PI * i) / n),
  ]);
  await apply(page, circle);
  await expect(page.getByTestId("e2-polygon-error")).toContainText(/10000|10,000/);
});

test("FR-017-47 · a valid polygon after a rejected one clears the error and shows the volumes", async ({
  page,
}) => {
  await openFixture(page);
  await apply(page, [
    [40, 80],
    [80, 80],
  ]);
  await expect(page.getByTestId("e2-polygon-error")).toBeVisible();
  await apply(page, FRUSTUM);
  await expect(page.getByTestId("e2-polygon-error")).toHaveCount(0);
  expect(await number(page, "e2-volume-fill")).toBeCloseTo(2369.684, 2);
});

test("NFR-017-04 · a 10,000-vertex polygon over a 2,048 x 2,048 grid is evaluated in at most one second", async ({
  page,
}) => {
  await openFixture(page, "stress");
  const n = 10_000;
  const circle = Array.from({ length: n }, (_, i) => [
    4096 + 3000 * Math.cos((2 * Math.PI * i) / n),
    4096 + 3000 * Math.sin((2 * Math.PI * i) / n),
  ]);
  await apply(page, circle);
  await expect(page.getByTestId("e2-volume-net")).toBeVisible();
  expect(await number(page, "e2-compute-ms")).toBeLessThanOrEqual(1000);
});
