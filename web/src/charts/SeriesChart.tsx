import { useTranslation } from "react-i18next";
import { BarPlot } from "./BarPlot";
import type { ChartDoc } from "./chartSeries";
import { LinePlot } from "./LinePlot";
import { RasterPlot } from "./RasterPlot";
import { SectionPlot } from "./SectionPlot";
import styles from "./seriesChart.module.css";

type Lang = "en" | "es";

/** A table number at five significant digits, in the page language; a value of the file is never printed as its raw float. */
const cellNumber = (value: number, lang: Lang) =>
  new Intl.NumberFormat(lang, { maximumSignificantDigits: 5, useGrouping: false }).format(value);

function TablePlot({ doc, lang, title }: { doc: ChartDoc; lang: Lang; title: string }) {
  const { t } = useTranslation("charts");
  const table = doc.table;
  if (!table) return null;
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table} data-testid="chart-table" aria-label={title}>
        <thead>
          <tr>
            {table.columns.map((c) => (
              <th key={c.id} scope="col" data-series={c.id}>
                {c.label[lang]}
                {c.unit ? ` (${c.unit})` : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: a table row has no id of its own, its order is its identity
            <tr key={i}>
              {row.map((cell, k) => (
                <td key={table.columns[k]?.id}>
                  {cell === null
                    ? t("notAvailable")
                    : typeof cell === "number"
                      ? cellNumber(cell, lang)
                      : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The producer label under every chart: tool, method, version and the data label of the run (FR-020-56). */
export function ProducerLine({ doc }: { doc: ChartDoc }) {
  const { t } = useTranslation("charts");
  const p = doc.producer;
  return (
    <p className={styles.producer} data-testid="chart-producer" data-producer={p.tool}>
      {t("producer", {
        tool: p.tool,
        method: p.method,
        version: p.version,
        label: p.label,
        interpolation: { escapeValue: false },
      })}
    </p>
  );
}

/**
 * One chart of a published run, by its type (FR-020-55): line, scatter and ECDF through the interactive chart (bands, steps,
 * markers), bars with error bars, a raster map with its colour scale, a section profile or a table, each with its axes, units
 * and the producer label of the run under it. A value not run shows its reason and draws nothing (FR-020-57).
 */
export function SeriesChart({ doc }: { doc: ChartDoc }) {
  const { t, i18n } = useTranslation("charts");
  const lang: Lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const title = doc.title[lang];
  let body: React.ReactNode;
  if (doc.status === "not-run") {
    body = (
      <p className={styles.notRun} data-testid="chart-not-run">
        {t("notRun", { reason: doc.not_run_reason?.[lang] ?? "" })}
      </p>
    );
  } else if (doc.chart_type === "bar") body = <BarPlot doc={doc} lang={lang} title={title} />;
  else if (doc.chart_type === "raster") body = <RasterPlot doc={doc} lang={lang} title={title} />;
  else if (doc.chart_type === "section") body = <SectionPlot doc={doc} lang={lang} title={title} />;
  else if (doc.chart_type === "table") body = <TablePlot doc={doc} lang={lang} title={title} />;
  else body = <LinePlot doc={doc} lang={lang} title={title} />;
  const markers =
    doc.chart_type === "line" || doc.chart_type === "scatter" || doc.chart_type === "ecdf"
      ? []
      : (doc.markers ?? []);
  return (
    <figure
      className={styles.figure}
      data-chart-series={doc.id}
      data-chart-type={doc.chart_type}
      data-status={doc.status}
      data-testid="chart-series"
    >
      <h4 className={styles.heading}>{title}</h4>
      {doc.status === "ok" &&
        doc.x_axis &&
        doc.y_axis &&
        doc.chart_type !== "raster" &&
        doc.chart_type !== "section" && (
          <p className={styles.caption} data-testid="chart-axes">
            {t("axes", {
              x: `${doc.x_axis.label[lang]} (${doc.x_axis.unit})`,
              y: `${doc.y_axis.label[lang]} (${doc.y_axis.unit})`,
            })}
          </p>
        )}
      {body}
      {markers.length > 0 && (
        <ul className={styles.legend}>
          {markers.map((m) => (
            <li key={m.id} data-marker={m.id}>
              {m.label[lang]}: {m.value_text}
            </li>
          ))}
        </ul>
      )}
      {doc.caption && <figcaption className={styles.caption}>{doc.caption[lang]}</figcaption>}
      <ProducerLine doc={doc} />
    </figure>
  );
}
