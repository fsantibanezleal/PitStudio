// FR-018-74: which published value feeds which KPI of a case. A headline entry of a published summary names its KPI in the
// explicit `kpi` field; nothing is mapped by name, and a unit that differs from the KPI unit feeds nothing. A pure module.
import type { KpiItem } from "./KpiTable";
import type { PublishedResult } from "./publishedResults";
import { type CaseEntry, headlineKpis } from "./types";

/** One item per headline KPI of the case, plus any other KPI a published value feeds; the newest run wins, a failed evaluation feeds nothing. */
export function kpiItems(entry: CaseEntry, results: readonly PublishedResult[]): KpiItem[] {
  const byId = new Map(entry.kpis.map((k) => [k.id, k]));
  const fed = new Map<string, KpiItem>();
  const working = results.filter((r) => r.verdict !== "failed" && r.artefact !== null);
  for (const r of [...working].sort((a, b) => a.runId.localeCompare(b.runId))) {
    for (const h of r.headline) {
      const kpi = h.kpi !== undefined ? byId.get(h.kpi) : undefined;
      if (!kpi || kpi.unit !== h.unit) continue;
      fed.set(kpi.id, {
        kpi,
        value: h.value,
        artefact: r.artefact,
        runLabel: r.label,
        partial: r.partial,
      });
    }
  }
  const shown = new Set(headlineKpis(entry).map((k) => k.id));
  return entry.kpis
    .filter((k) => shown.has(k.id) || fed.has(k.id))
    .map((kpi) => fed.get(kpi.id) ?? { kpi, value: null, artefact: null });
}
