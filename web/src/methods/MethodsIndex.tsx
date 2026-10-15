import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import { pick } from "~/cases/types";
import { type MethodEntry, type MethodStatus, methodSlug } from "./registry";
import { statusText } from "./status";

/** FR-020-17: one row per method of the registry, in registry order. */
export function MethodsIndex({
  methods,
  statuses = {},
}: {
  methods: MethodEntry[];
  statuses?: Record<string, MethodStatus>;
}) {
  const { t, i18n } = useTranslation("results");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} data-testid="methods-table">
        <thead>
          <tr>
            {(
              [
                "id",
                "name",
                "tiers",
                "implementation",
                "spdx",
                "lanes",
                "cases",
                "learned",
                "status",
              ] as const
            ).map((c) => (
              <th key={c} scope="col">
                {t(`methodsPage.table.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {methods.map((m) => {
            const slug = methodSlug(m.id);
            return (
              <tr key={m.id} data-method={m.id}>
                <th scope="row" data-field="id">
                  {slug ? <Link to={`/methods/${slug}/`}>{m.id}</Link> : m.id}
                </th>
                <td data-field="name">{pick(m.name, lang)}</td>
                <td data-field="tiers">{m.tiers.join(", ")}</td>
                <td data-field="implementation">{m.implementation}</td>
                <td data-field="spdx">{m.spdx.join(", ")}</td>
                <td data-field="lanes">{m.lanes.join(", ")}</td>
                <td data-field="cases">{m.cases.join(", ")}</td>
                <td data-field="learned" data-learned={String(m.learned)}>
                  {t(m.learned ? "methodsPage.learned" : "methodsPage.classical")}
                </td>
                <td data-field="status">{statusText(t, statuses[m.id])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
