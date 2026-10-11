import { useEffect, useState } from "react";
import { type ArtefactRecord, isCaseId, LAYER_IDS, type LayerId } from "./types";

const LANES = new Set(["live", "replay", "static"]);
const MAX_ARTEFACTS = 5000;

function str(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 400;
}

function readArtefact(raw: unknown): ArtefactRecord | null {
  if (typeof raw !== "object" || raw === null) return null;
  const a = raw as Record<string, unknown>;
  const producer = a.producer as { tool?: unknown } | undefined;
  if (!str(a.id) || !str(a.run_id) || !str(a.git_sha) || !str(a.path) || !str(a.kind)) return null;
  if (typeof a.lane !== "string" || !LANES.has(a.lane)) return null;
  if (!producer || !str(producer.tool)) return null;
  const cases = Array.isArray(a.cases)
    ? a.cases.filter((c): c is string => typeof c === "string")
    : undefined;
  return { ...(a as unknown as ArtefactRecord), cases };
}

/**
 * Artefact records of a web manifest (`kind: "web-index"`). Anything that is not a well-formed index gives an empty
 * list, and a malformed record is dropped on its own: a damaged manifest never breaks the page and never shows a
 * result (ADR-0040: an artefact that cannot be read is "Not yet run").
 */
export function parseWebIndex(raw: unknown): ArtefactRecord[] {
  if (typeof raw !== "object" || raw === null) return [];
  const index = raw as { kind?: unknown; artefacts?: unknown };
  if (index.kind !== "web-index" || !Array.isArray(index.artefacts)) return [];
  const out: ArtefactRecord[] = [];
  for (const item of index.artefacts.slice(0, MAX_ARTEFACTS)) {
    const record = readArtefact(item);
    if (record) out.push(record);
  }
  return out;
}

/** An artefact belongs to a case when its `cases` array is absent or empty (all cases) or lists it (data-model 001 2.5). */
export function appliesToCase(artefact: ArtefactRecord, caseId: string): boolean {
  return !artefact.cases || artefact.cases.length === 0 || artefact.cases.includes(caseId);
}

/** Layers with a published artefact for the case: an artefact whose id starts with `layer-<layer id>` (FR-018-04). */
export function publishedLayers(artefacts: readonly ArtefactRecord[], caseId: string): Set<LayerId> {
  const out = new Set<LayerId>();
  if (!isCaseId(caseId)) return out;
  for (const layer of LAYER_IDS) {
    if (artefacts.some((a) => a.id.startsWith(`layer-${layer}`) && appliesToCase(a, caseId))) out.add(layer);
  }
  return out;
}

/** Artefacts that name the case explicitly (the Studio replay tab lists these, FR-018-15). */
export function artefactsOfCase(artefacts: readonly ArtefactRecord[], caseId: string): ArtefactRecord[] {
  return artefacts.filter((a) => a.cases?.includes(caseId));
}

/** The run id of the newest run among the artefacts (run ids start with a UTC timestamp, so they sort by time). */
export function latestRunId(artefacts: readonly ArtefactRecord[]): string | null {
  let best: string | null = null;
  for (const a of artefacts) if (best === null || a.run_id > best) best = a.run_id;
  return best;
}

export interface WebManifest {
  /** `loading` until the fetch settled; `ready` with an empty list when nothing is published or the file is unusable. */
  status: "loading" | "ready";
  artefacts: ArtefactRecord[];
}

/** Fetches `<base>assets/manifest.json` once in the browser. A missing, failing or malformed file is "nothing published". */
export function useWebManifest(): WebManifest {
  const [state, setState] = useState<WebManifest>({ status: "loading", artefacts: [] });

  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}assets/manifest.json`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => setState({ status: "ready", artefacts: parseWebIndex(json) }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "ready", artefacts: [] });
      });
    return () => controller.abort();
  }, []);

  return state;
}
