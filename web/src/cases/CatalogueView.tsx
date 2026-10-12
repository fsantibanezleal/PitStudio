import { useTranslation } from "react-i18next";
import styles from "./cases.module.css";
import {
  type CaseId,
  type CaseRegistry,
  caseEntry,
  type Lang,
  orderedCaseIds,
  pick,
  type ToolEntry,
} from "./types";
import { unitSymbol } from "./units";

/** The methods of the method ladder, M1 to M23 (docs/cases/coverage-matrix.md). */
export const METHOD_IDS = Array.from({ length: 23 }, (_, i) => `M${i + 1}`);

export interface CatalogueViewProps {
  registry: CaseRegistry;
  /** Entries of the tool registry; only studio tools that at least one case lists get a row. */
  tools: ToolEntry[];
}

function Mark({ symbol, label }: { symbol: string; label: string }) {
  return (
    <>
      <span aria-hidden="true">{symbol}</span>
      <span className={styles.srOnly}>{label}</span>
    </>
  );
}

/** The catalogue, the coverage matrix and the tool matrix, all generated from the registry (FR-018-09). */
export function CatalogueView({ registry, tools }: CatalogueViewProps) {
  const { t, i18n } = useTranslation("cases");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const ids = orderedCaseIds(registry);
  const entries = ids.map((id) => [id, caseEntry(registry, id)] as const);

  const roleOf = (id: CaseId, tool: string): "named" | "supporting" | "none" => {
    const roles = caseEntry(registry, id)?.tools ?? {};
    return Object.hasOwn(roles, tool) ? (roles[tool] ?? "none") : "none";
  };
  const listed = tools.filter(
    (tool) => tool.category === "studio-tool" && ids.some((id) => roleOf(id, tool.id) !== "none"),
  );

  return (
    <div>
      <section aria-labelledby="catalogue-title">
        <h2 id="catalogue-title">{t("catalogue.title")}</h2>
        <div className={styles.tableWrap}>
          <table className={styles.table} data-table="catalogue">
            <caption className={styles.srOnly}>{t("catalogue.title")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("catalogue.case")}</th>
                <th scope="col">{t("catalogue.name")}</th>
                <th scope="col">{t("catalogue.category")}</th>
                <th scope="col">{t("catalogue.kpis")}</th>
                <th scope="col">{t("catalogue.real")}</th>
                <th scope="col">{t("catalogue.synthetic")}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([id, entry]) => {
                if (!entry) return null;
                const category = Object.hasOwn(registry.categories, entry.category)
                  ? pick(registry.categories[entry.category]?.title, lang)
                  : "";
                return (
                  <tr key={id} data-case-id={id}>
                    <th scope="row">{id}</th>
                    <td>{pick(entry.title, lang)}</td>
                    <td>
                      {entry.category} · {category}
                    </td>
                    <td>
                      <ul className={styles.list}>
                        {entry.kpis.map((kpi) => (
                          <li key={kpi.id}>
                            {pick(kpi.name, lang)}
                            {unitSymbol(kpi.unit) && (
                              <span className={styles.unit}> ({unitSymbol(kpi.unit)})</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td>{entry.sources.length > 0 ? entry.sources.join(", ") : t("catalogue.none")}</td>
                    <td>
                      <ul className={styles.list}>
                        {entry.synthetic_data.map((s) => (
                          <li key={s.label.en}>{pick(s.label, lang)}</li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="coverage-title">
        <h2 id="coverage-title">{t("coverage.title")}</h2>
        <p className={styles.unit}>{t("coverage.legend")}</p>
        <div className={styles.tableWrap}>
          <table className={styles.table} data-table="coverage">
            <caption className={styles.srOnly}>{t("coverage.title")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("coverage.method")}</th>
                {ids.map((id) => (
                  <th key={id} scope="col" className={styles.matrixCell}>
                    {id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METHOD_IDS.map((method) => (
                <tr key={method} data-method={method}>
                  <th scope="row">{method}</th>
                  {ids.map((id) => {
                    const marked = caseEntry(registry, id)?.methods.includes(method) ?? false;
                    return (
                      <td key={id} data-case={id} data-marked={String(marked)} className={styles.matrixCell}>
                        {marked && <Mark symbol="●" label={t("matrix.named")} />}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="tools-title">
        <h2 id="tools-title">{t("tools.title")}</h2>
        <p className={styles.unit}>{t("tools.legend")}</p>
        <div className={styles.tableWrap}>
          <table className={styles.table} data-table="tools">
            <caption className={styles.srOnly}>{t("tools.title")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("tools.tool")}</th>
                {ids.map((id) => (
                  <th key={id} scope="col" className={styles.matrixCell}>
                    {id}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {listed.map((tool) => (
                <tr key={tool.id} data-tool={tool.id}>
                  <th scope="row">{tool.name}</th>
                  {ids.map((id) => {
                    const role = roleOf(id, tool.id);
                    return (
                      <td key={id} data-case={id} data-role={role} className={styles.matrixCell}>
                        {role === "named" && <Mark symbol="●" label={t("matrix.named")} />}
                        {role === "supporting" && <Mark symbol="○" label={t("matrix.supporting")} />}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
