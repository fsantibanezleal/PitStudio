import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import { CASE_IDS, pick } from "~/cases/types";
import { unitSymbol } from "~/cases/units";
import { type MethodEntry, type MethodStatus, REPO_URL } from "./registry";
import { statusText } from "./status";

/** The gate values of one lane measurement (DC-018-06) the page reports. */
export interface LaneMeasurement {
  interaction_ms?: number | null;
  run_ms_t2?: number | null;
  max_asset_bytes?: number | null;
  measured?: { tier: string; date: string; browser: string } | null;
}

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);
const safeDocs = (p: string) => (/^docs\/[A-Za-z0-9_./-]+\.md$/.test(p) && !p.includes("..") ? p : "");

/** FR-020-18: what the method computes, its design, its recorded criterion, its lane, Simulate links, docs and status. */
export function MethodPage({
  method,
  measurement,
  status,
}: {
  method: MethodEntry;
  measurement?: LaneMeasurement | null;
  status?: MethodStatus;
}) {
  const { t, i18n } = useTranslation("results");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const m = method;
  const live = m.lanes.includes("live");
  const caseIds = m.cases.filter((c) => (CASE_IDS as readonly string[]).includes(c));
  const gate =
    measurement?.measured &&
    finite(measurement.interaction_ms) &&
    finite(measurement.run_ms_t2) &&
    finite(measurement.max_asset_bytes)
      ? { ...measurement, ...measurement.measured }
      : undefined;
  const docs = safeDocs(m.docs_page);
  const fmt = (n: number) => new Intl.NumberFormat(lang, { useGrouping: true }).format(n);

  return (
    <article className={styles.card}>
      <h1>{pick(m.name, lang)}</h1>
      <section>
        <h2>{t("methodsPage.computes")}</h2>
        <p data-testid="computes">{m.implementation}</p>
      </section>
      {m.comparison && (
        <section data-testid="design">
          <h2>{t("methodsPage.design")}</h2>
          <p>{t("methodsPage.baseline", { baseline: pick(m.comparison.baseline, lang) })}</p>
          <p>
            {t("methodsPage.metric", {
              metric: pick(m.comparison.metric.name, lang),
              unit: unitSymbol(m.comparison.metric.unit),
              orientation: t(`orientation.${m.comparison.metric.orientation}`, {
                defaultValue: m.comparison.metric.orientation,
              }),
            })}
          </p>
          <p>
            {t("methodsPage.pairing", { unit: pick(m.comparison.pairing_unit, lang), n: m.comparison.n })}
          </p>
        </section>
      )}
      {m.criterion && (
        <section data-testid="criterion">
          <h2>{t("methodsPage.criterion")}</h2>
          <p>{pick(m.criterion.text, lang)}</p>
          <p className={styles.unit}>
            {t("methodsPage.criterionRef", { requirement: m.criterion.requirement, spec: m.criterion.spec })}
          </p>
        </section>
      )}
      <section data-testid="lane">
        <h2>{t("methodsPage.lane")}</h2>
        <p>{t("methodsPage.laneList", { lanes: m.lanes.join(", ") })}</p>
        <p>
          {gate
            ? t("methodsPage.measured", {
                interaction: fmt(gate.interaction_ms as number),
                run: fmt(gate.run_ms_t2 as number),
                bytes: fmt(gate.max_asset_bytes as number),
                tier: gate.tier,
                date: gate.date,
                browser: gate.browser,
              })
            : t("methodsPage.estimate")}
        </p>
      </section>
      <section data-testid="simulate-links">
        {live && caseIds.length > 0 && (
          <>
            <p>{t("methodsPage.simulate")}</p>
            <ul>
              {caseIds.map((id) => (
                <li key={id}>
                  <Link to={`/cases/${id}/?tab=simulate`}>{id}</Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <p data-testid="docs-link">
        {t("methodsPage.docs")}:{" "}
        {docs ? (
          <a href={`${REPO_URL}/blob/main/${docs}`} rel="noreferrer">
            {docs}
          </a>
        ) : null}
      </p>
      <p data-testid="status">
        {t("methodsPage.status")}: {statusText(t, status)}
      </p>
    </article>
  );
}
