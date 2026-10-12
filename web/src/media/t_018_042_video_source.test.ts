// T-018-042 [red] · FR-018-25 (preload="none", poster, no bytes before play), FR-018-26 (AV1 1080p or H.264 720p by MediaCapabilities),
// FR-018-27 (neither encoding, failed load or failed SHA-256: poster and message, REPLAY badge kept, clock unaffected) and the
// re-seek rule of FR-018-24 (unit part). E2E half: web/e2e/t_018_042_video_cards.spec.ts.
//
// Expected API
//   module `~/media/pickVideoSource` (web/src/media/pickVideoSource.ts):
//     interface VideoFile { id: string; path: string; encoder: { codec: "av1" | "h264"; width: number; height: number; fps: number } }
//     interface MediaCapabilitiesLike { decodingInfo(config: unknown): Promise<unknown> }
//     pickVideoSource(files: VideoFile[], capabilities: MediaCapabilitiesLike | null | undefined): Promise<VideoFile | null>
//         the AV1 file when decodingInfo says `supported === true` and `powerEfficient === true` for it; otherwise the H.264 file when
//         decodingInfo says `supported === true` for it; otherwise null. An absent MediaCapabilities, a rejected or throwing
//         decodingInfo and a malformed answer (anything that is not an object with boolean `supported`) count as "not supported".
//         decodingInfo receives { type: "file", video: { contentType, width, height, bitrate, framerate } } with the file's own
//         width, height and fps and an RFC 6381 codecs string ("av01..." for AV1, "avc1.xxxxxx" for H.264). Never throws.
//   module `~/media/videoSync` (web/src/media/videoSync.ts):
//     needsReseek(mediaTime: number, clockTime: number, fps: number): boolean      true iff |mediaTime - clockTime| > 2 / fps
//   module `~/media/VideoCard` (web/src/media/VideoCard.tsx): named export VideoCard(props: {
//       files: VideoFile[]; posterUrl: string; baseUrl: string; clock: SimClock; title: string;
//       sha256ByPath: Record<string, string>; bytesByPath?: Record<string, number>;
//       mediaCapabilities?: MediaCapabilitiesLike | null; fetchImpl?: typeof fetch })
//     Renders [data-testid="video-card"][data-state="idle|loading|playing|unavailable|integrity-failed"] holding
//     video[data-testid="media-video"][preload="none"][poster=posterUrl] without any src, [data-testid="lane-badge"] "REPLAY" and, when
//     it cannot show the video, the poster plus the text "Video not available in this browser" or "integrity check failed". It fetches
//     `baseUrl + file.path` only when the shared clock starts playing, verifies SHA-256 (see ~/assets/loader) and then sets a blob URL
//     as src. A failure never touches the clock.
//
// Oracles: the EARS text; the truth table of FR-018-26 written below by hand; RFC 6381 codec strings (AV1 `av01`, H.264 `avc1`);
// SHA-256 of the test bytes from node:crypto.
import { createHash } from "node:crypto";
import { act, screen, waitFor } from "@testing-library/react";
import fc from "fast-check";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pickVideoSource, type VideoFile } from "~/media/pickVideoSource";
import { VideoCard } from "~/media/VideoCard";
import { needsReseek } from "~/media/videoSync";
import { createClock } from "~/sim/clock";
import { renderApp } from "~/test-support/render";

const AV1: VideoFile = {
  id: "c2-flood-av1",
  path: "videos/c2-flood-av1.mp4",
  encoder: { codec: "av1", width: 1920, height: 1080, fps: 30 },
};
const H264: VideoFile = {
  id: "c2-flood-h264",
  path: "videos/c2-flood-h264.mp4",
  encoder: { codec: "h264", width: 1280, height: 720, fps: 30 },
};

type Info = { supported: boolean; smooth: boolean; powerEfficient: boolean };
const info = (supported: boolean, powerEfficient = false): Info => ({
  supported,
  smooth: supported,
  powerEfficient,
});

function capabilities(av1: unknown, h264: unknown) {
  const decodingInfo = vi.fn(async (config: { video?: { contentType?: string } }) => {
    const type = config?.video?.contentType ?? "";
    return /av01/i.test(type) ? av1 : h264;
  });
  return { decodingInfo };
}

describe("choice of the video file (FR-018-26)", () => {
  // [AV1 supported, AV1 power efficient, H.264 supported] -> expected id (hand truth table of FR-018-26)
  const table: Array<[boolean, boolean, boolean, string | null]> = [
    [true, true, true, "c2-flood-av1"],
    [true, true, false, "c2-flood-av1"],
    [true, false, true, "c2-flood-h264"],
    [false, false, true, "c2-flood-h264"],
    [false, false, false, null],
  ];
  for (const [sup, eff, h, expected] of table) {
    it(`FR-018-26 · AV1 supported=${sup} powerEfficient=${eff}, H.264 supported=${h} -> ${expected ?? "no file"}`, async () => {
      const picked = await pickVideoSource([AV1, H264], capabilities(info(sup, eff), info(h)));
      expect(picked?.id ?? null).toBe(expected);
    });
  }

  it("FR-018-26 · the file order does not matter", async () => {
    const mc = capabilities(info(true, true), info(true));
    expect((await pickVideoSource([H264, AV1], mc))?.id).toBe("c2-flood-av1");
  });

  it("FR-018-26 · with only an H.264 file the H.264 file is used when it is supported", async () => {
    expect((await pickVideoSource([H264], capabilities(info(true, true), info(true))))?.id).toBe(
      "c2-flood-h264",
    );
    expect(await pickVideoSource([H264], capabilities(info(true, true), info(false)))).toBeNull();
  });

  it("FR-018-26 · with only an AV1 file and no efficient AV1 decoding no file is chosen", async () => {
    expect(await pickVideoSource([AV1], capabilities(info(true, false), info(true)))).toBeNull();
  });

  it("FR-018-26 · no files at all gives null", async () => {
    expect(await pickVideoSource([], capabilities(info(true, true), info(true)))).toBeNull();
  });

  it("FR-018-26 · decodingInfo is asked about each file's own size, frame rate and an RFC 6381 codec string", async () => {
    const mc = capabilities(info(true, true), info(true));
    await pickVideoSource([AV1, H264], mc);
    const configs = mc.decodingInfo.mock.calls.map(
      (c) => c[0] as { type: string; video: Record<string, unknown> },
    );
    const av1 = configs.find((c) => /av01/.test(String(c.video.contentType)));
    expect(av1).toBeDefined();
    expect(av1?.type).toBe("file");
    expect(av1?.video.width).toBe(1920);
    expect(av1?.video.height).toBe(1080);
    expect(av1?.video.framerate).toBe(30);
    expect(Number(av1?.video.bitrate)).toBeGreaterThan(0);
    // the H.264 question, if asked, uses avc1
    for (const c of configs) expect(String(c.video.contentType)).toMatch(/av01|avc1\.[0-9a-fA-F]{6}/);
  });
});

describe("hostile MediaCapabilities (FR-018-27)", () => {
  it("FR-018-27 · an absent MediaCapabilities (undefined or null) means no file", async () => {
    expect(await pickVideoSource([AV1, H264], undefined)).toBeNull();
    expect(await pickVideoSource([AV1, H264], null)).toBeNull();
  });

  it("FR-018-27 · a rejected decodingInfo means not supported, and the other codec can still be chosen", async () => {
    const decodingInfo = vi.fn(async (config: { video?: { contentType?: string } }) => {
      if (/av01/i.test(config?.video?.contentType ?? "")) throw new Error("boom");
      return info(true);
    });
    expect((await pickVideoSource([AV1, H264], { decodingInfo }))?.id).toBe("c2-flood-h264");
    const allReject = { decodingInfo: vi.fn(async () => Promise.reject(new Error("boom"))) };
    expect(await pickVideoSource([AV1, H264], allReject)).toBeNull();
  });

  it("FR-018-27 · a decodingInfo that throws synchronously means not supported", async () => {
    const mc = {
      decodingInfo: () => {
        throw new TypeError("not a function call");
      },
    };
    expect(await pickVideoSource([AV1, H264], mc as never)).toBeNull();
  });

  const malformed: Array<[string, unknown]> = [
    ["undefined", undefined],
    ["null", null],
    ["a string", "supported"],
    ["a number", 1],
    ["an empty object", {}],
    ["a string flag", { supported: "true", powerEfficient: "true" }],
    ["a numeric flag", { supported: 1, powerEfficient: 1 }],
    ["an array", [true, true]],
  ];
  for (const [name, answer] of malformed) {
    it(`FR-018-27 · a malformed answer (${name}) counts as not supported`, async () => {
      expect(await pickVideoSource([AV1, H264], capabilities(answer, answer))).toBeNull();
    });
  }

  it("FR-018-27 · a mediaCapabilities object without decodingInfo means no file and no exception", async () => {
    await expect(pickVideoSource([AV1, H264], {} as never)).resolves.toBeNull();
  });
});

describe("re-seek rule (FR-018-24)", () => {
  it("FR-018-24 · a video exactly two frame periods away is left alone; further away is re-seeked", () => {
    expect(needsReseek(10, 10, 25)).toBe(false);
    expect(needsReseek(10.079, 10, 25)).toBe(false); // 2 / 25 = 0.08 s
    expect(needsReseek(10.081, 10, 25)).toBe(true);
    expect(needsReseek(9.919, 10, 25)).toBe(true);
    expect(needsReseek(9.921, 10, 25)).toBe(false);
    // dyadic numbers make the boundary exact: 2 / 8 = 0.25 s
    expect(needsReseek(10.25, 10, 8)).toBe(false);
    expect(needsReseek(9.75, 10, 8)).toBe(false);
    expect(needsReseek(10.28125, 10, 8)).toBe(true);
    expect(needsReseek(9.71875, 10, 8)).toBe(true);
    expect(needsReseek(0, 1, 10)).toBe(true);
    expect(needsReseek(1, 1.15, 10)).toBe(false);
  });

  it("FR-018-24 · property: the rule is symmetric, and once a distance asks for a re-seek every larger distance does too", () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1000, noNaN: true }),
        fc.double({ min: 0, max: 5, noNaN: true }),
        fc.double({ min: 0, max: 5, noNaN: true }),
        fc.double({ min: 1, max: 120, noNaN: true }),
        (t, a, extra, fps) => {
          const symmetric = needsReseek(t + a, t, fps) === needsReseek(t, t + a, fps);
          const monotone = !needsReseek(t + a, t, fps) || needsReseek(t + a + extra, t, fps);
          return symmetric && monotone;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-24 · a non-finite time never asks for a re-seek", () => {
    expect(needsReseek(Number.NaN, 1, 25)).toBe(false);
    expect(needsReseek(1, Number.NaN, 25)).toBe(false);
  });
});

describe("the media card (FR-018-25, FR-018-27)", () => {
  const bytes = new TextEncoder().encode("not really a video, but bytes are bytes");
  const sha = createHash("sha256").update(bytes).digest("hex");
  const sha256ByPath = { [AV1.path]: sha, [H264.path]: sha };
  const baseUrl = "https://example.org/PitStudio/assets/";
  const supported = capabilities(info(true, true), info(true));

  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: vi.fn(() => "blob:fixture"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(async () => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function show(over: Record<string, unknown> = {}) {
    const clock = createClock({ duration: 10, timeSource: { now: () => 0 } });
    const fetchImpl = vi.fn(async () => new Response(bytes.slice(), { status: 200 }));
    await renderApp(
      createElement(VideoCard, {
        files: [AV1, H264],
        posterUrl: `${baseUrl}videos/c2-flood-poster.webp`,
        baseUrl,
        clock,
        title: "Flood replay",
        sha256ByPath,
        mediaCapabilities: supported,
        fetchImpl: fetchImpl as unknown as typeof fetch,
        ...over,
      }),
    );
    return { clock, fetchImpl };
  }

  it("FR-018-25 · the video element has preload=none, the WebP poster, no src and no source, and the card says REPLAY", async () => {
    const { fetchImpl } = await show();
    const el = document.querySelector('video[data-testid="media-video"]') as HTMLVideoElement;
    expect(el.getAttribute("preload")).toBe("none");
    expect(el.getAttribute("poster")).toBe(`${baseUrl}videos/c2-flood-poster.webp`);
    expect(el.hasAttribute("src")).toBe(false);
    expect(el.querySelector("source")).toBeNull();
    expect(screen.getByTestId("lane-badge").textContent).toBe("REPLAY");
    expect(screen.getByTestId("video-card").getAttribute("data-state")).toBe("idle");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 20));
    });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("FR-018-25 · no bytes are requested until the clock plays; then exactly the chosen file is fetched and the verified blob is set as src", async () => {
    const { clock, fetchImpl } = await show();
    act(() => clock.play());
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));
    expect((fetchImpl.mock.calls[0] as unknown[])[0]).toBe(`${baseUrl}${AV1.path}`);
    const el = document.querySelector('video[data-testid="media-video"]') as HTMLVideoElement;
    await waitFor(() => expect(el.getAttribute("src")).toBe("blob:fixture"));
    expect(["loading", "playing"]).toContain(screen.getByTestId("video-card").getAttribute("data-state"));
  });

  it("FR-018-26 · when AV1 is not power efficient the H.264 file is the one fetched", async () => {
    const { clock, fetchImpl } = await show({
      mediaCapabilities: capabilities(info(true, false), info(true)),
    });
    act(() => clock.play());
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(1));
    expect((fetchImpl.mock.calls[0] as unknown[])[0]).toBe(`${baseUrl}${H264.path}`);
  });

  it("FR-018-27 · neither encoding supported: poster, 'Video not available in this browser', REPLAY kept, clock still runs, nothing fetched", async () => {
    const { clock, fetchImpl } = await show({ mediaCapabilities: capabilities(info(false), info(false)) });
    await waitFor(() =>
      expect(screen.getByTestId("video-card").getAttribute("data-state")).toBe("unavailable"),
    );
    expect(screen.getByText("Video not available in this browser")).toBeTruthy();
    expect(screen.getByTestId("lane-badge").textContent).toBe("REPLAY");
    expect(document.querySelector("video")?.getAttribute("poster")).toContain("c2-flood-poster.webp");
    act(() => clock.play());
    expect(clock.getState().playing).toBe(true);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("FR-018-27 · an absent MediaCapabilities gives the same card", async () => {
    await show({ mediaCapabilities: null });
    await waitFor(() =>
      expect(screen.getByTestId("video-card").getAttribute("data-state")).toBe("unavailable"),
    );
    expect(screen.getByText("Video not available in this browser")).toBeTruthy();
  });

  it("FR-018-27 · bytes that fail the SHA-256 check give 'integrity check failed', keep REPLAY and leave the clock running", async () => {
    const mutated = bytes.slice();
    mutated[0] = (mutated[0] as number) ^ 0xff;
    const fetchImpl = vi.fn(async () => new Response(mutated, { status: 200 }));
    const { clock } = await show({ fetchImpl });
    act(() => clock.play());
    await waitFor(() =>
      expect(screen.getByTestId("video-card").getAttribute("data-state")).toBe("integrity-failed"),
    );
    expect(screen.getByText("integrity check failed")).toBeTruthy();
    expect(screen.getByTestId("lane-badge").textContent).toBe("REPLAY");
    expect(clock.getState().playing).toBe(true);
    expect(document.querySelector("video")?.hasAttribute("src")).toBe(false);
  });

  it("FR-018-27 · a file that cannot be fetched (HTTP 404, then a network error) shows 'Video not available in this browser'", async () => {
    for (const fetchImpl of [
      vi.fn(async () => new Response("missing", { status: 404 })),
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    ]) {
      const { clock } = await show({ fetchImpl });
      act(() => clock.play());
      await waitFor(() =>
        expect(screen.getByTestId("video-card").getAttribute("data-state")).toBe("unavailable"),
      );
      expect(screen.getByText("Video not available in this browser")).toBeTruthy();
      expect(clock.getState().playing).toBe(true);
      document.body.innerHTML = "";
    }
  });
});
