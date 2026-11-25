// FR-018-73: the render shown on every case page. The newest published render run that applies to the case is found in the web
// index (its `render.json` summary artefact, written by `studio import-run` kind render), the summary is read from it and its
// files are looked up in the same index. Pure functions first, then the hook that fetches the summary; a file that is missing or
// malformed is nothing published (ADR-0040), and a newer run replaces the older by publishing alone.
import { useEffect, useState } from "react";
import type { VideoFile } from "~/media/pickVideoSource";
import { appliesToCase } from "./manifest";
import type { ArtefactRecord } from "./types";

export interface RenderStill {
  artefact: ArtefactRecord;
  /** Flyover time of the frame, in seconds. */
  tS: number;
}

export interface RenderVideo {
  files: VideoFile[];
  sha256ByPath: Record<string, string>;
  bytesByPath: Record<string, number>;
}

export interface RenderModel {
  runId: string;
  label: string;
  title: { en: string; es: string };
  producer: { tool: string; version: string };
  /** Registry ids of the tools of the render, in the order the summary lists them. */
  builtWith: string[];
  /** The WebP poster of the clip (also shown when the video files are missing). */
  poster: ArtefactRecord | null;
  video: RenderVideo | null;
  stills: RenderStill[];
}

export interface RenderState {
  /** `loading` until the manifest and the summary settled; `ready` with a null model when nothing usable is published. */
  status: "loading" | "ready";
  model: RenderModel | null;
}

const MAX_STILLS = 12;

const text = (v: unknown, max = 400): v is string => typeof v === "string" && v.length > 0 && v.length <= max;
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v > 0;
const record = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** Render summaries of the web index that apply to the case, newest run first (run ids start with a UTC timestamp). */
export function renderCandidates(artefacts: readonly ArtefactRecord[], caseId: string): ArtefactRecord[] {
  return artefacts
    .filter(
      (a) =>
        a.kind === "table" &&
        a.id.endsWith("-render") &&
        a.path.endsWith("/render.json") &&
        appliesToCase(a, caseId),
    )
    .sort((a, b) =>
      a.run_id !== b.run_id ? (a.run_id < b.run_id ? 1 : -1) : a.id < b.id ? -1 : a.id > b.id ? 1 : 0,
    );
}

function posterOf(raw: unknown, own: Map<string, ArtefactRecord>): ArtefactRecord | null {
  const poster = record(raw) && typeof raw.poster === "string" ? own.get(raw.poster) : undefined;
  return poster?.kind === "image" ? poster : null;
}

function videoOf(raw: unknown, own: Map<string, ArtefactRecord>): RenderVideo | null {
  if (!record(raw) || !Array.isArray(raw.files)) return null;
  const video: RenderVideo = { files: [], sha256ByPath: {}, bytesByPath: {} };
  for (const id of raw.files) {
    const a = typeof id === "string" ? own.get(id) : undefined;
    const e = (a as unknown as { encoder?: Record<string, unknown> } | undefined)?.encoder;
    if (a?.kind !== "video" || !e || (e.codec !== "av1" && e.codec !== "h264")) continue;
    if (!num(e.width) || !num(e.height) || !num(e.fps)) continue;
    video.files.push({
      id: a.id,
      path: a.path,
      encoder: { codec: e.codec, width: e.width, height: e.height, fps: e.fps },
    });
    video.sha256ByPath[a.path] = a.sha256;
    video.bytesByPath[a.path] = a.bytes;
  }
  return video.files.length > 0 ? video : null;
}

/** The model of a render summary, or null when the summary is damaged, of another run, or lacks a label or a producer. */
export function readRender(
  raw: unknown,
  artefacts: readonly ArtefactRecord[],
  summary: ArtefactRecord,
): RenderModel | null {
  if (!record(raw) || raw.kind !== "render-summary" || raw.run_id !== summary.run_id) return null;
  const producer = raw.producer;
  if (!text(raw.label, 200) || !record(producer) || !text(producer.tool, 64) || !text(producer.version, 64))
    return null;
  if (!Array.isArray(raw.stills)) return null;
  const own = new Map(artefacts.filter((a) => a.run_id === summary.run_id).map((a) => [a.id, a]));
  const stills: RenderStill[] = [];
  for (const s of raw.stills.slice(0, MAX_STILLS)) {
    if (!record(s) || typeof s.artefact !== "string" || typeof s.t_s !== "number" || !Number.isFinite(s.t_s))
      continue;
    const a = own.get(s.artefact);
    if (a?.kind === "image") stills.push({ artefact: a, tS: s.t_s });
  }
  stills.sort((a, b) => a.tS - b.tS);
  const title = record(raw.title) ? raw.title : {};
  const pickTitle = (lang: "en" | "es") => (text(title[lang], 200) ? (title[lang] as string) : "");
  return {
    runId: summary.run_id,
    label: raw.label,
    title: { en: pickTitle("en"), es: pickTitle("es") || pickTitle("en") },
    producer: { tool: producer.tool, version: producer.version },
    builtWith: Array.isArray(raw.built_with) ? raw.built_with.filter((t): t is string => text(t, 64)) : [],
    poster: posterOf(raw.video, own),
    video: videoOf(raw.video, own),
    stills,
  };
}

const LOADING: RenderState = { status: "loading", model: null };

/** Fetches the render summary of the newest usable run that applies to the case, once per set of artefacts. */
export function useRenderSummary(
  caseId: string,
  artefacts: readonly ArtefactRecord[],
  ready: boolean,
): RenderState {
  const [state, setState] = useState<RenderState>(LOADING);
  const key = artefacts.map((a) => `${a.run_id}/${a.id}`).join("|");
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` stands for the artefact list
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const base = import.meta.env.BASE_URL;
    void (async () => {
      for (const candidate of renderCandidates(artefacts, caseId)) {
        const raw = await fetch(`${base}${candidate.path}`, { signal: controller.signal })
          .then((res) => (res.ok ? res.json() : null))
          .catch(() => null);
        const model = readRender(raw, artefacts, candidate);
        if (controller.signal.aborted) return;
        if (model) return setState({ status: "ready", model });
      }
      if (!controller.signal.aborted) setState({ status: "ready", model: null });
    })();
    return () => controller.abort();
  }, [caseId, key, ready]);
  return state;
}
