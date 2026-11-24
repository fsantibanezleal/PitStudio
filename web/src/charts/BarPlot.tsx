import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { fmt, ticks } from "./Chart";
import type { ChartDoc } from "./chartSeries";
import styles from "./seriesChart.module.css";

type Lang = "en" | "es";

const W = 640;
const H = 300;
const M = { left: 60, right: 12, top: 12, bottom: 56 };
const COLORS = [1, 2, 3, 4, 5, 6];

/** A bar chart with error bars: one group per category, one bar per series, the interval (lo, hi) as a whisker. */
export function BarPlot({ doc, lang, title }: { doc: ChartDoc; lang: Lang; title: string }) {
  const { t } = useTranslation("charts");
  const uid = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const cats = doc.categories;
  const series = doc.series;
  const yAxis = doc.y_axis;
  if (!cats || !series || !yAxis) return null;
  const nCat = cats.length;
  const nSer = series.length;
  const all = series
    .flatMap((s) => [...s.y, ...(s.lo ?? []), ...(s.hi ?? [])])
    .filter((v): v is number => v !== null);
  const lo = Math.min(0, ...all);
  const hi = Math.max(0, ...all);
  const span = hi > lo ? hi - lo : 1;
  const y0 = lo < 0 ? lo - 0.05 * span : lo;
  const y1 = hi + 0.05 * span;
  const pw = W - M.left - M.right;
  const ph = H - M.top - M.bottom;
  const px = (i: number) => M.left + ((i + 0.5) / nCat) * pw;
  const py = (v: number) => M.top + ph - ((v - y0) / (y1 - y0)) * ph;
  const barW = Math.min(48, (pw / nCat / (nSer + 0.5)) * 0.9);
  const yt = ticks(y0, y1, "linear", 5);
  const unitOf = (k: number) => series[k]?.unit ?? yAxis.unit;
  const valueText = (k: number, i: number) => {
    const s = series[k];
    const v = s?.y[i];
    if (!s || v === undefined || v === null) return t("notAvailable");
    const a = s.lo?.[i];
    const b = s.hi?.[i];
    const iv = typeof a === "number" && typeof b === "number" ? ` [${fmt(a, lang)}, ${fmt(b, lang)}]` : "";
    return `${fmt(v, lang)} ${unitOf(k)}${iv}`;
  };
  const readout =
    cursor === null
      ? null
      : (cats[cursor]?.label[lang] ?? "") +
        series.map((s, k) => ` · ${s.label[lang]} ${valueText(k, cursor)}`).join("");
  const onKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const key = event.key;
    if (key === "ArrowRight") setCursor((c) => Math.min(nCat - 1, (c ?? -1) + 1));
    else if (key === "ArrowLeft") setCursor((c) => Math.max(0, (c ?? nCat) - 1));
    else if (key === "Home") setCursor(0);
    else if (key === "End") setCursor(nCat - 1);
    else if (key === "Escape") setCursor(null);
    else return;
    event.preventDefault();
  };
  const tableId = `${uid}-table`;
  return (
    <div
      className={styles.panel}
      data-testid="series-bar"
      data-chart-id={doc.id}
      role="application"
      aria-label={title}
      aria-describedby={`${uid}-help`}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: a custom widget with a documented keyboard model (FR-020-11)
      tabIndex={0}
      onKeyDown={onKey}
    >
      <div className={styles.head}>
        <strong>{title}</strong>
        <button
          type="button"
          className={styles.button}
          aria-expanded={open}
          aria-controls={tableId}
          onClick={() => setOpen((o) => !o)}
        >
          {open ? t("hideData") : t("showData")}
        </button>
      </div>
      <svg className={styles.svg} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        <title>{title}</title>
        {yt.map((v) => (
          <g key={v}>
            <line className={styles.grid} x1={M.left} x2={W - M.right} y1={py(v)} y2={py(v)} />
            <text className={styles.tick} x={M.left - 6} y={py(v)} textAnchor="end" dominantBaseline="middle">
              {fmt(v, lang)}
            </text>
          </g>
        ))}
        <line className={styles.axis} x1={M.left} x2={W - M.right} y1={py(0)} y2={py(0)} />
        <line className={styles.axis} x1={M.left} x2={M.left} y1={M.top} y2={M.top + ph} />
        {cats.map((c, i) => (
          <text
            key={c.id}
            className={styles.tick}
            x={px(i)}
            y={H - M.bottom + 14}
            textAnchor="middle"
            style={{ fontWeight: cursor === i ? 700 : 400 }}
          >
            {c.label[lang]}
          </text>
        ))}
        {series.map((s, k) =>
          cats.map((c, i) => {
            const v = s.y[i];
            if (v === null || v === undefined) return null;
            const cx = px(i) + (k - (nSer - 1) / 2) * barW;
            const a = s.lo?.[i];
            const b = s.hi?.[i];
            const top = Math.min(py(v), py(0));
            return (
              <g key={`${s.id}-${c.id}`} data-bar={`${s.id}:${c.id}`} data-value={v}>
                <rect
                  x={cx - barW / 2}
                  y={top}
                  width={barW}
                  height={Math.abs(py(v) - py(0))}
                  style={{
                    fill: `var(--chart-${COLORS[k % COLORS.length]})`,
                    opacity: cursor === null || cursor === i ? 1 : 0.55,
                  }}
                />
                {typeof a === "number" && typeof b === "number" && (
                  <g style={{ stroke: "var(--fg)", strokeWidth: 1.5 }} data-whisker={`${a},${b}`}>
                    <line x1={cx} x2={cx} y1={py(a)} y2={py(b)} />
                    <line x1={cx - 5} x2={cx + 5} y1={py(a)} y2={py(a)} />
                    <line x1={cx - 5} x2={cx + 5} y1={py(b)} y2={py(b)} />
                  </g>
                )}
              </g>
            );
          }),
        )}
      </svg>
      <p className={styles.help}>
        {yAxis.label[lang]} ({yAxis.unit})
      </p>
      <ul className={styles.legend}>
        {series.map((s, k) => (
          <li key={s.id}>
            <span
              className={styles.swatch}
              style={{ background: `var(--chart-${COLORS[k % COLORS.length]})` }}
            />
            {s.label[lang]} ({unitOf(k)})
            {s.band_label ? ` · ${s.band_label[lang]}` : s.lo ? ` · ${t("whisker")}` : ""}
          </li>
        ))}
      </ul>
      <p id={`${uid}-help`} className={styles.help}>
        {t("barHelp")}
      </p>
      {readout && (
        <output className={styles.readout} data-testid="readout">
          {readout}
        </output>
      )}
      <div id={tableId} hidden={!open}>
        {open && (
          <div className={styles.tableWrap}>
            <table className={styles.table} data-testid="chart-table" aria-label={title}>
              <thead>
                <tr>
                  <th scope="col">{t("category")}</th>
                  {series.flatMap((s, k) => [
                    <th key={`${s.id}-y`} scope="col" data-series={s.id}>
                      {s.label[lang]} ({unitOf(k)})
                    </th>,
                    ...(s.lo
                      ? [
                          <th key={`${s.id}-lo`} scope="col">
                            {s.label[lang]}, {t("lower")} ({unitOf(k)})
                          </th>,
                          <th key={`${s.id}-hi`} scope="col">
                            {s.label[lang]}, {t("upper")} ({unitOf(k)})
                          </th>,
                        ]
                      : []),
                  ])}
                </tr>
              </thead>
              <tbody>
                {cats.map((c, i) => (
                  <tr key={c.id}>
                    <td>{c.label[lang]}</td>
                    {series.flatMap((s) => [
                      <td key={`${s.id}-y`}>{s.y[i] ?? t("notAvailable")}</td>,
                      ...(s.lo
                        ? [
                            <td key={`${s.id}-lo`}>{s.lo[i] ?? t("notAvailable")}</td>,
                            <td key={`${s.id}-hi`}>{s.hi?.[i] ?? t("notAvailable")}</td>,
                          ]
                        : []),
                    ])}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
