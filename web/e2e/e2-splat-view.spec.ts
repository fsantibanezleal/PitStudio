// T-017-049 [red] · FR-017-41, FR-017-49, NFR-017-05: the E2 splat view: badge, route-only loading, "Not run" label.
//
// Spec: specs/017-planning-survey/spec.md
//   FR-017-41: the E2 view shows the packaged splat (SPZ) with the badge "captured (photogrammetry), not simulated";
//   FR-017-49: a PLY or SPZ file that fails to parse (or declares more than 10^7 Gaussians, or has non-finite attributes)
//     makes the splat view show "Not run -- <reason>" (an em dash in the label);
//   NFR-017-05: the splat asset is at most 25 x 10^6 bytes and is requested only on the splat route, never in the first view.
//
// Oracles (written in the test): the request log of the page (every URL ending in `.spz` requested by the first view of the
// case page must be empty; the splat route requests exactly one); the response size of the asset against 25,000,000 bytes;
// the label texts above (em dash written as the escape —); a deliberately corrupt SPZ served for the asset URL
// (bytes that are not gzip) that the viewer must reject.
//
// What the green commit must deliver (route `cases/E2/`, the case page of spec 018; the splat route is `?tab=scene&view=splat`):
//   - the first view of `cases/E2/` (default tab) offers a link `data-testid="e2-splat-link"` to the splat route and
//     requests no `.spz` file and no splat viewer chunk named `spark*`;
//   - the splat route requests one `.spz` asset under `<base>assets/e2/` (the baked, pruned splat), shows
//     `data-testid="e2-splat-badge"` with the text "captured (photogrammetry), not simulated" and a canvas
//     `data-testid="e2-splat-canvas"`;
//   - when the asset cannot be parsed the view shows `data-testid="e2-splat-not-run"` with the text "Not run — <reason>"
//     (non-empty reason) and no canvas.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

const EM_DASH = "—";
const SPLAT_BYTES_MAX = 25_000_000;

function spzRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (req) => {
    const path = new URL(req.url()).pathname;
    if (path.endsWith(".spz")) urls.push(path);
  });
  return urls;
}

test("NFR-017-05 · the first view of the E2 case page requests no splat asset", async ({ page }) => {
  const spz = spzRequests(page);
  const chunks: string[] = [];
  page.on("request", (req) => {
    const path = new URL(req.url()).pathname;
    if (/spark/i.test(path)) chunks.push(path);
  });
  await open(page, "cases/E2/");
  await expect(page.locator("main h1")).toContainText("E2");
  await expect(page.getByTestId("e2-splat-link")).toBeVisible(); // the splat is offered, but only as a link to its route
  await page.waitForLoadState("networkidle");
  expect(spz).toEqual([]);
  expect(chunks).toEqual([]);
});

test("NFR-017-05 · the splat route requests exactly one splat asset of at most 25 MB", async ({ page }) => {
  const spz = spzRequests(page);
  const sizes: number[] = [];
  page.on("response", async (res) => {
    if (new URL(res.url()).pathname.endsWith(".spz") && res.status() === 200) {
      const length = Number(res.headers()["content-length"] ?? (await res.body()).length);
      sizes.push(length);
    }
  });
  await open(page, "cases/E2/?tab=scene&view=splat");
  await page.waitForLoadState("networkidle");
  expect(spz).toHaveLength(1);
  expect(spz[0]).toContain("/assets/e2/");
  for (const size of sizes) expect(size).toBeLessThanOrEqual(SPLAT_BYTES_MAX);
});

test("FR-017-41 · the splat view carries the captured-not-simulated badge", async ({ page }) => {
  await open(page, "cases/E2/?tab=scene&view=splat");
  await expect(page.getByTestId("e2-splat-badge")).toHaveText("captured (photogrammetry), not simulated");
  await expect(page.getByTestId("e2-splat-canvas")).toBeVisible();
});

test("FR-017-49 · a splat asset that does not parse gives 'Not run' with a reason and no canvas", async ({
  page,
}) => {
  await page.route("**/*.spz", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/octet-stream",
      body: Buffer.from("this is not a gzip stream"),
    }),
  );
  await open(page, "cases/E2/?tab=scene&view=splat");
  const note = page.getByTestId("e2-splat-not-run");
  await expect(note).toBeVisible();
  await expect(note).toHaveText(new RegExp(`^Not run ${EM_DASH} .+`));
  await expect(page.getByTestId("e2-splat-canvas")).toHaveCount(0);
});

test("FR-017-49 · a missing splat asset also gives 'Not run' and the rest of the E2 tab still works", async ({
  page,
}) => {
  await page.route("**/*.spz", (route) => route.fulfill({ status: 404, body: "" }));
  await open(page, "cases/E2/?tab=scene&view=splat");
  await expect(page.getByTestId("e2-splat-not-run")).toHaveText(new RegExp(`^Not run ${EM_DASH} .+`));
  await expect(page.locator("main h1")).toContainText("E2");
});
