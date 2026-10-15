import { useTranslation } from "react-i18next";
import { clip } from "../format";
import { SafeText } from "../SafeText";
import styles from "../studio.module.css";
import type { RunCard, StageRecord, StudioTool } from "../types";

/** A stage failed or was rejected when its status is failed or any attempt ended with an error class. */
function isFailedVariant(stage: StageRecord): boolean {
  return stage.status === "failed" || (stage.attempts ?? []).some((a) => a.error_class);
}

/** Block 6: the recorded notice of the registry and every failed or rejected variant of the tool's published runs (FR-019-17). */
export function LimitsBlock({ tool, runs }: { tool: StudioTool; runs: RunCard[] }) {
  const { t } = useTranslation("studio");
  const failures = runs.flatMap((run) =>
    run.stages.filter((s) => s.tool === tool.id && isFailedVariant(s)).map((stage) => ({ run, stage })),
  );
  return (
    <section data-block="limits" className={styles.block} aria-labelledby="b-limits">
      <h2 id="b-limits">{t("blocks.limits.title")}</h2>
      <ul className={styles.plain}>
        {tool.notice && (
          <li data-testid="limit">
            <SafeText value={tool.notice} />
          </li>
        )}
        {failures.map(({ run, stage }) => (
          <li key={`${run.run_id}/${stage.key.id}/${stage.key.variant ?? ""}`} data-testid="failed-variant">
            <strong>{clip(stage.key.id)}</strong>
            {stage.key.variant ? ` (${clip(stage.key.variant)})` : ""} · {t("blocks.limits.run")}{" "}
            {clip(run.run_id)}
            {stage.status === "failed" ? ` · ${t("blocks.limits.failed")}` : ""}
            {stage.error_class ? ` · ${clip(stage.error_class)}` : ""}
            {typeof stage.exit_code === "number" && stage.exit_code !== 0
              ? ` · ${t("blocks.limits.exit", { code: stage.exit_code })}`
              : ""}{" "}
            <ul className={styles.plain}>
              {(stage.attempts ?? []).map((a, i) => (
                <li key={a.n ?? i}>
                  {t("blocks.limits.attempt", { n: a.n ?? i + 1 })}:{" "}
                  {a.error_class ? clip(a.error_class) : t("blocks.limits.ok")}
                  {typeof a.duration_s === "number" && Number.isFinite(a.duration_s)
                    ? ` · ${a.duration_s} s`
                    : ""}
                </li>
              ))}
            </ul>
            {typeof stage.log_tail === "string" && stage.log_tail !== "" && (
              <p>
                <SafeText value={stage.log_tail} />
              </p>
            )}
          </li>
        ))}
      </ul>
      {!tool.notice && failures.length === 0 && <p>{t("blocks.limits.none")}</p>}
    </section>
  );
}
