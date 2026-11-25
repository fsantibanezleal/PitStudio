import { SeriesChart } from "./SeriesChart";
import { useChartSeries } from "./useChartSeries";

/** The charts of a run once its list is open: only then are the chart files requested and the chart code loaded. */
export default function OpenRunCharts({ caseId, runId }: { caseId: string; runId: string }) {
  const { charts } = useChartSeries(caseId);
  return charts.filter((c) => c.runId === runId).map((c) => <SeriesChart key={c.artefact.id} doc={c.doc} />);
}
