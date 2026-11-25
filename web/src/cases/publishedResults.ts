// The published results of a case: the summary artefact of each published run of the case (written by `studio import-run`) and
// the tools of that run's stages, read from its published manifest. A file that is missing or malformed is nothing published (ADR-0040).
import { createContext, useContext, useEffect, useState } from "react";
import { useWebManifest } from "./manifest";
import type { ArtefactRecord } from "./types";

export interface Headline {
  name: string;
  value: number;
  unit: string;
  note?: string;
  /** The id of the case KPI the value measures, named by the summary itself (FR-018-74); never guessed. */
  kpi?: string;
}
export interface PublishedResult {
  runId: string;
  title: string;
  label: string;
  verdict: "ok" | "partial" | "failed";
  methods: string[];
  tools: string[];
  headline: Headline[];
  rows: Array<Record<string, unknown>>;
  partial: boolean;
  /** The reasons after "partial:" in the run notes. */
  partialReasons: string[];
  /** The run was recorded by `studio import-run` from a queue job (profile "imported"). */
  imported: boolean;
  /** The queue job named in the run notes, when it names one. */
  job: string | null;
  /** The web-manifest record of the summary the headline values come from. */
  artefact: ArtefactRecord | null;
}

const text = (v: unknown, max = 400): v is string => typeof v === "string" && v.length > 0 && v.length <= max;
/** `job 21-dem-repose-n20k; script sha256 ...` (the note `studio import-run` writes). */
const JOB = /^job ([0-9]{2,3}-[a-z0-9][a-z0-9-]{0,60})(?:;|$)/;
const isHeadline = (h: unknown): h is Headline =>
  typeof h === "object" &&
  h !== null &&
  text((h as Headline).name) &&
  Number.isFinite((h as Headline).value) &&
  text((h as Headline).unit, 40);

export function readResult(
  raw: unknown,
  manifest: unknown,
  runId: string,
  artefact: ArtefactRecord | null = null,
): PublishedResult | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (!text(r.title) || !text(r.label) || !Array.isArray(r.headline)) return null;
  const headline = (r.headline as unknown[]).filter(isHeadline).map((h) => ({
    name: h.name,
    value: h.value,
    unit: h.unit,
    ...(text(h.note) ? { note: h.note } : {}),
    ...(text(h.kpi, 80) ? { kpi: h.kpi } : {}),
  }));
  const m = (typeof manifest === "object" && manifest !== null ? manifest : {}) as {
    stages?: Array<{ tool?: unknown }>;
    notes?: unknown[];
    profile?: unknown;
  };
  const notes = (m.notes ?? []).filter((n): n is string => typeof n === "string");
  const tools = [
    ...new Set((m.stages ?? []).map((s) => s.tool).filter((t): t is string => typeof t === "string")),
  ];
  const verdict = r.verdict === "failed" || r.verdict === "partial" ? r.verdict : "ok";
  return {
    runId,
    title: r.title,
    label: r.label,
    verdict,
    methods: Array.isArray(r.methods) ? r.methods.filter((x): x is string => typeof x === "string") : [],
    tools,
    headline,
    rows: Array.isArray(r.rows) ? (r.rows.slice(0, 30) as Array<Record<string, unknown>>) : [],
    partial: notes.some((n) => n.startsWith("partial:")),
    partialReasons: notes
      .filter((n) => n.startsWith("partial:"))
      .map((n) => n.slice("partial:".length).trim()),
    imported: m.profile === "imported",
    job: notes.map((n) => JOB.exec(n)?.[1]).find((j) => j !== undefined) ?? null,
    artefact,
  };
}

export interface PublishedCase {
  status: "loading" | "ready";
  results: PublishedResult[];
  usedTools: Set<string>;
  usedMethods: Set<string>;
}

/** Set by the case story: the published results of the case page, read once for every component below it. */
export const PublishedCaseContext = createContext<PublishedCase | null>(null);

/** The published results of a case: from the case story when there is one, else read here (Explore and Simulate routes). */
export function usePublishedCase(caseId: string): PublishedCase {
  const shared = useContext(PublishedCaseContext);
  const manifest = useWebManifest();
  const own = usePublishedResults(caseId, manifest.artefacts, shared === null && manifest.status === "ready");
  return shared ?? own;
}

const EMPTY: PublishedCase = { status: "loading", results: [], usedTools: new Set(), usedMethods: new Set() };

/** Fetches the summary and the run manifest of every published run of the case, once per set of artefacts. */
export function usePublishedResults(
  caseId: string,
  artefacts: readonly ArtefactRecord[],
  ready: boolean,
): PublishedCase {
  const [state, setState] = useState<PublishedCase>(EMPTY);
  const key = artefacts.map((a) => a.id).join("|");
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` stands for the artefact list
  useEffect(() => {
    if (!ready) return;
    const controller = new AbortController();
    const base = import.meta.env.BASE_URL;
    const get = (path: string) =>
      fetch(`${base}${path}`, { signal: controller.signal })
        .then((res) => (res.ok ? res.json() : null))
        .catch(() => null);
    const own = artefacts.filter((a) => a.id.endsWith("-results") && a.cases?.includes(caseId));
    void Promise.all(
      own.map(async (a) =>
        readResult(await get(a.path), await get(`assets/runs/${a.run_id}/manifest.json`), a.run_id, a),
      ),
    ).then((list) => {
      if (controller.signal.aborted) return;
      const results = list.filter((r): r is PublishedResult => r !== null);
      // a failed evaluation is shown as a result but never counts as a method or tool used in a working result
      const working = results.filter((r) => r.verdict !== "failed");
      setState({
        status: "ready",
        results,
        usedTools: new Set(working.flatMap((r) => r.tools)),
        usedMethods: new Set(working.flatMap((r) => r.methods)),
      });
    });
    return () => controller.abort();
  }, [caseId, key, ready]);
  return state;
}
