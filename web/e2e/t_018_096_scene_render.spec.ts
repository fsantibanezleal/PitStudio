// T-018-096 Â· FR-018-73 in a real browser, against the published render run (the first RTX flyover of the Bingham Canyon scene,
// published by `studio import-run` kind render): the rendered scene section on all 12 case pages from one component, the poster
// and the stills at once with the producer attribution in place, no video file requested before a click, and the clip playing
// after a click. Unit half: web/src/cases/t_018_096_scene_render.test.tsx.
import { expect, type Page, test } from "@playwright/test";
import { open } from "./helpers";
import { stubCapabilities } from "./support/video-fixture";

const CASES = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const LABEL = "Rendered with NVIDIA Omniverse RTX (ovrtx)";
const yes = { supported: true, smooth: true, powerEfficient: true };

async function openCase(page: Page, id: string): Promise<void> {
  await open(page, `cases/${id}/`);
  await expect(page.getByTestId("scene-render")).toHaveCount(1);
}

test.describe("the rendered scene section (FR-018-73)", () => {
  for (const id of CASES) {
    test(`${id} Â· one section with the poster, three stills, the label in place and the render tools in Built with`, async ({
      page,
    }) => {
      await openCase(page, id);
      const section = page.getByTestId("scene-render");
      await expect(section).toHaveAttribute("data-visual", "render");
      const video = section.locator("video");
      await expect(video).toHaveAttribute("preload", "none");
      await expect(video).not.toHaveAttribute("autoplay", /.*/);
      await expect(video).toHaveAttribute("poster", /\.webp$/);
      const stills = section.locator("figure[data-still] img");
      await expect(stills).toHaveCount(3);
      // a still is requested when it nears the viewport (NFR-018-01): bring each one into view before reading its size
      for (let i = 0; i < 3; i++) await stills.nth(i).scrollIntoViewIfNeeded();
      await expect
        .poll(() => stills.evaluateAll((els) => els.map((e) => (e as HTMLImageElement).naturalWidth)))
        .toEqual([1920, 1920, 1920]);
      await expect(section.locator("[data-producer='render']")).toContainText(LABEL);
      await expect(section.locator("figure[data-still]").first()).toContainText(LABEL);
      for (const t of ["0 s", "10 s", "20 s"]) await expect(section).toContainText(t);
      // the render tools are in the Built with section of the page as used, NVIDIA tools marked
      const built = page.getByTestId("built-with");
      await expect(built.locator("[data-chip='ovrtx']")).toHaveAttribute("data-status", "used");
      await expect(built.locator("[data-chip='ovrtx']")).toHaveAttribute("data-nvidia", "true");
      await expect(built.locator("[data-chip='nvenc-ffmpeg']")).toHaveAttribute("data-status", "used");
      await expect(built.locator("[data-chip='openusd']")).toHaveAttribute("data-status", "used");
    });
  }

  test("no video file is requested before the click, and the clip plays after it", async ({ page }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    const media: string[] = [];
    page.on("request", (r) => {
      if (/\.(mp4|webm)(\?|$)/.test(r.url())) media.push(r.url());
    });
    await openCase(page, "C1");
    await page.waitForTimeout(2500);
    expect(media).toEqual([]);
    const video = page.getByTestId("scene-render").locator("video");
    expect(await video.evaluate((el) => (el as HTMLVideoElement).paused && !el.hasAttribute("src"))).toBe(
      true,
    );
    await page.getByRole("button", { name: "Play the flyover" }).click();
    await expect.poll(() => media.length, { timeout: 30_000 }).toBe(1);
    expect(media[0]).toMatch(/bingham-flyover\.av1\.mp4$/);
    await expect(video).toHaveAttribute("src", /^blob:/);
    await expect
      .poll(() => video.evaluate((el) => (el as HTMLVideoElement).currentTime), { timeout: 30_000 })
      .toBeGreaterThan(0);
    expect(await video.evaluate((el) => (el as HTMLVideoElement).error === null)).toBe(true);
  });

  test("with the clip failing to load the poster and the stills stay and a message says so", async ({
    page,
  }) => {
    await stubCapabilities(page, { av1: yes, h264: yes });
    await page.route(/\.mp4(\?|$)/, (route) => route.abort());
    await openCase(page, "D2");
    await page.getByRole("button", { name: "Play the flyover" }).click();
    await expect(page.getByRole("status").filter({ hasText: "could not be loaded" })).toBeVisible();
    const section = page.getByTestId("scene-render");
    await expect(section.locator("video")).toHaveAttribute("poster", /\.webp$/);
    await expect(section.locator("figure[data-still] img")).toHaveCount(3);
    await expect(page.getByTestId("built-with")).toBeVisible();
  });

  test("the page is usable at phone width: no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openCase(page, "B1");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(
      true,
    );
  });
});
