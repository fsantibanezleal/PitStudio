import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import { Marked } from "./Marked";
import { SearchField, useQuery } from "./SearchField";
import { searchRows } from "./search";
import type { GlossaryEntry } from "./types";

/** FR-020-35: every glossary term with both languages, the definition of the active language and its source. */
export function GlossarySection({ entries }: { entries: GlossaryEntry[] }) {
  const { t, i18n } = useTranslation("results");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const [q] = useQuery();
  const rows = searchRows(entries, q, (e) => [e.term_en, e.term_es, e.definition_en, e.definition_es]);
  return (
    <section data-testid="glossary" aria-label={t("knowledge.nav.glossary")}>
      <SearchField />
      {rows.length === 0 ? (
        <p data-testid="no-match">{t("knowledge.noTerms")}</p>
      ) : (
        <ul className={styles.rows}>
          {rows.map((e) => (
            <li key={e.id} data-term={e.id} className={styles.card}>
              <h4>
                <span data-field="term-en">
                  <Marked text={e.term_en} query={q} />
                </span>
                {" · "}
                <span data-field="term-es">
                  <Marked text={e.term_es} query={q} />
                </span>
              </h4>
              <p data-field="definition">
                <Marked text={lang === "es" ? e.definition_es : e.definition_en} query={q} />
              </p>
              {e.citation && (
                <p className={styles.unit} data-field="source">
                  <Link to={`/knowledge/?section=bibliography#${e.citation}`}>
                    {t("knowledge.glossary.source", { key: e.citation })}
                  </Link>
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
