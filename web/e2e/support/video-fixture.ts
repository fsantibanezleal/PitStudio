// Shared, locked E2E support (first used by T-018-041; also T-018-042). Not a test file.
//
// Builds a real, seekable WebM (VP8) video at test time with Playwright's own recorder (no binary is committed), plus the web
// manifest records and route stubs that make a case page list it as a replay video of case C2:
//   artefacts  c2-flood-av1 (codec av1, 1920 x 1080), c2-flood-h264 (codec h264, 1280 x 720), c2-flood-poster (image/webp)
// Both video artefacts serve the same VP8 bytes (the browser sniffs the container, so the declared codec only drives the choice of
// file, FR-018-26). The recorder writes 25 fps, which is therefore the `encoder.fps` of the fixture.
// Observation hooks used with it (see t_018_041, t_018_042):
//   [data-testid="sim-clock"][data-t][data-playing][data-duration]        the page clock, with the controls "Play" / "Pause",
//                                                                          "Step back", "Step forward" and the "Time" slider
//   [data-testid="video-card"][data-state]  idle | loading | playing | unavailable | integrity-failed, containing
//        video[data-testid="media-video"], [data-testid="lane-badge"] and the message texts of FR-018-27
//   window.__pitstudio.clock               the page's SimClock ({ tick(), getState(): { t, rate, playing } })
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import type { Browser, Page } from "@playwright/test";
import { makeArtefact, makeWebIndex } from "../../src/test-support/fixtures";

export interface FixtureVideo {
  bytes: Buffer;
  sha256: string;
  fps: number;
  frames: number;
  duration_s: number;
}

export const TINY_WEBP = Buffer.from("UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA==", "base64");
export const FIXTURE_FPS = 25;

export async function makeFixtureVideo(browser: Browser): Promise<FixtureVideo> {
  const dir = process.env.PITSTUDIO_E2E_TMP ?? "test-results/video-fixture";
  const context = await browser.newContext({ recordVideo: { dir, size: { width: 320, height: 240 } } });
  const page = await context.newPage();
  await page.setContent(
    `<body style="margin:0;background:#123"><div id="b" style="width:40px;height:40px;background:#fc0;position:absolute"></div>
     <script>let x=0;setInterval(()=>{x=(x+7)%280;document.getElementById('b').style.left=x+'px'},20)</script></body>`,
  );
  await page.waitForTimeout(4200);
  const video = page.video();
  await context.close();
  const path = await video?.path();
  if (!path) throw new Error("the recorder produced no video");
  const bytes = readFileSync(path);
  const probe = await browser.newPage();
  const duration = await probe.evaluate(async (b64: string) => {
    const blob = await (await fetch(`data:video/webm;base64,${b64}`)).blob();
    const el = document.createElement("video");
    el.src = URL.createObjectURL(blob);
    await new Promise<void>((resolve, reject) => {
      el.onloadedmetadata = () => resolve();
      el.onerror = () => reject(new Error("fixture video cannot be decoded"));
    });
    return el.duration;
  }, bytes.toString("base64"));
  await probe.close();
  const d = Number.isFinite(duration) && duration > 0 ? duration : 4;
  return {
    bytes,
    sha256: createHash("sha256").update(bytes).digest("hex"),
    fps: FIXTURE_FPS,
    frames: Math.round(d * FIXTURE_FPS),
    duration_s: d,
  };
}

function encoder(codec: "av1" | "h264", v: FixtureVideo) {
  return {
    codec,
    profile: codec === "av1" ? "main" : "high",
    pix_fmt: "yuv420p",
    width: codec === "av1" ? 1920 : 1280,
    height: codec === "av1" ? 1080 : 720,
    fps: v.fps,
    frames: v.frames,
    duration_s: v.duration_s,
    bitrate_kbps: 800,
    vmaf: { mean: 95, p5: 90, model: "vmaf_v0.6.1" },
    source_frames_sha256: "b".repeat(64),
    encoder: { ffmpeg_version: "7.1", build_sha256: "c".repeat(64), nvenc_api: null, args: [] },
    encode_fps: null,
  };
}

/** The web manifest of the fixture: two video files of one replay video of case C2 and its WebP poster. */
export function videoManifest(v: FixtureVideo, files: { av1?: Buffer; h264?: Buffer } = {}) {
  const av1 = files.av1 ?? v.bytes;
  const h264 = files.h264 ?? v.bytes;
  const sha = (b: Buffer) => createHash("sha256").update(b).digest("hex");
  return makeWebIndex([
    makeArtefact({
      id: "c2-flood-av1",
      kind: "video",
      path: "videos/c2-flood-av1.webm",
      bytes: av1.length,
      sha256: v.sha256,
      cases: ["C2"],
      lane: "replay",
      budget_class: "videos",
      producer: { tool: "nvenc-ffmpeg", stage: { id: "st56_encode" } },
      ...({ encoder: encoder("av1", v), media_type: "video/webm" } as object),
    }),
    makeArtefact({
      id: "c2-flood-h264",
      kind: "video",
      path: "videos/c2-flood-h264.webm",
      bytes: h264.length,
      sha256: v.sha256,
      cases: ["C2"],
      lane: "replay",
      budget_class: "videos",
      producer: { tool: "nvenc-ffmpeg", stage: { id: "st56_encode" } },
      ...({ encoder: encoder("h264", v), media_type: "video/webm" } as object),
    }),
    makeArtefact({
      id: "c2-flood-poster",
      kind: "image",
      path: "videos/c2-flood-poster.webp",
      bytes: TINY_WEBP.length,
      sha256: sha(TINY_WEBP),
      cases: ["C2"],
      lane: "static",
      budget_class: "own-code",
      producer: { tool: "nvenc-ffmpeg", stage: { id: "st56_encode" } },
    }),
  ]);
}

export interface VideoRoutes {
  requested: () => string[];
}

/** Serves the fixture manifest, both video files (optionally replaced bytes) and the poster; records the video requests. */
export async function routeVideo(
  page: Page,
  v: FixtureVideo,
  files: { av1?: Buffer; h264?: Buffer } = {},
): Promise<VideoRoutes> {
  const requested: string[] = [];
  const manifest = videoManifest(v, files);
  await page.route("**/assets/manifest.json", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(manifest) }),
  );
  await page.route("**/assets/videos/c2-flood-av1.webm", (route) => {
    requested.push("av1");
    return route.fulfill({ contentType: "video/webm", body: files.av1 ?? v.bytes });
  });
  await page.route("**/assets/videos/c2-flood-h264.webm", (route) => {
    requested.push("h264");
    return route.fulfill({ contentType: "video/webm", body: files.h264 ?? v.bytes });
  });
  await page.route("**/assets/videos/c2-flood-poster.webp", (route) =>
    route.fulfill({ contentType: "image/webp", body: TINY_WEBP }),
  );
  return { requested: () => [...requested] };
}

/** Stubs MediaCapabilities.decodingInfo per codec (matched on the content type: "av01" or "avc1"). */
export async function stubCapabilities(
  page: Page,
  answers: { av1?: unknown; h264?: unknown } | "absent" | "rejects",
): Promise<void> {
  await page.addInitScript((a) => {
    if (a === "absent") {
      Object.defineProperty(navigator, "mediaCapabilities", { value: undefined, configurable: true });
      return;
    }
    const decodingInfo = (config: { video?: { contentType?: string } }) => {
      if (a === "rejects") return Promise.reject(new Error("decodingInfo failed"));
      const type = config?.video?.contentType ?? "";
      const key = /av01|av1/i.test(type) ? "av1" : "h264";
      return Promise.resolve(
        (a as Record<string, unknown>)[key] ?? { supported: false, smooth: false, powerEfficient: false },
      );
    };
    Object.defineProperty(navigator, "mediaCapabilities", { value: { decodingInfo }, configurable: true });
  }, answers);
}
