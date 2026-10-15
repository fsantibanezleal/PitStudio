import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import styles from "~/cases/cases.module.css";
import { type BibliographyRow, type DatasetRow, type FrameworkRow, httpsUrl } from "./types";

// Scheme-relative on purpose: the card lives in the repository, and only the dataset landing page is an https link.
const REPO_BLOB = "//github.com/fsantibanezleal/PitStudio/blob/main/";
const safeCard = (p: unknown) =>
  typeof p === "string" && /^[A-Za-z0-9_./-]+$/.test(p) && !p.includes("..") ? `${REPO_BLOB}${p}` : undefined;

/** FR-020-36: every dataset of the sources registry; third-party (real) data is never redistributed. */
export function DatasetsSection({ datasets }: { datasets: DatasetRow[] }) {
  const { t } = useTranslation("results");
  return (
    <section data-testid="datasets" aria-label={t("knowledge.nav.datasets")} className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {(["id", "kind", "spdx", "redistribution", "landing", "card"] as const).map((c) => (
              <th key={c} scope="col">
                {t(`knowledge.datasets.${c}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {datasets.map((d) => {
            const landing = httpsUrl(d.landing_url);
            const card = safeCard(d.card);
            return (
              <tr key={d.id} data-dataset={d.id}>
                <th scope="row">{d.id}</th>
                <td>
                  {d.kind === "real" ? t("knowledge.datasets.real") : t("knowledge.datasets.synthetic")}
                </td>
                <td>{d.spdx}</td>
                <td>{d.redistribution}</td>
                <td>
                  {landing ? (
                    <a href={landing} rel="noreferrer">
                      {t("knowledge.datasets.landing")}
                    </a>
                  ) : (
                    <span>{String(d.landing_url ?? "")}</span>
                  )}
                  {d.kind === "real" && (
                    <span data-field="provenance"> {t("knowledge.datasets.provenance")}</span>
                  )}
                </td>
                <td>
                  {card && (
                    <a href={card} rel="noreferrer">
                      {t("knowledge.datasets.card")}
                    </a>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

const STATUS_KEY: Record<string, string> = {
  "not-yet-run": "notYetRun",
  "evaluated-not-adopted": "evaluatedNotAdopted",
  done: "done",
};

/** FR-037: every framework or tool, the evaluated-not-adopted ones included; only studio tools have a page. */
export function FrameworksSection({ frameworks }: { frameworks: FrameworkRow[] }) {
  const { t } = useTranslation("results");
  return (
    <section data-testid="frameworks" aria-label={t("knowledge.nav.frameworks")}>
      <ul className={styles.rows}>
        {frameworks.map((f) => (
          <li key={f.id} data-framework={f.id} className={styles.card}>
            <h4>
              {f.category === "studio-tool" ? (
                <Link to={`/studio/tools/${encodeURIComponent(f.id)}/`}>{f.name}</Link>
              ) : (
                f.name
              )}
            </h4>
            <p>{t(`knowledge.frameworks.${STATUS_KEY[f.status] ?? "notYetRun"}`)}</p>
            {f.licence_class && (
              <p className={styles.unit}>{t("knowledge.frameworks.licence", { value: f.licence_class })}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** FR-038: every entry with a stable anchor equal to its citation key, a DOI or URL link, and who cites it. */
export function BibliographySection({ bibliography }: { bibliography: BibliographyRow[] }) {
  const { t } = useTranslation("results");
  return (
    <section data-testid="bibliography" aria-label={t("knowledge.nav.bibliography")}>
      {bibliography.map((b) => {
        const href = b.doi ? `https://doi.org/${encodeURI(String(b.doi))}` : httpsUrl(b.url);
        const cite = `${b.authors} (${String(b.year ?? "")}). `;
        return (
          <article key={b.key} data-bib={b.key} id={b.key} className={styles.card}>
            <p>
              {cite}
              <strong>{b.title}</strong>
            </p>
            {href && (
              <p>
                <a href={href} rel="noreferrer">
                  {b.doi ? t("knowledge.bib.doi") : t("knowledge.bib.link")}
                </a>
              </p>
            )}
            {(b.cited_by?.parameters ?? []).length > 0 && (
              <ul aria-label={t("knowledge.bib.citedParameters")}>
                {(b.cited_by?.parameters ?? []).map((id) => (
                  <li key={id} data-cited-parameter={id}>
                    <Link to={`/knowledge/?section=parameters&q=${encodeURIComponent(id)}`}>{id}</Link>
                  </li>
                ))}
              </ul>
            )}
            {(b.cited_by?.equations ?? []).length > 0 && (
              <ul aria-label={t("knowledge.bib.citedEquations")}>
                {(b.cited_by?.equations ?? []).map((id) => (
                  <li key={id} data-cited-equation={id}>
                    <Link to={`/knowledge/?section=equations#eq-${encodeURIComponent(id)}`}>{id}</Link>
                  </li>
                ))}
              </ul>
            )}
          </article>
        );
      })}
    </section>
  );
}
