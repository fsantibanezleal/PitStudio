// T-018-041 [red] · FR-018-21 (paused for at least 10 s after load, E2E half), FR-018-22 (keyboard), FR-018-23 (scrub and step reach
// every video within one frame period), FR-018-24 (play: video within two frame periods of the clock, re-seek on drift) and FR-018-28
// (reduced motion). Unit half of FR-018-21/22: web/src/sim/t_018_040_clock.test.ts.
//
// Hooks and the real fixture video: web/e2e/support/video-fixture.ts (a WebM recorded by Playwright, 25 fps, case C2, tab "replay").
// The video fps of the oracle is the recorder's 25 fps; the clock fps of the case registry is 10 (`clock_fps` in the example registry),
// so one clock step is 0.1 s. Scene "replay frame" and chart-cursor views of US-018-5 need replay shards and chart data that no
// fixture provides yet; they are not covered here (see the report).
// Oracles: the EARS text; frame periods 1/25 s (video) and 1/10 s (clock step).
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { type FixtureVideo, makeFixtureVideo, routeVideo, stubCapabilities } from "./support/video-fixture";

let video: FixtureVideo;
test.beforeAll(async ({ browser }) => {
  video = await makeFixtureVideo(browser);
});

const SUPPORTED = { supported: true, smooth: true, powerEfficient: true };

async function openReplay(page: Page, extra = ""): Promise<void> {
  await stubCapabilities(page, { av1: SUPPORTED, h264: SUPPORTED });
  await routeVideo(page, video);
  await open(page, `cases/C2/?tab=replay${extra}`);
  await expect(page.getByTestId("sim-clock")).toBeVisible();
}

const clockState = (page: Page) =>
  page.evaluate(() => {
    const el = document.querySelector('[data-testid="sim-clock"]') as HTMLElement;
    return {
      t: Number(el.dataset.t),
      playing: el.dataset.playing === "true",
      duration: Number(el.dataset.duration),
    };
  });
const videoTime = (page: Page) =>
  page.evaluate(
    () => (document.querySelector('video[data-testid="media-video"]') as HTMLVideoElement).currentTime,
  );

test.describe("paused by default (FR-018-21)", () => {
  test("FR-018-21 · on / and on a case page the clock stays at t = 0, paused, for 10 s, with no video playing", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await open(page, "");
    await expect(page.getByTestId("sim-clock")).toBeVisible();
    await page.waitForTimeout(10_200);
    expect(await clockState(page)).toMatchObject({ t: 0, playing: false });

    await openReplay(page);
    const el = page.locator('video[data-testid="media-video"]').first();
    await expect(el).toBeAttached();
    await page.waitForTimeout(10_200);
    expect(await clockState(page)).toMatchObject({ t: 0, playing: false });
    expect(await el.evaluate((v: HTMLVideoElement) => v.paused)).toBe(true);
    expect(await videoTime(page)).toBe(0);
  });
});

test.describe("keyboard operation (FR-018-22)", () => {
  test("FR-018-22 · Space on Play runs the clock, Space on Pause stops it, and time advanced at about wall speed", async ({
    page,
  }) => {
    await openReplay(page);
    const play = page.getByRole("button", { name: "Play" });
    await play.focus();
    await page.keyboard.press("Space");
    await expect(page.getByTestId("sim-clock")).toHaveAttribute("data-playing", "true");
    await page.waitForTimeout(1000);
    await page.getByRole("button", { name: "Pause" }).focus();
    await page.keyboard.press("Space");
    const s = await clockState(page);
    expect(s.playing).toBe(false);
    expect(s.t).toBeGreaterThan(0.7);
    expect(s.t).toBeLessThan(1.6);
  });

  test("FR-018-22 · the step buttons and the arrow keys on the slider move the clock by 1/fps = 0.1 s; Home and End jump to the ends", async ({
    page,
  }) => {
    await openReplay(page);
    await page.getByRole("button", { name: "Step forward" }).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Enter");
    expect((await clockState(page)).t).toBeCloseTo(0.2, 6);
    await page.getByRole("button", { name: "Step back" }).focus();
    await page.keyboard.press("Enter");
    expect((await clockState(page)).t).toBeCloseTo(0.1, 6);
    const slider = page.getByRole("slider", { name: "Time" });
    await slider.focus();
    await page.keyboard.press("ArrowRight");
    expect((await clockState(page)).t).toBeCloseTo(0.2, 6);
    await page.keyboard.press("End");
    const end = await clockState(page);
    expect(end.t).toBeCloseTo(end.duration, 6);
    await page.keyboard.press("Home");
    expect((await clockState(page)).t).toBe(0);
  });
});

test.describe("scrub and step (FR-018-23)", () => {
  test("FR-018-23 · scrubbing to t puts the video within one frame period (1/25 s) of t at the next animation frame", async ({
    page,
  }) => {
    await openReplay(page);
    await expect(page.locator('video[data-testid="media-video"]').first()).toBeAttached();
    const slider = page.getByRole("slider", { name: "Time" });
    for (const t of [1.5, 0.5, 2.5, 0]) {
      await slider.fill(String(t));
      await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
      expect(Math.abs((await clockState(page)).t - t)).toBeLessThan(0.051);
      expect(Math.abs((await videoTime(page)) - t)).toBeLessThanOrEqual(1 / video.fps + 1e-6);
    }
  });

  test("FR-018-23 · stepping moves the video with the clock", async ({ page }) => {
    await openReplay(page);
    await expect(page.locator('video[data-testid="media-video"]').first()).toBeAttached();
    await page.getByRole("button", { name: "Step forward" }).focus();
    for (let i = 0; i < 12; i++) await page.keyboard.press("Enter");
    await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const t = (await clockState(page)).t;
    expect(t).toBeCloseTo(1.2, 6);
    expect(Math.abs((await videoTime(page)) - t)).toBeLessThanOrEqual(1 / video.fps + 1e-6);
  });
});

test.describe("playing (FR-018-24)", () => {
  test("FR-018-24 · while the clock plays, every presented frame is within two frame periods of the clock", async ({
    page,
  }) => {
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    const drifts = await page.evaluate(
      () =>
        new Promise<number[]>((resolve) => {
          const el = document.querySelector('video[data-testid="media-video"]') as HTMLVideoElement;
          const w = window as unknown as {
            __pitstudio: { clock: { tick(): void; getState(): { t: number } } };
          };
          const out: number[] = [];
          const onFrame = (_now: number, meta: VideoFrameCallbackMetadata) => {
            w.__pitstudio.clock.tick();
            out.push(meta.mediaTime - w.__pitstudio.clock.getState().t);
            if (out.length >= 30) resolve(out);
            else el.requestVideoFrameCallback(onFrame);
          };
          el.requestVideoFrameCallback(onFrame);
          setTimeout(() => resolve(out), 6000);
        }),
    );
    expect(drifts.length).toBeGreaterThanOrEqual(10);
    for (const d of drifts) expect(Math.abs(d)).toBeLessThanOrEqual(2 / video.fps + 1e-3);
  });

  test("FR-018-24 · a video pushed 1 s away from the clock is re-seeked to it", async ({ page }) => {
    await openReplay(page);
    await page.getByRole("button", { name: "Play" }).click();
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      const el = document.querySelector('video[data-testid="media-video"]') as HTMLVideoElement;
      el.currentTime = Math.min(el.duration - 0.2, el.currentTime + 1);
    });
    await expect
      .poll(
        async () => {
          const s = await clockState(page);
          return Math.abs((await videoTime(page)) - s.t);
        },
        { timeout: 3000 },
      )
      .toBeLessThanOrEqual(2 / video.fps + 0.05);
  });
});

test.describe("reduced motion (FR-018-28)", () => {
  test.use({ reducedMotion: "reduce" });

  test("FR-018-28 · with prefers-reduced-motion the pages run no animation and the clock moves only on user action", async ({
    page,
  }) => {
    await open(page, "?case=A1");
    await page.waitForTimeout(1500);
    const running = await page.evaluate(
      () => document.getAnimations().filter((a) => a.playState === "running").length,
    );
    expect(running).toBe(0);
    await expect(page.getByTestId("scene-state")).toHaveAttribute("data-motion", "reduced");
    expect(await clockState(page)).toMatchObject({ t: 0, playing: false });
    await page.waitForTimeout(2500);
    expect(await clockState(page)).toMatchObject({ t: 0, playing: false });
    await page.getByRole("button", { name: "Step forward" }).click();
    expect((await clockState(page)).t).toBeCloseTo(0.1, 6);
  });

  test("FR-018-28 · without the preference the scene reports full motion", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "no-preference" });
    const page = await context.newPage();
    await open(page, "?case=A1");
    await expect(page.getByTestId("scene-state")).toHaveAttribute("data-motion", "full");
    await context.close();
  });
});
