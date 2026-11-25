import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { clip } from "../format";
import styles from "../studio.module.css";
import type { RunCard } from "../types";

/**
 * One card per stage of the run card marked `performance: local-only` (Isaac Sim, Kit, Replicator, ovrtx, TensorRT for RTX):
 * the licence note and links to the stage's outputs. No number of the stage is printed, even when the card holds some
 * (FR-019-30, FR-000-08).
 */
export function LocalOnlyCards({ run }: { run: RunCard }) {
  const { t } = useTranslation("studio");
  const stages = run.stages.filter((s) => s.performance === "local-only");
  return (
    <>
      {stages.map((stage, i) => {
        const outputs = run.artefacts.filter(
          (a) =>
            a.producer.stage.id === stage.key.id &&
            (stage.key.variant === undefined || a.producer.stage.variant === stage.key.variant),
        );
        return (
          <article
            // biome-ignore lint/suspicious/noArrayIndexKey: a stage is identified by its place on the card
            key={i}
            data-testid="local-only-stage"
            data-stage={stage.key.id}
            className={styles.block}
          >
            <h3>
              {clip(stage.key.id)} · {clip(stage.tool)}
            </h3>
            <p>{t("gpu.localOnly")}</p>
            {outputs.length > 0 && (
              <ul className={styles.plain}>
                {outputs.map((a) => (
                  <li key={a.id}>
                    <Link
                      data-testid="output-link"
                      to={`/studio/runs/${encodeURIComponent(run.run_id)}/#${encodeURIComponent(a.id)}`}
                    >
                      {clip(a.id)}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
    </>
  );
}
