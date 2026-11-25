// The collapsed list of the charts of one published run, as the Published-results card shows it (FR-020-55). It holds nothing but the
// disclosure and the count the manifest gives; the chart files and the chart code are requested when the visitor opens the list
// (NFR-018-01, NFR-018-02).
import { lazy, Suspense, useState } from "react";
import { useTranslation } from "react-i18next";
import { chartArtefacts, useWebManifest } from "~/cases/manifest";

const OpenRunCharts = lazy(() => import("./OpenRunCharts"));

export function RunChartList({ caseId, runId }: { caseId: string; runId: string }) {
  const { t } = useTranslation("cases");
  const manifest = useWebManifest();
  const [opened, setOpened] = useState(false);
  const count = chartArtefacts(manifest.artefacts, caseId).filter((a) => a.run_id === runId).length;
  if (count === 0) return null;
  return (
    <details
      data-testid="run-charts"
      data-run-charts={runId}
      onToggle={(event) => {
        if ((event.currentTarget as HTMLDetailsElement).open) setOpened(true);
      }}
    >
      <summary>{t("charts.runCharts", { count })}</summary>
      {opened && (
        <Suspense fallback={null}>
          <OpenRunCharts caseId={caseId} runId={runId} />
        </Suspense>
      )}
    </details>
  );
}
