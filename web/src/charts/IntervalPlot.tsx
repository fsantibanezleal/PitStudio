import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { fmt, ticks } from "./Chart";
import styles from "./seriesChart.module.css";

export interface IntervalEntry {
  id: string;
  label: string;
  lo: number;
  hi: number;
  /** The estimate inside the interval, when the row has one (a difference interval has none of its own). */
  point?: number;
}

const W = 640;
const M = { left: 16, right: 16, top: 12, bottom: 34 };
const ROW = 44;

/**
 * Intervals drawn as intervals (FR-018-85): a segment from the lower to the upper end with a cap on each end, the estimate as a
 * point when there is one, and for a difference the zero reference. A difference interval is never drawn as a line between
 * its ends on a position axis. Keyboard: the arrows move the read-out between intervals; "Show data" lists every number.
 */
export function IntervalPlot({
  id,
  title,
  unit,
  intervals,
  zero,
  level,
  lang,
}: {
  id: string;
  title: string;
  unit: string;
  intervals: IntervalEntry[];
  /** Draw the zero reference (the interval is a difference). */
  zero: boolean;
  level: number;
  lang: "en" | "es";
}) {
  const { t } = useTranslation("charts");
  const uid = useId();
  const [cursor, setCursor] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const values = intervals.flatMap((i) => [i.lo, i.hi, ...(i.point !== undefined ? [i.point] : [])]);
  const lo = Math.min(...values, ...(zero ? [0] : []));
  const hi = Math.max(...values, ...(zero ? [0] : []));
  const pad = (hi > lo ? hi - lo : Math.max(Math.abs(lo), 1)) * 0.06;
  const [x0, x1] = [lo - pad, hi + pad];
  const pw = W - M.left - M.right;
  const H = M.top + intervals.length * ROW + M.bottom;
  const sx = (v: number) => M.left + ((v - x0) / (x1 - x0)) * pw;
  // the zero label (7 px per character at the tick font) goes to the left of the line when it would run past the right edge
  const zeroText = t("zeroReference");
  const flipZero = sx(0) + 4 + zeroText.length * 7 > W - M.right;
  const readout =
    cursor === null
      ? null
      : (() => {
          const i = intervals[cursor] as IntervalEntry;
          return `${i.label}: ${t("intervalText", { level: Math.round(level * 100), lo: fmt(i.lo, lang), hi: fmt(i.hi, lang), unit })}`;
        })();
  const onKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const n = intervals.length;
    if (event.key === "ArrowDown" || event.key === "ArrowRight")
      setCursor((c) => Math.min(n - 1, (c ?? -1) + 1));
    else if (event.key === "ArrowUp" || event.key === "ArrowLeft")
      setCursor((c) => Math.max(0, (c ?? n) - 1));
    else if (event.key === "Escape") setCursor(null);
    else return;
    event.preventDefault();
  };
  const tableId = `${uid}-table`;
  return (
    <div
      className={styles.panel}
      data-testid="chart"
      data-chart-id={id}
      data-chart-kind="interval"
      data-intervals={intervals.length}
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
        {ticks(x0, x1, "linear", 6).map((v) => (
          <g key={v}>
            <line className={styles.grid} x1={sx(v)} x2={sx(v)} y1={M.top} y2={H - M.bottom} />
            <text className={styles.tick} x={sx(v)} y={H - M.bottom + 14} textAnchor="middle">
              {fmt(v, lang)}
            </text>
          </g>
        ))}
        <line className={styles.axis} x1={M.left} x2={W - M.right} y1={H - M.bottom} y2={H - M.bottom} />
        {zero && (
          <g data-zero-reference>
            <line
              x1={sx(0)}
              x2={sx(0)}
              y1={M.top}
              y2={H - M.bottom}
              style={{ stroke: "var(--fg)", strokeWidth: 1.5, strokeDasharray: "5 4" }}
            />
            <text
              className={styles.tick}
              x={flipZero ? sx(0) - 4 : sx(0) + 4}
              y={M.top + 10}
              textAnchor={flipZero ? "end" : "start"}
              style={{ fill: "var(--fg)" }}
            >
              {zeroText}
            </text>
          </g>
        )}
        {intervals.map((i, k) => {
          const cy = M.top + k * ROW + ROW / 2 + 6;
          const color = `var(--chart-${(k % 6) + 1})`;
          return (
            <g
              key={i.id}
              data-interval={i.id}
              data-lo={i.lo}
              data-hi={i.hi}
              style={{
                stroke: color,
                strokeWidth: cursor === k ? 4 : 2.5,
                opacity: cursor === null || cursor === k ? 1 : 0.6,
              }}
            >
              <line x1={sx(i.lo)} x2={sx(i.hi)} y1={cy} y2={cy} />
              <line x1={sx(i.lo)} x2={sx(i.lo)} y1={cy - 7} y2={cy + 7} />
              <line x1={sx(i.hi)} x2={sx(i.hi)} y1={cy - 7} y2={cy + 7} />
              {i.point !== undefined && <circle cx={sx(i.point)} cy={cy} r={5} style={{ fill: color }} />}
              <text x={M.left} y={cy - 12} style={{ fill: "var(--fg)", stroke: "none", fontSize: "12px" }}>
                {i.label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className={styles.help}>{t("intervalAxis", { unit, level: Math.round(level * 100) })}</p>
      <p id={`${uid}-help`} className={styles.help}>
        {t("intervalHelp")}
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
                  <th scope="col">
                    {t("lower")} ({unit})
                  </th>
                  <th scope="col">
                    {t("upper")} ({unit})
                  </th>
                  <th scope="col">
                    {t("estimate")} ({unit})
                  </th>
                </tr>
              </thead>
              <tbody>
                {intervals.map((i) => (
                  <tr key={i.id}>
                    <td>{i.label}</td>
                    <td>{i.lo}</td>
                    <td>{i.hi}</td>
                    <td>{i.point ?? t("notAvailable")}</td>
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
