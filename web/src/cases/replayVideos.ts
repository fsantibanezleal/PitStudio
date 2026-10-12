import type { VideoFile } from "~/media/pickVideoSource";
import type { ArtefactRecord } from "./types";

/** A replay video of a case: its encodings (one artefact each), its WebP poster and the checksums to verify them against. */
export interface ReplayVideo {
  id: string;
  files: VideoFile[];
  durationS: number;
  poster: ArtefactRecord | null;
  sha256ByPath: Record<string, string>;
  bytesByPath: Record<string, number>;
}

interface EncoderJson {
  codec?: unknown;
  width?: unknown;
  height?: unknown;
  fps?: unknown;
  duration_s?: unknown;
}

const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v > 0;
const SUFFIX = /-(av1|h264)$/;

/**
 * The replay videos of a case from the web manifest: video artefacts of lane REPLAY that list the case and carry an encoder record,
 * grouped by their id without the codec suffix (`c2-flood-av1` and `c2-flood-h264` are one video), each with the static image
 * `<id>-poster` of the same case.
 */
export function replayVideosOf(artefacts: readonly ArtefactRecord[], caseId: string): ReplayVideo[] {
  const groups = new Map<string, ReplayVideo>();
  for (const a of artefacts) {
    if (a.kind !== "video" || a.lane !== "replay" || !a.cases?.includes(caseId)) continue;
    const encoder = (a as unknown as { encoder?: EncoderJson }).encoder;
    if (!encoder || (encoder.codec !== "av1" && encoder.codec !== "h264")) continue;
    if (!num(encoder.width) || !num(encoder.height) || !num(encoder.fps)) continue;
    const key = a.id.replace(SUFFIX, "");
    const group = groups.get(key) ?? {
      id: key,
      files: [],
      durationS: 0,
      poster: null,
      sha256ByPath: {},
      bytesByPath: {},
    };
    group.files.push({
      id: a.id,
      path: a.path,
      encoder: { codec: encoder.codec, width: encoder.width, height: encoder.height, fps: encoder.fps },
    });
    if (num(encoder.duration_s)) group.durationS = Math.max(group.durationS, encoder.duration_s);
    group.sha256ByPath[a.path] = a.sha256;
    group.bytesByPath[a.path] = a.bytes;
    groups.set(key, group);
  }
  for (const group of groups.values()) {
    group.poster =
      artefacts.find(
        (a) => a.id === `${group.id}-poster` && a.kind === "image" && a.cases?.includes(caseId),
      ) ?? null;
  }
  return [...groups.values()];
}

/** The longest replay video of a case sets the time axis of its clock. */
export function replayDuration(videos: readonly ReplayVideo[]): number | null {
  const longest = Math.max(0, ...videos.map((v) => v.durationS));
  return longest > 0 ? longest : null;
}
