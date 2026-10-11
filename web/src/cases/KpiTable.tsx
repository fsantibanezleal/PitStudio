import { useTranslation } from "react-i18next";
import styles from "./cases.module.css";
import { type ArtefactRecord, type Kpi, type Lang, pick } from "./types";
import { unitSymbol } from "./units";

export interface KpiItem {
  kpi: Kpi;
  /** The value read from the published artefact; null when no artefact has been published. */
  value: number | null;
  /** The web-manifest record the value comes from; without it a number has no provenance and is not shown. */
  artefact: ArtefactRecord | null;
}

export function formatValue(value: number, lang: Lang): string {
  return new Intl.NumberFormat(lang, { maximumSignificantDigits: 4, useGrouping: false }).format(value);
}

/** One row per KPI: the value with its lane badge and provenance chip, or "Not yet run" (FR-018-05). */
export function KpiTable({ items }: { items: KpiItem[] }) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";

  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">{t("kpi.name")}</th>
          <th scope="col">{t("kpi.value")}</th>
          <th scope="col">{t("kpi.provenance")}</th>
        </tr>
      </thead>
      <tbody>
        {items.map(({ kpi, value, artefact }) => {
          const published = artefact !== null && typeof value === "number" && Number.isFinite(value);
          const unit = unitSymbol(kpi.unit);
          return (
            <tr key={kpi.id} data-kpi={kpi.id}>
              <th scope="row">{pick(kpi.name, lang)}</th>
              <td>
                {published ? (
                  <span className={styles.value}>{formatValue(value, lang)}</span>
                ) : (
                  <span className={styles.pending}>{t("notYetRun")}</span>
                )}
                {unit && <span className={styles.unit}> {unit}</span>}
              </td>
              <td>
                {published && (
                  <>
                    <span className={styles.lane} data-lane={artefact.lane}>
                      {t(`lane.${artefact.lane}`)}
                    </span>{" "}
                    <span className={styles.chip}>
                      {artefact.producer.tool} · {artefact.run_id} · {artefact.git_sha.slice(0, 7)}
                    </span>
                  </>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
