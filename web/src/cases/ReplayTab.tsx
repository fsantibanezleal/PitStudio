import { useTranslation } from "react-i18next";
import { ArtefactCard } from "~/cards/ArtefactCard";
import styles from "./cases.module.css";
import type { ArtefactRecord, RunSummary } from "./types";

/**
 * The Studio replay tab (FR-018-15): one artefact card for every REPLAY artefact whose `cases` array lists the case, in the order
 * given; an artefact of another case, of another lane or without a `cases` array is not listed. Nothing published is "Not yet run".
 */
export function ReplayTab({
  caseId,
  artefacts,
  runs = [],
}: {
  caseId: string;
  artefacts: readonly ArtefactRecord[];
  runs?: readonly RunSummary[];
}) {
  const { t } = useTranslation("cases");
  const own = artefacts.filter(
    (a) => a.lane === "replay" && Array.isArray(a.cases) && a.cases.includes(caseId),
  );
  if (own.length === 0) {
    return (
      <p className={styles.panel}>
        <span className={styles.pending}>{t("notYetRun")}</span> · {t("case.replayPending")}
      </p>
    );
  }
  return (
    <ul className={styles.cardList}>
      {own.map((artefact) => (
        <li key={artefact.id}>
          <ArtefactCard artefact={artefact} run={runs.find((r) => r.run_id === artefact.run_id) ?? null} />
        </li>
      ))}
    </ul>
  );
}
