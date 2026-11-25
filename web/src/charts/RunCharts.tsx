// The generic chart reader of a case page (FR-020-55): every chart-series artefact of the case's published runs, grouped by run,
// drawn by type with its axes, units and producer label. Loaded on demand (dynamic import) so that the chart code stays out of
// the initial JavaScript of the case pages (NFR-018-01, ADR-0038).
import { useTranslation } from "react-i18next";
import { type PublishedResult, usePublishedCase } from "~/cases/publishedResults";
import { i18n } from "~/shell/i18n";
import { SeriesChart } from "./SeriesChart";
import { type PublishedChart, useChartSeries } from "./useChartSeries";

function byRun(charts: readonly PublishedChart[]): Array<[string, PublishedChart[]]> {
  const groups = new Map<string, PublishedChart[]>();
  for (const c of charts) groups.set(c.runId, [...(groups.get(c.runId) ?? []), c]);
  return [...groups.entries()];
}

export { RunChartList } from "./RunChartList";

/**
 * The heading of a run group: the title of the run's published result; without one, the method of the run's charts with its tool and
 * the UTC date of the run (read from the run id), never the run id itself.
 */
export function runHeading(
  runId: string,
  charts: readonly PublishedChart[],
  results: readonly Pick<PublishedResult, "runId" | "title">[],
  lang: "en" | "es",
): string {
  const title = results.find((r) => r.runId === runId)?.title;
  if (title) return title;
  const producer = charts.find((c) => c.runId === runId)?.doc.producer;
  const m = /^(\d{4})(\d{2})(\d{2})T/.exec(runId);
  const date = m ? `${m[1]}-${m[2]}-${m[3]}` : runId;
  return i18n.getFixedT(lang, "cases")("charts.runHeading", {
    method: producer?.method ?? "",
    tool: producer?.tool ?? "",
    date,
    interpolation: { escapeValue: false },
  });
}

/** Every chart of the case, grouped by run; nothing at all when no run carries one (the page keeps its other charts). */
export default function CaseRunCharts({ caseId }: { caseId: string }) {
  const { t, i18n: active } = useTranslation("cases");
  const lang = active.resolvedLanguage === "es" ? "es" : "en";
  const { charts } = useChartSeries(caseId);
  const published = usePublishedCase(caseId);
  if (charts.length === 0) return null;
  return (
    <section data-testid="run-charts-section" aria-labelledby={`run-charts-${caseId}`}>
      <h2 id={`run-charts-${caseId}`}>{t("charts.runChartsTitle")}</h2>
      {byRun(charts).map(([runId, list]) => (
        <section key={runId} data-run-charts={runId}>
          <h3>{runHeading(runId, charts, published.results, lang)}</h3>
          {list.map((c) => (
            <SeriesChart key={c.artefact.id} doc={c.doc} />
          ))}
        </section>
      ))}
    </section>
  );
}
