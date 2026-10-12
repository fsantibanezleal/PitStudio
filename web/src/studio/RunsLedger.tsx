import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { useHydrated } from "~/shell/useHydrated";
import { clip, utcDate } from "./format";
import { newestFirst } from "./Loop";
import styles from "./studio.module.css";
import type { RunCard } from "./types";

const MAX_FILTER_CHARS = 2000;

/** The filter value when it is one of the known ids, else null (unknown, malformed or over-long: FR-019-41). */
function known(value: string | null, ids: readonly string[]): string | null {
  if (value === null || value.length > MAX_FILTER_CHARS) return null;
  return ids.includes(value) ? value : null;
}

const unique = (values: Iterable<string>) => [...new Set(values)];

/** The ledger of published runs, newest first, filterable by `?case=` and `?tool=` (FR-019-21, FR-019-41). */
export function RunsLedger({
  runs,
  cases,
  tools,
}: {
  runs: readonly RunCard[];
  cases: readonly string[];
  tools: readonly string[];
}) {
  const { t } = useTranslation("studio");
  const hydrated = useHydrated();
  const [params] = useSearchParams();
  const published = newestFirst(runs.filter((r) => r.published !== false));

  const rawCase = hydrated ? params.get("case") : null;
  const rawTool = hydrated ? params.get("tool") : null;
  const caseFilter = known(rawCase, cases);
  const toolFilter = known(rawTool, tools);
  const ignored = (rawCase !== null && caseFilter === null) || (rawTool !== null && toolFilter === null);

  const rows = published
    .map((run) => ({
      run,
      cases: unique(run.artefacts.flatMap((a) => a.cases ?? [])),
      tools: unique(run.artefacts.map((a) => a.producer.tool)),
      classes: unique(
        run.stages.map((s) => s.determinism?.class).filter((c): c is string => typeof c === "string"),
      ),
    }))
    .filter(
      (r) =>
        (caseFilter === null || r.cases.includes(caseFilter)) &&
        (toolFilter === null || r.tools.includes(toolFilter)),
    );

  return (
    <div>
      {ignored && (
        <p data-testid="filter-note" role="status" className={styles.notice}>
          {t("runs.unknownFilter")}
        </p>
      )}
      {published.length === 0 ? (
        <p data-testid="no-runs">{t("runs.none")}</p>
      ) : (
        <table data-testid="runs-table" className={styles.table}>
          <thead>
            <tr>
              {["run", "cases", "tools", "date", "determinism", "artefacts"].map((c) => (
                <th key={c} scope="col">
                  {t(`runs.col.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ run, cases: runCases, tools: runTools, classes }) => (
              <tr key={run.run_id} data-run={run.run_id}>
                <td data-col="run">
                  <Link to={`/studio/runs/${encodeURIComponent(run.run_id)}/`}>{clip(run.run_id)}</Link>
                  {run.stale && (
                    <span className={styles.badge} data-testid="stale-badge">
                      {t("stale")}
                    </span>
                  )}
                  {run.fixture && (
                    <span className={styles.badge} data-testid="fixture-badge">
                      {t("fixture")}
                    </span>
                  )}
                </td>
                <td data-col="cases">{runCases.map(clip).join(", ")}</td>
                <td data-col="tools">{runTools.map(clip).join(", ")}</td>
                <td data-col="date">{utcDate(run.created) ?? ""}</td>
                <td data-col="determinism">{classes.map(clip).join(", ")}</td>
                <td data-col="artefacts">{run.artefacts.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
