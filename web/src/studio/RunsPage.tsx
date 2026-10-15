import { useTranslation } from "react-i18next";
import shell from "~/shell/shell.module.css";
import { caseIds, studioTools, useRunSummaries } from "./data";
import { RunsLedger } from "./RunsLedger";

/** `/studio/runs`: the ledger of published runs (FR-019-21). */
export function RunsPage() {
  const { t } = useTranslation("studio");
  const runs = useRunSummaries();
  return (
    <article className={shell.page}>
      <h1>{t("runs.title")}</h1>
      <p className={shell.lead}>{t("runs.lead")}</p>
      {runs.status === "ready" ? (
        <RunsLedger runs={runs.value} cases={caseIds} tools={studioTools.map((x) => x.id)} />
      ) : (
        <p>{t("runPage.loading")}</p>
      )}
    </article>
  );
}
