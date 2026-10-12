import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import type { ArtefactRecord, RunSummary } from "~/cases/types";

/** UTC calendar date (YYYY-MM-DD) of an ISO timestamp, or null when it does not parse. */
export function utcDate(created: string): string | null {
  const time = Date.parse(created);
  return Number.isNaN(time) ? null : new Date(time).toISOString().slice(0, 10);
}

/**
 * An artefact card (FR-018-18): lane badge, producer and run chips, the 7-hex commit, the licence class, the data
 * sources it was made from and, for a REPLAY artefact whose run is known, where and when it was precomputed.
 */
export function ArtefactCard({ artefact, run }: { artefact: ArtefactRecord; run?: RunSummary | null }) {
  const { t } = useTranslation("cases");
  const { t: tStudio } = useTranslation("studio");
  const sources = artefact.inputs.filter((input) => input.kind === "source");
  const sameRun = run && run.run_id === artefact.run_id ? run : null;
  const date = sameRun ? utcDate(sameRun.created) : null;
  const precomputed = artefact.lane === "replay" && sameRun?.gpu?.name && date;

  return (
    <article className={styles.card} data-artefact={artefact.id}>
      <div className={styles.chips}>
        <span className={styles.lane} data-lane={artefact.lane}>
          {t(`lane.${artefact.lane}`)}
        </span>
        <strong>{artefact.id}</strong>
      </div>
      <div className={styles.chips}>
        <Link to={`/studio/tools/${encodeURIComponent(artefact.producer.tool)}/`} className={styles.chip}>
          {artefact.producer.tool}
        </Link>
        <Link to={`/studio/runs/${encodeURIComponent(artefact.run_id)}/`} className={styles.chip}>
          {artefact.run_id}
        </Link>
        <span className={styles.chip}>{artefact.git_sha.slice(0, 7)}</span>
        <span className={styles.chip}>{artefact.licence_class}</span>
      </div>
      {artefact.producer.tool === "cosmos-reason-2" && (
        <p className={styles.unit}>
          <span>{tStudio("cosmos.built")}</span> <span>{tStudio("cosmos.displayOnly")}</span>
        </p>
      )}
      {artefact.attribution && <p className={styles.unit}>{artefact.attribution}</p>}
      {sources.length > 0 && (
        <p className={styles.unit}>
          {t("card.sources")}: {sources.map((s) => s.id).join(", ")}
        </p>
      )}
      {precomputed && <p>{t("card.precomputed", { gpu: sameRun?.gpu?.name, date })}</p>}
    </article>
  );
}
