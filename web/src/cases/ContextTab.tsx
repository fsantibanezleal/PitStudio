import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "./cases.module.css";
import { type CaseRegistry, caseEntry, type Lang, methodHref, pick, type SourceEntry } from "./types";

export interface ContextTabProps {
  caseId: string;
  registry: CaseRegistry;
  /** Entries of the data source registry; an id the case lists but the registry lacks is shown by its id alone. */
  sources: SourceEntry[];
}

/** Only an https URL becomes a link; anything else (javascript:, data:, a relative path) is shown as text. */
function httpsUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

/** The Context tab: question, sources with licences, synthetic-data labels, validity range and links (FR-018-17). */
export function ContextTab({ caseId, registry, sources }: ContextTabProps) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const entry = caseEntry(registry, caseId);
  if (!entry) return null;
  const known = new Map(sources.map((s) => [s.id, s]));

  return (
    <div>
      <section aria-labelledby="ctx-question">
        <h3 id="ctx-question">{t("context.question")}</h3>
        <p>{pick(entry.question, lang)}</p>
      </section>

      <section aria-labelledby="ctx-sources">
        <h3 id="ctx-sources">{t("context.sources")}</h3>
        {entry.sources.length === 0 ? (
          <p className={styles.unit}>{t("context.noSources")}</p>
        ) : (
          <ul className={styles.list}>
            {entry.sources.map((id) => {
              const source = known.get(id);
              const landing = source ? httpsUrl(source.landing_url) : null;
              return (
                <li key={id} data-source={id} className={styles.card}>
                  <span>
                    <code>{id}</code>
                    {source && <> · {source.title}</>}
                  </span>{" "}
                  {source ? (
                    <span>
                      {t(`context.kind.${source.kind}`)} · {t("context.licence")}: {source.spdx}
                    </span>
                  ) : (
                    <span className={styles.pending}>{t("context.unregistered")}</span>
                  )}{" "}
                  <span className={styles.chips}>
                    <Link to={`/knowledge/datasets/${encodeURIComponent(id)}/`}>{t("context.card")}</Link>
                    {landing && (
                      <a href={landing} rel="noreferrer noopener">
                        {t("context.landing")}
                      </a>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="ctx-synthetic">
        <h3 id="ctx-synthetic">{t("context.synthetic")}</h3>
        <ul className={styles.list}>
          {entry.synthetic_data.map((s) => (
            <li key={s.label.en}>
              {pick(s.label, lang)}
              {s.validation === "unvalidated" && (
                <>
                  {" "}
                  <span className={styles.synthetic}>{t("context.unvalidated")}</span>
                </>
              )}
              {s.validation === "validated-against-real" && <> · {t("context.validated")}</>}
              {s.validation === "descriptive-only" && <> · {t("context.descriptive")}</>}
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ctx-validity">
        <h3 id="ctx-validity">{t("context.validity")}</h3>
        <p>{pick(entry.validity, lang)}</p>
      </section>

      <section aria-labelledby="ctx-links">
        <h3 id="ctx-links">{t("context.links")}</h3>
        <p className={styles.chips}>
          <Link to="/theory/">{t("context.theory")}</Link>
          {entry.methods.map((m) => {
            const href = methodHref(m);
            return href ? (
              <Link key={m} to={href}>
                {m}
              </Link>
            ) : null;
          })}
        </p>
      </section>
    </div>
  );
}
