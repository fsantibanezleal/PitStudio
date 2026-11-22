import { useTranslation } from "react-i18next";
import styles from "./surrogates.module.css";

/**
 * The A3 calibration replay view (FR-011-31), REPLAY at every tier. The calibration study (50 coverage trials per arm on the GPU) has
 * not been run, so no aggregate document is published and the view shows the declared state "Not yet run" with its REPLAY badge; it
 * never shows a curve, a path, a coverage or a profile that was not produced by that study.
 */
export function CalibrationReplay() {
  const { t } = useTranslation("surrogates");
  return (
    <section
      className={styles.scene}
      aria-label={t("calibration.region")}
      data-testid="calibration-replay"
      data-state="not-published"
    >
      <span className={styles.badge} data-lane="replay">
        {t("lane.replay")}
      </span>
      <p className={styles.note} role="status">
        {t("calibration.notPublished")}
      </p>
    </section>
  );
}
