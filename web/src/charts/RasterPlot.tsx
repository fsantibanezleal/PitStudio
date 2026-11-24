import { useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useTranslation } from "react-i18next";
import { fmt, ticks } from "./Chart";
import type { ChartDoc } from "./chartSeries";
import { colormap, rgbText } from "./colormaps";
import { DataTable } from "./DataTable";
import styles from "./seriesChart.module.css";

type Lang = "en" | "es";

const PLOT_W = 560;
const MARGIN = { left: 64, right: 10, top: 10, bottom: 30 };

function tokens(el: Element) {
  const css = getComputedStyle(el);
  const token = (name: string) => css.getPropertyValue(name).trim();
  return { axis: token("--fg-muted"), grid: token("--border"), text: token("--fg") };
}

/** A raster map: nx by ny cells over an extent, coloured by one of the four allowed maps, with axes, units and a colour scale. */
export function RasterPlot({ doc, lang, title }: { doc: ChartDoc; lang: Lang; title: string }) {
  const { t } = useTranslation("charts");
  const uid = useId();
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const [cell, setCell] = useState<{ ix: number; iy: number } | null>(null);
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState(0);
  const r = doc.raster;
  const xAxis = doc.x_axis;
  const yAxis = doc.y_axis;
  const {
    nx,
    ny,
    extent: e,
    values,
    colour,
  } = r ?? {
    nx: 0,
    ny: 0,
    extent: { x0: 0, x1: 1, y0: 0, y1: 1 },
    values: [] as Array<number | null>,
    colour: { colormap: "viridis" as const, vmin: 0, vmax: 1, unit: "1", label: { en: "", es: "" } },
  };
  const dx = e.x1 - e.x0;
  const dy = e.y1 - e.y0;
  const plotH = Math.round(Math.min(640, Math.max(140, (PLOT_W * dy) / dx)));
  const W = PLOT_W + MARGIN.left + MARGIN.right;
  const H = plotH + MARGIN.top + MARGIN.bottom;

  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    const bump = () => flushSync(() => setTheme((n) => n + 1));
    const observer = new MutationObserver(bump);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
    media?.addEventListener("change", bump);
    return () => {
      observer.disconnect();
      media?.removeEventListener("change", bump);
    };
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: `theme` repaints the canvas when the theme tokens change
  useLayoutEffect(() => {
    const cv = canvas.current;
    const el = root.current;
    if (!cv || !el || !r) return;
    const g = cv.getContext("2d");
    if (!g) return;
    const dpr = typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1;
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(H * dpr);
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const c = tokens(el);
    const cw = PLOT_W / nx;
    const ch = plotH / ny;
    for (let iy = 0; iy < ny; iy++) {
      for (let ix = 0; ix < nx; ix++) {
        const v = values[iy * nx + ix];
        if (v === null || v === undefined) continue;
        g.fillStyle = rgbText(colormap(colour.colormap, (v - colour.vmin) / (colour.vmax - colour.vmin)));
        g.fillRect(MARGIN.left + ix * cw, MARGIN.top + iy * ch, Math.ceil(cw), Math.ceil(ch));
      }
    }
    g.strokeStyle = c.axis;
    g.strokeRect(MARGIN.left + 0.5, MARGIN.top + 0.5, PLOT_W - 1, plotH - 1);
    g.font = "11px system-ui, sans-serif";
    g.fillStyle = c.axis;
    g.textAlign = "center";
    g.textBaseline = "top";
    for (const v of ticks(e.x0, e.x1, "linear", 5)) {
      const x = MARGIN.left + ((v - e.x0) / dx) * PLOT_W;
      g.fillRect(x, MARGIN.top + plotH, 1, 4);
      g.fillText(fmt(v, lang), x, MARGIN.top + plotH + 6);
    }
    g.textAlign = "right";
    g.textBaseline = "middle";
    for (const v of ticks(e.y0, e.y1, "linear", 5)) {
      const y = MARGIN.top + plotH - ((v - e.y0) / dy) * plotH;
      g.fillRect(MARGIN.left - 4, y, 4, 1);
      g.fillText(fmt(v, lang), MARGIN.left - 6, y);
    }
    if (cell) {
      g.strokeStyle = c.text;
      g.lineWidth = 2;
      g.strokeRect(MARGIN.left + cell.ix * cw, MARGIN.top + cell.iy * ch, cw, ch);
    }
  }, [r, cell, lang, theme, W, H, plotH, nx, ny, values, colour, e, dx, dy]);

  const gradient = useMemo(() => {
    const stops = Array.from(
      { length: 9 },
      (_, i) => `${rgbText(colormap(colour.colormap, i / 8))} ${(i / 8) * 100}%`,
    );
    return `linear-gradient(to right, ${stops.join(", ")})`;
  }, [colour.colormap]);

  const table = useMemo(() => {
    if (!r) return null;
    const n = nx * ny;
    const xs = new Float64Array(n);
    const ys = new Float64Array(n);
    const vs = new Float64Array(n);
    for (let iy = 0; iy < ny; iy++)
      for (let ix = 0; ix < nx; ix++) {
        const k = iy * nx + ix;
        xs[k] = e.x0 + ((ix + 0.5) / nx) * dx;
        ys[k] = e.y1 - ((iy + 0.5) / ny) * dy;
        vs[k] = values[k] ?? Number.NaN;
      }
    return { xs, ys, vs };
  }, [r, nx, ny, e, dx, dy, values]);

  if (!r || !xAxis || !yAxis || !table) return null;
  const info = (c: { ix: number; iy: number }) => {
    const k = c.iy * nx + c.ix;
    const v = values[k];
    return `${xAxis.label[lang]} ${fmt(table.xs[k] as number, lang)} ${xAxis.unit} · ${yAxis.label[lang]} ${fmt(table.ys[k] as number, lang)} ${yAxis.unit} · ${colour.label[lang]} ${v === null || v === undefined ? t("raster.noData") : `${fmt(v, lang)} ${colour.unit}`}`;
  };
  const cellAt = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const sx = W / box.width;
    const sy = H / box.height;
    const ix = Math.floor(((event.clientX - box.left) * sx - MARGIN.left) / (PLOT_W / nx));
    const iy = Math.floor(((event.clientY - box.top) * sy - MARGIN.top) / (plotH / ny));
    return ix >= 0 && ix < nx && iy >= 0 && iy < ny ? { ix, iy } : null;
  };
  const onKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const key = event.key;
    const from = cell ?? { ix: Math.floor(nx / 2), iy: Math.floor(ny / 2) };
    const next = { ...from };
    if (key === "ArrowRight") next.ix = Math.min(nx - 1, from.ix + 1);
    else if (key === "ArrowLeft") next.ix = Math.max(0, from.ix - 1);
    else if (key === "ArrowDown") next.iy = Math.min(ny - 1, from.iy + 1);
    else if (key === "ArrowUp") next.iy = Math.max(0, from.iy - 1);
    else if (key === "Escape") {
      setCell(null);
      return;
    } else return;
    event.preventDefault();
    setCell(cell === null ? from : next);
  };
  const tableId = `${uid}-table`;
  return (
    <div
      ref={root}
      className={styles.panel}
      data-testid="series-raster"
      data-chart-id={doc.id}
      data-colormap={colour.colormap}
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
      <canvas
        ref={canvas}
        className={styles.canvas}
        style={{ aspectRatio: `${W} / ${H}` }}
        role="img"
        aria-label={title}
        onPointerMove={(event) => setCell(cellAt(event))}
        onPointerLeave={() => setCell(null)}
      />
      <p className={styles.help}>
        {xAxis.label[lang]} ({xAxis.unit}){" · "}
        {yAxis.label[lang]} ({yAxis.unit})
      </p>
      <div className={styles.scale} data-testid="colour-scale">
        <span>
          {fmt(colour.vmin, lang)} {colour.unit}
        </span>
        <span className={styles.scaleBar} style={{ background: gradient }} />
        <span>
          {fmt(colour.vmax, lang)} {colour.unit}
        </span>
        <span>
          {colour.label[lang]} ({colour.unit}, {colour.colormap})
        </span>
      </div>
      <p id={`${uid}-help`} className={styles.help}>
        {t("raster.help")}
      </p>
      {cell && (
        <output className={styles.readout} data-testid="readout">
          {info(cell)}
        </output>
      )}
      <div id={tableId} hidden={!open}>
        {open && (
          <DataTable
            label={title}
            x={{ header: `${xAxis.label[lang]} (${xAxis.unit})`, values: table.xs }}
            columns={[
              { id: "y", header: `${yAxis.label[lang]} (${yAxis.unit})`, values: table.ys },
              { id: "value", header: `${colour.label[lang]} (${colour.unit})`, values: table.vs },
            ]}
          />
        )}
      </div>
    </div>
  );
}
