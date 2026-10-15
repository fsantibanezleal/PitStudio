import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { clip } from "./format";
import styles from "./studio.module.css";
import type { RunCard } from "./types";

/** The physical-AI loop and the stages that realise each step (spec 019 section 7.2). */
export const LOOP_STEPS = [
  { id: "scene", stages: ["st40_compose"] },
  { id: "sensors", stages: ["st53_sensors", "st55_sdg"] },
  { id: "labels", stages: ["st55_sdg"] },
  { id: "training", stages: ["s30_train", "st60_il_train"] },
  { id: "validation", stages: ["s50_evaluate"] },
  { id: "acceleration", stages: ["s62_accel"] },
  { id: "encoding", stages: ["st56_encode"] },
  { id: "web", stages: ["s60_export"] },
] as const;

/** Newest first; runs created at the same instant are ordered by run id, descending, so the order is stable. */
export function newestFirst<T extends { run_id: string; created: string }>(runs: readonly T[]): T[] {
  return [...runs].sort((a, b) => {
    const ta = Date.parse(a.created);
    const tb = Date.parse(b.created);
    if (ta !== tb && !Number.isNaN(ta) && !Number.isNaN(tb)) return tb - ta;
    return a.run_id < b.run_id ? 1 : a.run_id > b.run_id ? -1 : 0;
  });
}

/** The loop below the map: each step links to the published runs that have a succeeded stage realising it (FR-019-07). */
export function Loop({ runs }: { runs: readonly RunCard[] }) {
  const { t } = useTranslation("studio");
  const published = newestFirst(runs.filter((r) => r.published !== false));
  return (
    <ol data-testid="loop" aria-label={t("loop.label")} className={styles.loop}>
      {LOOP_STEPS.map((step) => {
        const hits = published.filter((r) =>
          r.stages.some(
            (s) => s.status === "succeeded" && (step.stages as readonly string[]).includes(s.key.id),
          ),
        );
        return (
          <li key={step.id} data-step={step.id} className={styles.loopStep}>
            <strong>{t(`loop.${step.id}`)}</strong>{" "}
            {hits.length === 0 ? (
              <span>{t("notYetRun")}</span>
            ) : (
              hits.map((r) => (
                <Link
                  key={r.run_id}
                  to={`/studio/runs/${encodeURIComponent(r.run_id)}/`}
                  className={styles.chip}
                >
                  {clip(r.run_id)}
                </Link>
              ))
            )}
          </li>
        );
      })}
    </ol>
  );
}
