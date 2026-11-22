import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "./cases.module.css";
import type { ImportedRun } from "./importedRuns";
import { isCaseId } from "./types";

export interface RecipeSummary {
  stages: Array<{ resources: { gpu: "exclusive" | "nvenc" | "none" } }>;
}

/** Run id pattern of data-model 001 section 1.3. Anything else never reaches a command. */
const RUN_ID = /^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$/;
const PROFILE = "laptop-rtx5000ada";

/** Repository path of a case recipe, with the id in lower case (FR-018-19). */
export function recipePath(caseId: string): string {
  return `studio/recipes/cases/${caseId.toLowerCase()}.yaml`;
}

/** The three commands of FR-018-19 for a case, with the real run id only when it is one. */
export function reproduceCommands(caseId: string, runId: string | null): string[] {
  const recipe = recipePath(caseId);
  const run = runId !== null && RUN_ID.test(runId) ? runId : "<run-id>";
  return [
    `uv run studio plan ${recipe} --profile ${PROFILE}`,
    `uv run studio run ${recipe} --profile ${PROFILE}`,
    `uv run studio publish ${run}`,
  ];
}

/** The "Reproduce this" block that ends a case page (FR-018-19, FR-018-20). */
export function ReproduceBlock({
  caseId,
  recipe,
  runId,
  runs = [],
}: {
  caseId: string;
  recipe: RecipeSummary | null;
  runId: string | null;
  /** Published runs of the case that `studio import-run` recorded from a queue job (FR-018-77). */
  runs?: readonly ImportedRun[];
}) {
  const { t } = useTranslation("cases");
  const [copied, setCopied] = useState(false);
  const known = isCaseId(caseId);

  const gpus = recipe?.stages.map((s) => s.resources.gpu) ?? [];
  const note = gpus.includes("exclusive")
    ? t("reproduce.needsGpu")
    : gpus.includes("nvenc")
      ? t("reproduce.needsNvenc")
      : t("reproduce.noGpu");

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className={styles.reproduce} aria-labelledby="reproduce-title">
      <h2 id="reproduce-title">{t("reproduce.title")}</h2>
      {recipe && known ? (
        <>
          <p>
            {t("reproduce.recipe")}: <code>{recipePath(caseId)}</code>
          </p>
          {reproduceCommands(caseId, runId).map((line) => (
            <code key={line} data-command className={styles.command}>
              {line}
            </code>
          ))}
          <p>{note}</p>
          <p>
            <button
              type="button"
              className={styles.button}
              onClick={() => void copy(reproduceCommands(caseId, runId).join("\n"))}
            >
              {t("reproduce.copy")}
            </button>{" "}
            <span role="status" className={styles.unit}>
              {copied ? t("reproduce.copied") : ""}
            </span>
          </p>
        </>
      ) : runs.length === 0 ? (
        <p className={styles.pending}>{t("reproduce.planned")}</p>
      ) : (
        <p>{t("reproduce.noRecipe")}</p>
      )}
      {runs.length > 0 && <PublishedRuns runs={runs} />}
    </section>
  );
}

const importCommand = (job: string): string => `uv run studio import-run ${job} --from <job output folder>`;

/** What reproduces each published imported run: its import command and `studio publish`, or why it cannot be reproduced yet. */
function PublishedRuns({ runs }: { runs: readonly ImportedRun[] }) {
  const { t } = useTranslation("cases");
  return (
    <div data-testid="published-runs">
      <h3>{t("reproduce.published")}</h3>
      {runs.map((run) => (
        <div key={run.runId} data-run={run.runId}>
          <p>
            <Link to={`/studio/runs/${run.runId}/`}>{run.runId}</Link> · {run.label}
          </p>
          {run.verdict === "failed" && <p className={styles.failed}>{t("results.failed")}</p>}
          {run.partialReasons.length > 0 && (
            <p className={styles.unit}>
              {t("results.partial")} {run.partialReasons.join("; ")}
            </p>
          )}
          {run.job ? (
            <>
              {[importCommand(run.job), `uv run studio publish ${run.runId}`].map((line) => (
                <code key={line} data-command className={styles.command}>
                  {line}
                </code>
              ))}
            </>
          ) : (
            <p className={styles.unit}>{t("reproduce.cannotYet")}</p>
          )}
        </div>
      ))}
    </div>
  );
}
