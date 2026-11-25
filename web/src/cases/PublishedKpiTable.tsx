import { useMemo } from "react";
import { KpiTable } from "./KpiTable";
import { kpiItems } from "./kpiValues";
import { usePublishedCase } from "./publishedResults";
import { type CaseEntry, headlineKpis } from "./types";

/** The KPI table of a case: each headline KPI with the published value that names it, else "Not yet run" (FR-018-74). */
export function PublishedKpiTable({ caseId, entry }: { caseId: string; entry: CaseEntry }) {
  const published = usePublishedCase(caseId);
  const items = useMemo(
    () =>
      published.status === "ready"
        ? kpiItems(entry, published.results)
        : headlineKpis(entry).map((kpi) => ({ kpi, value: null, artefact: null })),
    [entry, published],
  );
  return <KpiTable items={items} />;
}
