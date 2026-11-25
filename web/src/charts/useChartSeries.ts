// The chart series a case's published runs carry: the artefacts of kind `chart-series` of the web manifest that apply to the
// case, each fetched once and read through the contract (FR-020-55). A file that is missing, not JSON or not a valid chart
// series is nothing published; a chart of another case is not drawn on this one.
import { useEffect, useState } from "react";
import { chartArtefacts, useWebManifest } from "~/cases/manifest";
import type { ArtefactRecord } from "~/cases/types";
import { type ChartDoc, readChartSeries } from "./chartSeries";

export interface PublishedChart {
  runId: string;
  artefact: ArtefactRecord;
  doc: ChartDoc;
}

export interface CaseCharts {
  status: "loading" | "ready";
  charts: PublishedChart[];
}

// One fetch per file for the page's life. The cache belongs to the `fetch` function that filled it, so a replaced `fetch` (a test
// double, a service-worker swap) never reads another implementation's answers.
const caches = new WeakMap<typeof fetch, Map<string, Promise<unknown>>>();

function fetchJson(path: string): Promise<unknown> {
  const url = `${import.meta.env.BASE_URL}${path}`;
  const get = globalThis.fetch;
  let cache = caches.get(get);
  if (!cache) {
    cache = new Map();
    caches.set(get, cache);
  }
  let hit = cache.get(url);
  if (!hit) {
    hit = get(url)
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null);
    cache.set(url, hit);
  }
  return hit;
}

export { chartArtefacts };

export function useChartSeries(caseId: string): CaseCharts {
  const manifest = useWebManifest();
  const [state, setState] = useState<CaseCharts>({ status: "loading", charts: [] });
  const own = manifest.status === "ready" ? chartArtefacts(manifest.artefacts, caseId) : null;
  const key = own === null ? null : own.map((a) => a.id).join("|");
  // biome-ignore lint/correctness/useExhaustiveDependencies: `key` stands for the artefact list
  useEffect(() => {
    if (own === null) return;
    let live = true;
    void Promise.all(
      own.map(async (artefact) => {
        const doc = readChartSeries(await fetchJson(artefact.path));
        return doc && doc.case === caseId ? { runId: artefact.run_id, artefact, doc } : null;
      }),
    ).then((list) => {
      if (live) setState({ status: "ready", charts: list.filter((c): c is PublishedChart => c !== null) });
    });
    return () => {
      live = false;
    };
  }, [caseId, key]);
  return state;
}
