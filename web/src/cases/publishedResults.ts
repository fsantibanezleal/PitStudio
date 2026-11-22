// The published results of a case: the summary artefact of each published run of the case (written by `studio import-run`) and
// the tools of that run's stages, read from its published manifest. A file that is missing or malformed is nothing published (ADR-0040).
import { useEffect, useState } from "react";
import type { ArtefactRecord } from "./types";

export interface Headline {
  name: string;
  value: number;
  unit: string;
  note?: string;
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
}

const text = (v: unknown, max = 400): v is string => typeof v === "string" && v.length > 0 && v.length <= max;
const isHeadline = (h: unknown): h is Headline =>
  typeof h === "object" &&
  h !== null &&
  text((h as Headline).name) &&
  Number.isFinite((h as Headline).value) &&
  text((h as Headline).unit, 40);

export function readResult(raw: unknown, manifest: unknown, runId: string): PublishedResult | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (!text(r.title) || !text(r.label) || !Array.isArray(r.headline)) return null;
  const headline = (r.headline as unknown[])
    .filter(isHeadline)
    .map((h) => ({ name: h.name, value: h.value, unit: h.unit, ...(text(h.note) ? { note: h.note } : {}) }));
  const m = (typeof manifest === "object" && manifest !== null ? manifest : {}) as {
    stages?: Array<{ tool?: unknown }>;
    notes?: unknown[];
  };
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
    partial: (m.notes ?? []).some((n) => typeof n === "string" && n.startsWith("partial:")),
  };
}

export interface PublishedCase {
  status: "loading" | "ready";
  results: PublishedResult[];
  usedTools: Set<string>;
  usedMethods: Set<string>;
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
        readResult(await get(a.path), await get(`assets/runs/${a.run_id}/manifest.json`), a.run_id),
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
