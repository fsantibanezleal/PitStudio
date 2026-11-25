import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import { pick } from "~/cases/types";
import { type MethodEntry, methodRegistry } from "~/methods/registry";
import type { PublishedBundle } from "./bundles";
import { criterionStatus, MODEL_ROWS } from "./criteria";

/**
 * The 13 model rows of plan section 7 with their pre-registered criterion and the status computed from the published
 * bundles (FR-020-24, SC-020-02). The criterion text is the one recorded in the method registry for the row's requirement;
 * a requirement no registry entry records is shown with the text transcribed from its owning spec (locale `criteria.fallback`).
 */
export function CriteriaTable({
  bundles,
  methods = methodRegistry,
}: {
  bundles: ReadonlyArray<Pick<PublishedBundle, "criteria">>;
  methods?: readonly MethodEntry[];
}) {
  const { t, i18n } = useTranslation("results");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  return (
    <section data-testid="criteria" aria-label={t("criteria.title")}>
      <h2>{t("criteria.title")}</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">{t("criteria.model")}</th>
              <th scope="col">{t("criteria.criterion")}</th>
              <th scope="col">{t("criteria.status")}</th>
            </tr>
          </thead>
          <tbody>
            {MODEL_ROWS.map((row) => {
              const recorded = row.methods
                .map((id) => methods.find((m) => m.id === id)?.criterion)
                .filter((c): c is NonNullable<MethodEntry["criterion"]> => !!c)
                .filter((c) => row.requirements.includes(c.requirement));
              const text =
                recorded.length > 0
                  ? recorded.map((c) => `${pick(c.text, lang)} (${c.requirement})`).join("; ")
                  : t(`criteria.fallback.${row.id}`);
              const status = criterionStatus(row.requirements, bundles);
              return (
                <tr key={row.id} data-model-row={row.id}>
                  <th scope="row">{t(`criteria.rows.${row.id}`)}</th>
                  <td data-testid="criterion">{text}</td>
                  <td data-testid="status" data-status={status}>
                    {status === "not-yet-run" ? t("pending.status") : t(`criteria.${status}`)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
