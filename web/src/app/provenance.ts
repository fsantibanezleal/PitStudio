// FR-018-75: the footer provenance line, from the runs the web manifest lists.
import { useEffect, useState } from "react";
import type { ProvenanceItem } from "~/shell/config";

/** Items of the footer line for a published-run count: null while the manifest is being read. */
export function provenanceItems(runs: number | null): ProvenanceItem[] {
  if (runs === null) return [{ labelKey: "footer.provenanceLoading" }];
  if (runs === 0) return [{ labelKey: "footer.provenanceNone" }];
  return [{ labelKey: "footer.provenanceRuns", values: { count: runs }, href: "/studio/runs/" }];
}

/** Distinct run ids of the web index: its `runs` list and the run of every artefact record. A damaged file lists none. */
export function countRuns(index: unknown): number {
  if (typeof index !== "object" || index === null) return 0;
  const { kind, runs, artefacts } = index as { kind?: unknown; runs?: unknown; artefacts?: unknown };
  if (kind !== "web-index") return 0;
  const ids = new Set<string>();
  for (const list of [runs, artefacts])
    if (Array.isArray(list))
      for (const x of list) {
        const id = (x as { run_id?: unknown } | null)?.run_id;
        if (typeof id === "string" && id.length > 0) ids.add(id);
      }
  return ids.size;
}

/** The footer line of the app: reads `assets/manifest.json` once; a missing or unreadable file is "none published". */
export function usePublishedProvenance(): ProvenanceItem[] {
  const [runs, setRuns] = useState<number | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${import.meta.env.BASE_URL}assets/manifest.json`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((json) => setRuns(countRuns(json)))
      .catch(() => {
        if (!controller.signal.aborted) setRuns(0);
      });
    return () => controller.abort();
  }, []);
  return provenanceItems(runs);
}
