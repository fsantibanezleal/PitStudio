import { TriangleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import styles from "~/cases/cases.module.css";
import { unitSymbol } from "~/cases/units";
import { useHydrated } from "~/shell/useHydrated";
import { SearchField, useQuery } from "./SearchField";
import { searchRows } from "./search";
import type { ParameterRow } from "./types";

const STATUSES = ["verified", "UNVERIFIED"] as const;

const show = (v: unknown) => (typeof v === "number" || typeof v === "string" ? String(v) : "");
const range = (r: { min: number; max: number } | undefined) => (r ? `${show(r.min)} – ${show(r.max)}` : "");

/** The UNVERIFIED badge: text and icon, never colour alone (FR-020-33). */
export function UnverifiedBadge() {
  const { t } = useTranslation("results");
  return (
    <span data-testid="unverified-badge" className={styles.pending}>
      <TriangleAlert aria-hidden="true" size={14} /> {t("knowledge.unverified")}
    </span>
  );
}

/** FR-020-33: one row per knowledge-table row, filters by module and status read from the URL, text search. */
export function ParametersSection({ parameters }: { parameters: ParameterRow[] }) {
  const { t } = useTranslation("results");
  const [params, setParams] = useSearchParams();
  const [q] = useQuery();
  const modules = [...new Set(parameters.map((p) => p.module))].sort();
  const hydrated = useHydrated();
  const moduleParam = hydrated ? (params.get("module") ?? "") : "";
  const statusParam = hydrated ? (params.get("status") ?? "") : "";
  const module = modules.includes(moduleParam) ? moduleParam : "";
  const status = (STATUSES as readonly string[]).includes(statusParam) ? statusParam : "";

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value === "") next.delete(key);
    else next.set(key, value);
    setParams(next, { replace: true, preventScrollReset: true });
  };

  const rows = searchRows(
    parameters.filter(
      (p) => (module === "" || p.module === module) && (status === "" || p.verification === status),
    ),
    q,
    (p) => [p.id, p.quantity ?? "", p.module, p.citation, ...(p.symbols ?? [])],
  );

  return (
    <section data-testid="parameters" aria-label={t("knowledge.nav.parameters")}>
      <div>
        <label>
          {t("knowledge.filter.module")}{" "}
          <select data-testid="filter-module" value={module} onChange={(e) => set("module", e.target.value)}>
            <option value="">{t("knowledge.filter.all")}</option>
            {modules.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>{" "}
        <label>
          {t("knowledge.filter.status")}{" "}
          <select data-testid="filter-status" value={status} onChange={(e) => set("status", e.target.value)}>
            <option value="">{t("knowledge.filter.all")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s === "verified" ? t("knowledge.verified") : s}
              </option>
            ))}
          </select>
        </label>{" "}
        <SearchField />
      </div>
      {rows.length === 0 ? (
        <p data-testid="no-match">{t("knowledge.noParameters")}</p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">{t("knowledge.param.id")}</th>
                {(
                  ["module", "value", "units", "si", "citation", "page", "verification", "symbols"] as const
                ).map((c) => (
                  <th key={c} scope="col">
                    {t(`knowledge.param.${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => {
                const siUnit = p.si ? unitSymbol(p.si.unit) : "";
                return (
                  <tr key={p.id} data-parameter={p.id}>
                    <th scope="row">{p.id}</th>
                    <td data-field="module">{p.module}</td>
                    <td data-field="value">{p.range ? range(p.range) : show(p.value)}</td>
                    <td data-field="units">{p.units}</td>
                    <td data-field="si">
                      {p.si ? `${p.si.range ? range(p.si.range) : show(p.si.value)} ${siUnit}`.trim() : ""}
                    </td>
                    <td data-field="citation">
                      <Link to={`/knowledge/?section=bibliography#${p.citation}`}>{p.citation}</Link>
                    </td>
                    <td data-field="page">{p.page ?? ""}</td>
                    <td data-field="verification">
                      {p.verification === "UNVERIFIED" ? (
                        <UnverifiedBadge />
                      ) : (
                        <span>{t("knowledge.verified")}</span>
                      )}
                    </td>
                    <td data-field="symbols">{(p.symbols ?? []).join(", ")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
