import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "./cases.module.css";
import {
  CATEGORY_IDS,
  type CaseId,
  type CaseRegistry,
  caseEntry,
  isCaseId,
  type Lang,
  orderedCaseIds,
  pick,
} from "./types";

export interface CaseRailProps {
  registry: CaseRegistry;
  /** A canonical case id; anything else selects nothing. */
  selected?: string | null;
  onSelect?: (id: CaseId) => void;
}

/** The 12 cases in 5 labelled groups (A to E), in canonical order whatever the key order of the registry (FR-018-02). */
export function CaseRail({ registry, selected, onSelect }: CaseRailProps) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const ids = orderedCaseIds(registry);
  const current = isCaseId(selected) ? selected : null;

  return (
    <div className={styles.rail}>
      {CATEGORY_IDS.map((letter) => {
        const members = ids.filter((id) => caseEntry(registry, id)?.category === letter);
        const title = Object.hasOwn(registry.categories, letter)
          ? pick(registry.categories[letter]?.title, lang)
          : "";
        const labelId = `rail-group-${letter}`;
        return (
          <fieldset key={letter} aria-labelledby={labelId} className={styles.railGroup}>
            <h3 id={labelId} className={styles.railGroupTitle}>
              {letter} · {title}
            </h3>
            <ul className={styles.railList}>
              {members.map((id) => (
                <li key={id} data-case-id={id} className={styles.railItem}>
                  <button
                    type="button"
                    className={styles.railSelect}
                    aria-pressed={current === id}
                    onClick={() => onSelect?.(id)}
                  >
                    <span className={styles.railId}>{id}</span> {pick(caseEntry(registry, id)?.title, lang)}
                  </button>
                  <Link to={`/cases/${id}/`} className={styles.railOpen} aria-label={t("rail.open", { id })}>
                    {t("rail.page")}
                  </Link>
                </li>
              ))}
            </ul>
          </fieldset>
        );
      })}
    </div>
  );
}
