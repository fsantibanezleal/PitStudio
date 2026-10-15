import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./cases.module.css";
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
}: {
  caseId: string;
  recipe: RecipeSummary | null;
  runId: string | null;
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
      ) : (
        <p className={styles.pending}>{t("reproduce.planned")}</p>
      )}
    </section>
  );
}
