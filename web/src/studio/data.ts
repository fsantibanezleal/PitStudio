// The data of the studio pages: the registry entries and the studio index written at build time by
// `web/scripts/build-studio-index.mjs` (DC-019-03), and the hooks that read the published runs in the browser.
// A file that is missing, failing or malformed is "nothing published" (ADR-0040): it never breaks a page and never shows a result.
import { useEffect, useState } from "react";
import { parseWebIndex } from "~/cases/manifest";
import { caseRegistry } from "~/cases/registry";
import { type ArtefactRecord, CASE_IDS } from "~/cases/types";
import data from "./generated/studio-data.json";
import type { PublishedTelemetry } from "./telemetry/GpuTimelines";
import type { RunCard, StudioIndex, StudioTool } from "./types";

export const studioTools = data.tools as unknown as StudioTool[];
export const studioIndex = data.index as unknown as StudioIndex;
/** Run ids published in the Pages artifact when this site was built (the pages of these ids are prerendered). */
export const publishedRunIds: string[] = (data as unknown as { run_ids?: string[] }).run_ids ?? [];
export { caseRegistry };
export const caseIds: readonly string[] = CASE_IDS;

/** Run id pattern of data-model 001 section 1.3. Anything else is never turned into a request address. */
export const RUN_ID = /^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$/;

const TOOL_IDS = new Set(studioTools.map((t) => t.id));
const RUN_IDS = new Set(publishedRunIds);

/** The registry entry of an id; only an exact id of the 20 studio ids qualifies (no case folding, no decoding). */
export function toolById(id: string | undefined): StudioTool | undefined {
  return id !== undefined && TOOL_IDS.has(id) ? studioTools.find((t) => t.id === id) : undefined;
}

export function isPublishedRun(id: string | undefined): id is string {
  return id !== undefined && RUN_IDS.has(id);
}

const base = () => import.meta.env.BASE_URL;

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  try {
    const response = await fetch(`${base()}${path}`, { signal });
    return response.ok ? await response.json() : null;
  } catch {
    return null;
  }
}

export interface Loaded<T> {
  status: "loading" | "ready";
  value: T;
}

/** The slim cards of the runs published with this build, part of the prerendered page data: the ledger and the loop read these. */
export const studioRuns: RunCard[] = (data as unknown as { runs?: RunCard[] }).runs ?? [];
const READY: Loaded<RunCard[]> = { status: "ready", value: studioRuns };

export function useRunSummaries(): Loaded<RunCard[]> {
  return READY;
}
export interface StudioManifest {
  artefacts: ArtefactRecord[];
  /** Run ids the web manifest lists as published (`runs[].run_id`). */
  runs: string[];
}

/** The web manifest: the artefacts of every published run and the ids of those runs. */
export function useStudioManifest(): Loaded<StudioManifest> {
  const [state, setState] = useState<Loaded<StudioManifest>>({
    status: "loading",
    value: { artefacts: [], runs: [] },
  });
  useEffect(() => {
    const controller = new AbortController();
    void getJson("assets/manifest.json", controller.signal).then((raw) => {
      if (controller.signal.aborted) return;
      const list = (raw as { runs?: unknown } | null)?.runs;
      const runs = Array.isArray(list)
        ? list
            .map((r) => (r as { run_id?: unknown } | null)?.run_id)
            .filter((id): id is string => typeof id === "string" && RUN_ID.test(id))
        : [];
      setState({ status: "ready", value: { artefacts: parseWebIndex(raw), runs } });
    });
    return () => controller.abort();
  }, []);
  return state;
}

const acceptCard = (raw: unknown): RunCard | null =>
  typeof raw === "object" &&
  raw !== null &&
  Array.isArray((raw as RunCard).stages) &&
  Array.isArray((raw as RunCard).artefacts) &&
  typeof (raw as RunCard).run_id === "string"
    ? (raw as RunCard)
    : null;

const acceptTelemetry = (raw: unknown): PublishedTelemetry | null =>
  typeof raw === "object" && raw !== null && Array.isArray((raw as PublishedTelemetry).stages)
    ? (raw as PublishedTelemetry)
    : null;

export interface RunBundle {
  card: RunCard;
  telemetry: PublishedTelemetry | null;
}

/** The full card (and, when asked, the published telemetry) of each run id; ids that are not well-formed are never requested. */
export function useRunBundles(ids: readonly string[], withTelemetry: boolean): Loaded<RunBundle[]> {
  const key = [...new Set(ids.filter((id) => RUN_ID.test(id)))].sort().join("\n");
  const [state, setState] = useState<Loaded<RunBundle[]>>({ status: "loading", value: [] });
  useEffect(() => {
    if (key === "") {
      setState({ status: "ready", value: [] });
      return;
    }
    const controller = new AbortController();
    void Promise.all(
      key.split("\n").map(async (id) => {
        const card = acceptCard(
          await getJson(`assets/runs/${encodeURIComponent(id)}/manifest.json`, controller.signal),
        );
        if (card === null || card.run_id !== id) return null;
        const telemetry = withTelemetry
          ? acceptTelemetry(
              await getJson(`assets/runs/${encodeURIComponent(id)}/telemetry.json`, controller.signal),
            )
          : null;
        return { card, telemetry } satisfies RunBundle;
      }),
    ).then((bundles) => {
      if (!controller.signal.aborted)
        setState({ status: "ready", value: bundles.filter((b): b is RunBundle => b !== null) });
    });
    return () => controller.abort();
  }, [key, withTelemetry]);
  return state;
}
