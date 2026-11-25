import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { fmt, ticks } from "./Chart";
import type { ChartDoc } from "./chartSeries";
import styles from "./seriesChart.module.css";

type Lang = "en" | "es";

const W = 640;
const M = { left: 60, right: 12, top: 12, bottom: 34 };
const ROLE_COLOR: Record<string, string> = {
  ground: "var(--fg)",
  bench: "var(--chart-2)",
  shell: "var(--chart-3)",
  water: "var(--chart-1)",
  other: "var(--chart-4)",
};

/** A vertical section: polylines and circles drawn with the same scale on both axes (a slope is a shape, not a graph). */
export function SectionPlot({ doc, lang, title }: { doc: ChartDoc; lang: Lang; title: string }) {
  const { t } = useTranslation("charts");
  const uid = useId();
  const [open, setOpen] = useState(false);
  const s = doc.section;
  const xAxis = doc.x_axis;
  const yAxis = doc.y_axis;
  if (!s || !xAxis || !yAxis) return null;
  const circles = s.circles ?? [];
  // the view holds every polyline vertex; a circle is drawn clipped to it (its arc inside the section matters, not its far side)
  const px0 = Math.min(...s.polylines.flatMap((p) => p.points.map((q) => q[0])));
  const px1 = Math.max(...s.polylines.flatMap((p) => p.points.map((q) => q[0])));
  const py0 = Math.min(...s.polylines.flatMap((p) => p.points.map((q) => q[1])));
  const py1 = Math.max(...s.polylines.flatMap((p) => p.points.map((q) => q[1])));
  const padX = (px1 - px0 || 1) * 0.04;
  const padY = (py1 - py0 || 1) * 0.08;
  const [x0, x1, y0, y1] = [px0 - padX, px1 + padX, py0 - padY, py1 + padY];
  const pw = W - M.left - M.right;
  const scale = pw / (x1 - x0);
  const ph = Math.min(520, Math.max(120, (y1 - y0) * scale));
  const H = ph + M.top + M.bottom;
  const sx = (v: number) => M.left + (v - x0) * scale;
  const sy = (v: number) => M.top + ph - (v - y0) * (ph / (y1 - y0));
  const clip = `${uid}-clip`;
  const tableId = `${uid}-table`;
  return (
    <div className={styles.panel} data-testid="series-section" data-chart-id={doc.id}>
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
        <defs>
          <clipPath id={clip}>
            <rect x={M.left} y={M.top} width={pw} height={ph} />
          </clipPath>
        </defs>
        {ticks(y0, y1, "linear", 5).map((v) => (
          <g key={`y${v}`}>
            <line className={styles.grid} x1={M.left} x2={W - M.right} y1={sy(v)} y2={sy(v)} />
            <text className={styles.tick} x={M.left - 6} y={sy(v)} textAnchor="end" dominantBaseline="middle">
              {fmt(v, lang)}
            </text>
          </g>
        ))}
        {ticks(x0, x1, "linear", 6).map((v) => (
          <text key={`x${v}`} className={styles.tick} x={sx(v)} y={H - M.bottom + 14} textAnchor="middle">
            {fmt(v, lang)}
          </text>
        ))}
        <rect className={styles.axis} x={M.left} y={M.top} width={pw} height={ph} />
        <g clipPath={`url(#${clip})`}>
          {circles.map((c) => (
            <circle
              key={c.id}
              data-circle={c.id}
              cx={sx(c.cx)}
              cy={sy(c.cy)}
              r={c.r * scale}
              style={{
                fill: "none",
                stroke: c.role === "critical" ? "var(--chart-5)" : "var(--chart-6)",
                strokeWidth: c.role === "critical" ? 2.5 : 1.5,
                strokeDasharray: c.role === "critical" ? undefined : "5 4",
              }}
            />
          ))}
          {s.polylines.map((p) => (
            <polyline
              key={p.id}
              data-polyline={p.id}
              points={p.points.map((q) => `${sx(q[0])},${sy(q[1])}`).join(" ")}
              style={{
                fill: "none",
                stroke: ROLE_COLOR[p.role ?? "other"],
                strokeWidth: p.role === "ground" ? 2.5 : 1.75,
                strokeDasharray: p.role === "water" ? "6 4" : undefined,
              }}
            />
          ))}
        </g>
        {(doc.markers ?? []).map((m) =>
          m.x !== undefined && m.y !== undefined ? (
            <g key={m.id} data-marker={m.id} style={{ fill: "var(--fg)", stroke: "var(--fg)" }}>
              <circle cx={sx(m.x)} cy={sy(m.y)} r={4} />
              <text x={sx(m.x) + 7} y={sy(m.y) - 5} style={{ stroke: "none", fontSize: "11px" }}>
                {m.label[lang]} {m.value_text}
              </text>
            </g>
          ) : null,
        )}
      </svg>
      <p className={styles.help}>
        {xAxis.label[lang]} ({xAxis.unit}){" · "}
        {yAxis.label[lang]} ({yAxis.unit}){" · "}
        {t("section.equal")}
      </p>
      <ul className={styles.legend}>
        {s.polylines.map((p) => (
          <li key={p.id}>
            <span className={styles.swatch} style={{ background: ROLE_COLOR[p.role ?? "other"] }} />
            {p.label[lang]}
          </li>
        ))}
        {circles.map((c) => (
          <li key={c.id}>
            <span
              className={styles.swatch}
              style={{ background: c.role === "critical" ? "var(--chart-5)" : "var(--chart-6)" }}
            />
            {c.label[lang]} ({t("section.radius", { r: fmt(c.r, lang), unit: xAxis.unit })})
          </li>
        ))}
      </ul>
      <div id={tableId} hidden={!open}>
        {open && (
          <div className={styles.tableWrap}>
            <table className={styles.table} data-testid="chart-table" aria-label={title}>
              <thead>
                <tr>
                  <th scope="col">{t("section.element")}</th>
                  <th scope="col">
                    {xAxis.label[lang]} ({xAxis.unit})
                  </th>
                  <th scope="col">
                    {yAxis.label[lang]} ({yAxis.unit})
                  </th>
                </tr>
              </thead>
              <tbody>
                {s.polylines.flatMap((p) =>
                  p.points.map((q, i) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: a vertex has no id of its own, its order is its identity
                    <tr key={`${p.id}-${i}`}>
                      <td>{p.label[lang]}</td>
                      <td>{q[0]}</td>
                      <td>{q[1]}</td>
                    </tr>
                  )),
                )}
                {circles.map((c) => (
                  <tr key={c.id}>
                    <td>
                      {c.label[lang]} ({t("section.centre")},{" "}
                      {t("section.radius", { r: c.r, unit: xAxis.unit })})
                    </td>
                    <td>{c.cx}</td>
                    <td>{c.cy}</td>
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
