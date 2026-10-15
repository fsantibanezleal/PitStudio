// T-017-034 [red] · FR-017-29: optional Composer review captures of the E1 pushbacks and their "Not run" state.
//
// Spec: specs/017-planning-survey/spec.md FR-017-29 (optional): where the kit-app-template licence prompt has been answered and
// the Kit lane runs, E1 publishes pushback review captures of the shells in the pit stage (`st58_kit_capture`); otherwise the
// Composer artefact shows "Not run". Kit performance data stay local-only (Constitution principle 11).
//
// Oracles (written in the test): the two fixture states of the E1 page: `composer-captures` (a baked set of three pushback
// review captures, as the stage would publish them) and `composer-not-run` (no capture; the licence prompt unanswered); the
// text "Not run" for the second; the absence of any kit performance number or request in both states (the page must not show
// frame times, GPU names or throughput of the Kit lane, and must not request files whose name contains "kit-perf" or
// "kit_performance").
//
// What the green commit must deliver (route `cases/E1/?tab=replay&fixture=<name>`):
//   - with `composer-captures`: `data-testid="e1-composer-captures"` holding one `<img data-testid="e1-capture">` per pushback
//     (three), each with a non-empty alt "Pushback <n> review capture" and a natural width above 0, and a caption naming the
//     pushback; no `e1-composer-not-run`;
//   - with `composer-not-run`: `data-testid="e1-composer-not-run"` whose text starts with "Not run" (a reason may follow), and no
//     `e1-capture` element;
//   - in both states no element `data-testid="e1-kit-performance"` and no request to a kit performance file.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";

function kitPerfRequests(page: Page): string[] {
  const urls: string[] = [];
  page.on("request", (req) => {
    const path = new URL(req.url()).pathname;
    if (/kit[-_]perf|kit_performance/i.test(path)) urls.push(path);
  });
  return urls;
}

async function openFixture(page: Page, name: string): Promise<void> {
  await open(page, `cases/E1/?tab=replay&fixture=${name}`);
  await expect(page.locator("main h1")).toContainText("E1");
}

test("FR-017-29 · with the Kit lane's captures the E1 tab shows one review capture per pushback", async ({
  page,
}) => {
  await openFixture(page, "composer-captures");
  const captures = page.getByTestId("e1-capture");
  await expect(captures).toHaveCount(3);
  for (let i = 0; i < 3; i++) {
    const image = captures.nth(i);
    await expect(image).toHaveAttribute("alt", new RegExp(`^Pushback ${i + 1} review capture`));
    const width = await image.evaluate((el: HTMLImageElement) => el.naturalWidth);
    expect(width).toBeGreaterThan(0);
  }
  await expect(page.getByTestId("e1-composer-not-run")).toHaveCount(0);
});

test("FR-017-29 · without the Kit lane the Composer artefact shows 'Not run' and no capture", async ({
  page,
}) => {
  await openFixture(page, "composer-not-run");
  await expect(page.getByTestId("e1-composer-not-run")).toHaveText(/^Not run/);
  await expect(page.getByTestId("e1-capture")).toHaveCount(0);
});

test("FR-017-29 · Kit performance data stay local-only: no element and no request in either state", async ({
  page,
}) => {
  const requests = kitPerfRequests(page);
  for (const name of ["composer-captures", "composer-not-run"]) {
    await openFixture(page, name);
    // the Composer artefact is shown in its state first, so the absence checks below look at the right page
    await expect(
      page.getByTestId(name === "composer-captures" ? "e1-composer-captures" : "e1-composer-not-run"),
    ).toBeVisible();
    await page.waitForLoadState("networkidle");
    await expect(page.getByTestId("e1-kit-performance")).toHaveCount(0);
    const text = (await page.locator("main").innerText()).toLowerCase();
    expect(text).not.toMatch(/frame time|fps|rtx 5000|gpu-?ms/);
  }
  expect(requests).toEqual([]);
});

test("FR-017-29 · the Not run state of the Composer artefact does not break the rest of the E1 replay tab", async ({
  page,
}) => {
  await openFixture(page, "composer-not-run");
  await expect(page.getByTestId("e1-composer-not-run")).toBeVisible();
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.locator("main h1")).toContainText("E1");
});
