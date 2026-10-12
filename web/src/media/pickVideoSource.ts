// Choice of the replay video file by MediaCapabilities (FR-018-26): the AV1 1080p file when the browser decodes it and says it is
// power efficient, else the H.264 720p file when it decodes it, else none. An absent, failing or malformed MediaCapabilities counts
// as "not supported" (FR-018-27); nothing here throws.

export interface VideoFile {
  id: string;
  path: string;
  encoder: { codec: "av1" | "h264"; width: number; height: number; fps: number };
}

export interface MediaCapabilitiesLike {
  decodingInfo(config: unknown): Promise<unknown>;
}

/** RFC 6381 codec string: AV1 main profile level 4.0 (8-bit), H.264 High profile at level 3.1 (720p) or 4.0 (1080p). */
function codecString(file: VideoFile): string {
  if (file.encoder.codec === "av1") return "av01.0.08M.08";
  return file.encoder.height > 720 ? "avc1.640028" : "avc1.64001f";
}

/** A planning bit rate for the question to MediaCapabilities: 0.07 bit per pixel and frame. */
function bitrate(file: VideoFile): number {
  const { width, height, fps } = file.encoder;
  return Math.max(1, Math.round(width * height * fps * 0.07));
}

async function ask(
  capabilities: MediaCapabilitiesLike,
  file: VideoFile,
): Promise<{ supported: boolean; efficient: boolean }> {
  try {
    const answer: unknown = await capabilities.decodingInfo({
      type: "file",
      video: {
        contentType: `video/mp4; codecs="${codecString(file)}"`,
        width: file.encoder.width,
        height: file.encoder.height,
        bitrate: bitrate(file),
        framerate: file.encoder.fps,
      },
    });
    if (answer === null || typeof answer !== "object" || Array.isArray(answer))
      return { supported: false, efficient: false };
    const info = answer as { supported?: unknown; powerEfficient?: unknown };
    return { supported: info.supported === true, efficient: info.powerEfficient === true };
  } catch {
    return { supported: false, efficient: false };
  }
}

export async function pickVideoSource(
  files: VideoFile[],
  capabilities: MediaCapabilitiesLike | null | undefined,
): Promise<VideoFile | null> {
  if (!capabilities || typeof capabilities.decodingInfo !== "function") return null;
  const av1 = files.find((f) => f.encoder.codec === "av1");
  if (av1) {
    const info = await ask(capabilities, av1);
    if (info.supported && info.efficient) return av1;
  }
  const h264 = files.find((f) => f.encoder.codec === "h264");
  if (h264) {
    const info = await ask(capabilities, h264);
    if (info.supported) return h264;
  }
  return null;
}
