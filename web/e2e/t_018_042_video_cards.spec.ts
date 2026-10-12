// T-018-042 [red] · FR-018-25 (preload="none", WebP poster, no video bytes before play), FR-018-26 (file choice) and FR-018-27 (failures
// keep the REPLAY badge and leave the clock and the other views running), in a real browser. Unit half:
// web/src/media/t_018_042_video_source.test.ts.
//
// Hooks and fixture: web/e2e/support/video-fixture.ts (case C2, tab "replay"; AV1 1080p and H.264 720p files, WebP poster, stubbed
// MediaCapabilities). The video card exposes [data-testid="video-card"][data-state] with the texts "Video not available in this
// browser" / "integrity check failed" and [data-testid="lane-badge"] REPLAY.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { type FixtureVideo, makeFixtureVideo, routeVideo, stubCapabilities } from "./support/video-fixture";

let video: FixtureVideo;
test.beforeAll(async ({ browser }) => {
  video = await makeFixtureVideo(browser);
});

const yes = { supported: true, smooth: true, powerEfficient: true };
const no = { supported: false, smooth: false, powerEfficient: false };

async function openReplay(page: Page): Promise<void> {
  await open(page, "cases/C2/?tab=replay");
  await expect(page.getByTestId("video-card").first()).toBeVisible();
}

test.describe("no bytes before play (FR-018-25)", () => {
  test("FR-018-25 · every video has preload=none and a WebP poster, and no video file is requested before play", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    const routes = await routeVideo(page, video);
    const urls: string[] = [];
    page.on("request", (r) => urls.push(r.url()));
    await openReplay(page);
    await page.waitForTimeout(2500);
    const videos = page.locator("video");
    const n = await videos.count();
    expect(n).toBeGreaterThan(0);
    for (let i = 0; i < n; i++) {
      await expect(videos.nth(i)).toHaveAttribute("preload", "none");
      await expect(videos.nth(i)).toHaveAttribute("poster", /\.webp(\?|$)/);
    }
    expect(routes.requested()).toEqual([]);
    expect(urls.filter((u) => /\.(webm|mp4)(\?|$)/.test(u))).toEqual([]);
    await page.getByRole("button", { name: "Play" }).click();
    await expect.poll(() => routes.requested().length, { timeout: 15_000 }).toBeGreaterThan(0);
  });

  test("FR-018-25 · the video bytes are requested after play on the card as well as after play on the clock", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    const routes = await routeVideo(page, video);
    await openReplay(page);
    const card = page.getByTestId("video-card").first();
    await card.getByRole("button", { name: /play/i }).click();
    await expect.poll(() => routes.requested().length, { timeout: 15_000 }).toBeGreaterThan(0);
  });
});

test.describe("file choice (FR-018-26)", () => {
  test("FR-018-26 · AV1 supported and power efficient: the AV1 file is fetched, not the H.264 one", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    const routes = await routeVideo(page, video);
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    await expect.poll(() => routes.requested().length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect(routes.requested()).toEqual(["av1"]);
  });

  test("FR-018-26 · AV1 supported but not power efficient: the H.264 file is fetched", async ({ page }) => {
    await stubCapabilities(page, {
      av1: { supported: true, smooth: true, powerEfficient: false },
      h264: yes,
    });
    const routes = await routeVideo(page, video);
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    await expect.poll(() => routes.requested().length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect(routes.requested()).toEqual(["h264"]);
  });
});

test.describe("failures keep the page running (FR-018-27)", () => {
  async function expectUnavailable(page: Page, message: string): Promise<void> {
    const card = page.getByTestId("video-card").first();
    await expect(card).toContainText(message);
    await expect(card.getByTestId("lane-badge")).toHaveText("REPLAY");
    await expect(card.locator("video")).toHaveAttribute("poster", /\.webp/);
    // the clock and the rest of the page keep working
    await page.getByRole("button", { name: "Play" }).click();
    await expect(page.getByTestId("sim-clock")).toHaveAttribute("data-playing", "true");
    await page.waitForTimeout(600);
    expect(Number(await page.getByTestId("sim-clock").getAttribute("data-t"))).toBeGreaterThan(0.3);
    await expect(page.getByTestId("tier-badge")).toBeVisible();
  }

  test("FR-018-27 · neither encoding supported: poster and 'Video not available in this browser'", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: no, h264: no });
    const routes = await routeVideo(page, video);
    await openReplay(page);
    await expectUnavailable(page, "Video not available in this browser");
    expect(routes.requested()).toEqual([]);
  });

  test("FR-018-27 · an absent MediaCapabilities counts as not supported", async ({ page }) => {
    await stubCapabilities(page, "absent");
    await routeVideo(page, video);
    await openReplay(page);
    await expectUnavailable(page, "Video not available in this browser");
  });

  test("FR-018-27 · a rejected decodingInfo counts as not supported", async ({ page }) => {
    await stubCapabilities(page, "rejects");
    await routeVideo(page, video);
    await openReplay(page);
    await expectUnavailable(page, "Video not available in this browser");
  });

  test("FR-018-27 · a malformed decodingInfo answer counts as not supported", async ({ page }) => {
    await stubCapabilities(page, { av1: "supported", h264: { supported: "yes" } });
    await routeVideo(page, video);
    await openReplay(page);
    await expectUnavailable(page, "Video not available in this browser");
  });

  test("FR-018-27 · a video file that fails its SHA-256 check shows 'integrity check failed' and keeps REPLAY", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    const corrupted = Buffer.from(video.bytes);
    corrupted[corrupted.length >> 1] = (corrupted[corrupted.length >> 1] as number) ^ 0xff;
    await routeVideo(page, video, { av1: corrupted });
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    const card = page.getByTestId("video-card").first();
    await expect(card).toContainText("integrity check failed", { timeout: 15_000 });
    await expect(card.getByTestId("lane-badge")).toHaveText("REPLAY");
    await expect(page.getByTestId("sim-clock")).toHaveAttribute("data-playing", "true");
  });

  test("FR-018-27 · a video file that cannot be loaded (HTTP 404) shows 'Video not available in this browser'", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    await routeVideo(page, video);
    await page.route("**/assets/videos/c2-flood-av1.webm", (route) =>
      route.fulfill({ status: 404, body: "gone" }),
    );
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    await expect(page.getByTestId("video-card").first()).toContainText(
      "Video not available in this browser",
      {
        timeout: 15_000,
      },
    );
    await expect(page.getByTestId("sim-clock")).toHaveAttribute("data-playing", "true");
  });
});
