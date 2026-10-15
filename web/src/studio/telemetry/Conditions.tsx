import { useTranslation } from "react-i18next";
import { clip, num, percent, THROTTLE_REASONS } from "../format";
import styles from "../studio.module.css";
import type { RunCard, TelemetrySummary } from "../types";

/**
 * The conditions of a published timing (FR-019-32): GPU model, driver, enforced power limit, the share of time in each
 * clocks-event (throttle) state, and the statement that the numbers come from our hardware and are not a benchmark.
 * A value the run card does not hold reads "not available on this GPU"; it is never shown as 0.
 */
export function ConditionsNote({ run, stage }: { run: RunCard; stage: string }) {
  const { t } = useTranslation("studio");
  const na = t("gpu.notAvailable");
  const record = run.stages.find((s) => s.key.id === stage);
  const tele: TelemetrySummary | null =
    record && typeof record.telemetry === "object" ? record.telemetry : null;
  const fractions = tele?.clocks_event_frac;
  const limit = num(run.gpu?.power_limit_enforced_w);
  return (
    <div data-testid="conditions" className={styles.conditions}>
      <p>
        {t("gpu.conditions.gpu")}: {run.gpu ? clip(run.gpu.name) : na} · {t("gpu.conditions.driver")}:{" "}
        {run.gpu ? clip(run.gpu.driver) : na} · {t("gpu.conditions.limit")}:{" "}
        {limit === null ? na : `${limit} W`}
      </p>
      <ul className={styles.plain}>
        {THROTTLE_REASONS.map((reason) => {
          const p = fractions && typeof fractions === "object" ? percent(fractions[reason]) : null;
          return (
            <li key={reason}>
              {t(`throttle.${reason}`)}: {p === null ? na : `${p} %`}
            </li>
          );
        })}
      </ul>
      <p>{t("gpu.conditions.notBenchmark")}</p>
    </div>
  );
}
