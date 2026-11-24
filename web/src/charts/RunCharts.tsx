// The generic chart reader of a case page (FR-020-55): every chart-series artefact of the case's published runs, grouped by run,
// drawn by type with its axes, units and producer label. Loaded on demand (dynamic import) so that the chart code stays out of
// the initial JavaScript of the case pages (NFR-018-01, ADR-0038).
import { useTranslation } from "react-i18next";
import { usePublishedCase } from "~/cases/publishedResults";
import { SeriesChart } from "./SeriesChart";
import { type PublishedChart, useChartSeries } from "./useChartSeries";

function byRun(charts: readonly PublishedChart[]): Array<[string, PublishedChart[]]> {
  const groups = new Map<string, PublishedChart[]>();
  for (const c of charts) groups.set(c.runId, [...(groups.get(c.runId) ?? []), c]);
  return [...groups.entries()];
}

/** The charts of one published run, as the Published-results card shows them (collapsed until the visitor opens them). */
export function RunChartList({ caseId, runId }: { caseId: string; runId: string }) {
  const { t } = useTranslation("cases");
  const { charts } = useChartSeries(caseId);
  const own = charts.filter((c) => c.runId === runId);
  if (own.length === 0) return null;
  return (
    <details data-testid="run-charts" data-run-charts={runId}>
      <summary>{t("charts.runCharts", { count: own.length })}</summary>
      {own.map((c) => (
        <SeriesChart key={c.artefact.id} doc={c.doc} />
      ))}
    </details>
  );
}

/** Every chart of the case, grouped by run; nothing at all when no run carries one (the page keeps its other charts). */
export default function CaseRunCharts({ caseId }: { caseId: string }) {
  const { t } = useTranslation("cases");
  const { charts } = useChartSeries(caseId);
  const published = usePublishedCase(caseId);
  if (charts.length === 0) return null;
  return (
    <section data-testid="run-charts-section" aria-labelledby={`run-charts-${caseId}`}>
      <h2 id={`run-charts-${caseId}`}>{t("charts.runChartsTitle")}</h2>
      {byRun(charts).map(([runId, list]) => (
        <section key={runId} data-run-charts={runId}>
          <h3>{published.results.find((r) => r.runId === runId)?.title ?? runId}</h3>
          {list.map((c) => (
            <SeriesChart key={c.artefact.id} doc={c.doc} />
          ))}
        </section>
      ))}
    </section>
  );
}
