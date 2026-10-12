import { useTranslation } from "react-i18next";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { VideoCard } from "~/media/VideoCard";
import { ClockControls } from "~/sim/ClockControls";
import type { SimClock } from "~/sim/clock";
import styles from "./cases.module.css";
import { replayVideosOf } from "./replayVideos";
import type { ArtefactRecord, RunSummary } from "./types";

/**
 * The Studio replay tab (FR-018-15): one artefact card for every REPLAY artefact whose `cases` array lists the case, in the order
 * given; an artefact of another case, of another lane or without a `cases` array is not listed. Nothing published is "Not yet run".
 * With a page clock, the replay videos of the case are shown above the cards, bound to that clock; the clock's controls sit in the
 * first video card, so there is one set of transport controls on the page (FR-018-22..24).
 */
export function ReplayTab({
  caseId,
  artefacts,
  runs = [],
  clock,
}: {
  caseId: string;
  artefacts: readonly ArtefactRecord[];
  runs?: readonly RunSummary[];
  clock?: SimClock;
}) {
  const { t } = useTranslation("cases");
  const own = artefacts.filter(
    (a) => a.lane === "replay" && Array.isArray(a.cases) && a.cases.includes(caseId),
  );
  const videos = clock ? replayVideosOf(artefacts, caseId) : [];
  const assets = `${import.meta.env.BASE_URL}assets/`;
  if (own.length === 0) {
    return (
      <p className={styles.panel}>
        <span className={styles.pending}>{t("notYetRun")}</span> · {t("case.replayPending")}
      </p>
    );
  }
  return (
    <>
      {clock &&
        videos.map((video, index) => (
          <VideoCard
            key={video.id}
            files={video.files}
            posterUrl={video.poster ? `${assets}${video.poster.path}` : ""}
            baseUrl={assets}
            clock={clock}
            title={`${t("video.title")}: ${video.id}`}
            sha256ByPath={video.sha256ByPath}
            bytesByPath={video.bytesByPath}
          >
            {index === 0 && <ClockControls clock={clock} />}
          </VideoCard>
        ))}
      <ul className={styles.cardList}>
        {own.map((artefact) => (
          <li key={artefact.id}>
            <ArtefactCard artefact={artefact} run={runs.find((r) => r.run_id === artefact.run_id) ?? null} />
          </li>
        ))}
      </ul>
    </>
  );
}
