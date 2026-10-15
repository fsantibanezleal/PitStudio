import { type ReactNode, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useTranslation } from "react-i18next";
import styles from "./chart.module.css";
import { DataTable } from "./DataTable";
import { decimate } from "./decimate";
import { lowerBound, makeSeries, nearestIndex, type Series } from "./series";
import { makeView, pan, type Scale, toData, toScreen, type View, zoomAt } from "./viewTransform";

/** A unit with its conversion to SI (FR-020-07: a source unit is followed by SI in parentheses). */
export interface SiUnit {
  unit: string;
  /** SI value = (value x factor) + offset. */
  factor: number;
  offset?: number;
}

export interface ChartSeries {
  id: string;
  name: string;
  y: ArrayLike<number>;
  unit: string;
  si?: SiUnit;
}

export interface ChartProps {
  id: string;
  title: string;
  x: ArrayLike<number>;
  xName: string;
  xUnit: string;
  xSi?: SiUnit;
  series: ChartSeries[];
  xScale?: Scale;
  yScale?: Scale;
  /** Plot height in CSS pixels. */
  height?: number;
  /** Extra data attributes for the chart element (used by the pages that embed a chart, e.g. the GPU evidence page). */
  attrs?: Record<string, string | number | undefined>;
  /** Content shown inside the chart element after the plot (labels, reference values, popovers). */
  children?: ReactNode;
  /** Text of a missing reading in the data table, instead of the generic one. */
  missingText?: string;
  /** Horizontal reference lines at `y` (in the unit of the first series), drawn dashed with their label. */
  references?: Array<{ id: string; y: number; label: string }>;
  /** Draw the series as bands stacked on each other (the values in the table stay the plain series values). */
  stacked?: boolean;
}

interface ChartData {
  x: Series | null;
  ys: Float64Array[];
  n: number;
}

interface Ranges {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

const MARGIN = { left: 58, right: 12, top: 10, bottom: 30 };
const ZOOM_STEP = 1.25;
const WHEEL_RATE = 0.002;
const MAX_ZOOM = 1e9;
const SERIES_COLORS = ["--chart-1", "--chart-2", "--chart-3", "--chart-4", "--chart-5", "--chart-6"];

function extent(values: ArrayLike<number>, positiveOnly: boolean): [number, number] | null {
  let lo = Number.POSITIVE_INFINITY;
  let hi = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < values.length; i++) {
    const v = values[i] as number;
    if (!Number.isFinite(v) || (positiveOnly && v <= 0)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return hi >= lo ? [lo, hi] : null;
}

/** The initial visible range: the data extent, padded by 5 % (a log axis pads in log space); a flat series gets a unit span. */
/** Running totals over the series, so that each band sits on the previous one; a missing reading leaves a gap in every total above it. */
function cumulative(ys: Float64Array[]): Float64Array[] {
  const out: Float64Array[] = [];
  for (const [k, y] of ys.entries()) {
    const below = out[k - 1];
    out.push(Float64Array.from(y, (v, i) => v + (below ? (below[i] as number) : 0)));
  }
  return out;
}

function paddedRange(lo: number, hi: number, scale: Scale, pad: number): [number, number] {
  if (scale === "log") {
    const a = Math.log(lo);
    const b = Math.log(hi);
    const span = b > a ? b - a : 1;
    return [Math.exp(a - pad * span), Math.exp(b + pad * span)];
  }
  const span = hi > lo ? hi - lo : Math.max(Math.abs(lo), 1);
  return hi > lo ? [lo - pad * span, hi + pad * span] : [lo - span / 2, hi + span / 2];
}

function initialRanges(
  x: Series | null,
  ys: Float64Array[],
  xScale: Scale,
  yScale: Scale,
  refs: readonly number[] = [],
): Ranges {
  const xe = x ? extent(x.x, xScale === "log") : null;
  const ye = [...ys, Float64Array.from(refs)]
    .map((y) => extent(y, yScale === "log"))
    .filter((e): e is [number, number] => e !== null);
  const yLo = ye.length ? Math.min(...ye.map((e) => e[0])) : yScale === "log" ? 1 : 0;
  const yHi = ye.length ? Math.max(...ye.map((e) => e[1])) : yScale === "log" ? 10 : 1;
  const [x0, x1] = xe
    ? xe[0] === xe[1]
      ? paddedRange(xe[0], xe[1], xScale, 0)
      : [xe[0], xe[1]]
    : xScale === "log"
      ? [1, 10]
      : [0, 1];
  const [y0, y1] = paddedRange(yLo, yHi, yScale, 0.05);
  return { x0, x1, y0, y1 };
}

/** Round tick positions covering [lo, hi]: 1, 2, 5 times a power of ten, or whole decades on a log axis. */
function ticks(lo: number, hi: number, scale: Scale, approx: number): number[] {
  const out: number[] = [];
  if (scale === "log") {
    const a = Math.floor(Math.log10(lo));
    const b = Math.ceil(Math.log10(hi));
    for (let e = a; e <= b; e++) {
      const v = 10 ** e;
      if (v >= lo && v <= hi) out.push(v);
    }
    return out;
  }
  const span = hi - lo;
  if (!(span > 0)) return out;
  const rough = span / Math.max(1, approx);
  const mag = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / mag;
  const step = (norm < 1.5 ? 1 : norm < 3.5 ? 2 : norm < 7.5 ? 5 : 10) * mag;
  const start = Math.ceil(lo / step) * step;
  for (let v = start; v <= hi + step * 1e-9 && out.length < 50; v += step)
    out.push(Number(v.toPrecision(12)));
  return out;
}

function fmt(value: number, lang: string): string {
  if (!Number.isFinite(value)) return "";
  return new Intl.NumberFormat(lang, { maximumSignificantDigits: 4, useGrouping: false }).format(value);
}

function toSi(si: SiUnit, value: number): number {
  return value * si.factor + (si.offset ?? 0);
}

function readColors(el: Element): { series: string[]; axis: string; grid: string; text: string } {
  const css = getComputedStyle(el);
  const token = (name: string) => css.getPropertyValue(name).trim();
  return {
    series: SERIES_COLORS.map(token),
    axis: token("--fg-muted"),
    grid: token("--border"),
    text: token("--fg"),
  };
}

type Colors = ReturnType<typeof readColors>;

/** Before the first read the attributes name the tokens themselves (a valid CSS colour), so they are never empty. */
const TOKEN_COLORS = { series: SERIES_COLORS.map((name) => `var(${name})`), axis: "var(--fg-muted)" };

/**
 * An interactive line chart on a canvas: wheel and drag zoom and pan about the cursor, a crosshair read-out that snaps to the
 * nearest sample of the FULL data (arrow keys move it by one sample), a "Show data" table with the units in its headers, colours
 * from the theme tokens (repainted at once on a theme change), and a min/max-per-pixel-column drawing computed on the full data
 * (FR-020-07, -11, -12, -15). A chart holds no WebGL context.
 */
export function Chart(props: ChartProps) {
  const { id, title, xName, xUnit, xSi, series: inputs, height = 260 } = props;
  const xScale = props.xScale ?? "linear";
  const yScale = props.yScale ?? "linear";
  const { t, i18n } = useTranslation("charts");
  const lang = i18n.resolvedLanguage === "es" ? "es" : "en";
  const uid = useId();

  // The full data is copied into typed arrays once per distinct input arrays (their identity, not the identity of `series`).
  const cache = useRef<{ x: ArrayLike<number>; ys: ArrayLike<number>[]; value: ChartData } | null>(null);
  const sameInputs =
    cache.current !== null &&
    cache.current.x === props.x &&
    cache.current.ys.length === inputs.length &&
    inputs.every((s, k) => s.y === cache.current?.ys[k]);
  if (!sameInputs || cache.current === null) {
    let value: ChartData;
    if (props.x.length === 0) {
      value = { x: null, ys: [], n: 0 };
    } else {
      const first = makeSeries(props.x, inputs[0]?.y ?? props.x);
      const plain = inputs.map((s, k) => (k === 0 ? first.y : makeSeries(props.x, s.y).y));
      value = { x: first, ys: props.stacked ? cumulative(plain) : plain, n: first.n };
    }
    cache.current = { x: props.x, ys: inputs.map((s) => s.y), value };
  }
  const data = cache.current.value;

  const refValues = (props.references ?? []).map((r) => r.y).join(",");
  // biome-ignore lint/correctness/useExhaustiveDependencies: refValues is the stable text of the reference values
  const initial = useMemo(
    () =>
      initialRanges(
        data.x,
        data.ys,
        xScale,
        yScale,
        (props.references ?? []).map((r) => r.y),
      ),
    [data, xScale, yScale, refValues],
  );
  const [ranges, setRanges] = useState<Ranges>(initial);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [cursor, setCursor] = useState<number | null>(null);
  const [tableOpen, setTableOpen] = useState(false);
  const [colors, setColors] = useState<Colors | null>(null);
  const frame = useRef<HTMLDivElement | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const plot = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const drag = useRef<{ x: number; y: number; id: number } | null>(null);
  const pointer = useRef<{ x: number; y: number } | null>(null);
  const live = useRef({ ranges, size, cursor });
  live.current = { ranges, size, cursor };

  // A new data set starts from its own extent.
  useEffect(() => {
    setRanges(initial);
    setCursor(null);
  }, [initial]);

  const view = useMemo<View | null>(() => {
    if (size.w <= 0 || size.h <= 0) return null;
    try {
      return makeView({
        x: { min: ranges.x0, max: ranges.x1, scale: xScale },
        y: { min: ranges.y0, max: ranges.y1, scale: yScale },
        width: size.w,
        height: size.h,
      });
    } catch {
      return null;
    }
  }, [ranges, size, xScale, yScale]);

  // Size of the plot area, tracked.
  useLayoutEffect(() => {
    const el = plot.current;
    if (!el) return;
    const measure = () => {
      const r = el.getBoundingClientRect();
      setSize((s) => (s.w === r.width && s.h === r.height ? s : { w: r.width, h: r.height }));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Theme tokens: read now, and again whenever the theme changes (attribute on <html> or the system scheme).
  useLayoutEffect(() => {
    const el = root.current;
    if (!el) return;
    setColors(readColors(el));
    const update = () => flushSync(() => setColors(readColors(el)));
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme", "class"],
    });
    const media = typeof matchMedia === "function" ? matchMedia("(prefers-color-scheme: dark)") : null;
    media?.addEventListener("change", update);
    return () => {
      observer.disconnect();
      media?.removeEventListener("change", update);
    };
  }, []);

  // What is drawn: the slice of the full data inside the visible x range, reduced to min and max per pixel column.
  const drawn = useMemo(() => {
    if (!data.x || !view)
      return { lists: [] as Uint32Array[], i0: 0, count: 0, ymin: Number.NaN, ymax: Number.NaN };
    const i0 = lowerBound(data.x.x, ranges.x0);
    // one past the last index with x <= x1
    let end = i0;
    let hi = data.n;
    while (end < hi) {
      const mid = (end + hi) >>> 1;
      if ((data.x.x[mid] as number) <= ranges.x1) end = mid + 1;
      else hi = mid;
    }
    if (end <= i0)
      return {
        lists: data.ys.map(() => new Uint32Array(0)),
        i0,
        count: 0,
        ymin: Number.NaN,
        ymax: Number.NaN,
      };
    const columns = Math.max(1, Math.ceil(view.width));
    const lists = data.ys.map((y) => decimate(y.subarray(i0, end), columns));
    const main = data.ys[0] as Float64Array;
    let ymin = Number.POSITIVE_INFINITY;
    let ymax = Number.NEGATIVE_INFINITY;
    for (const k of lists[0] ?? []) {
      const v = main[k + i0] as number;
      if (Number.isNaN(v)) continue;
      if (v < ymin) ymin = v;
      if (v > ymax) ymax = v;
    }
    return {
      lists,
      i0,
      count: lists[0]?.length ?? 0,
      ymin: ymax >= ymin ? ymin : Number.NaN,
      ymax: ymax >= ymin ? ymax : Number.NaN,
    };
  }, [data, ranges.x0, ranges.x1, view]);

  // Paint: repaint on any change of what is drawn, of the view, the theme colours or the language.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the dependencies are the inputs of the drawing, read through refs
  useLayoutEffect(() => {
    const cv = canvas.current;
    const fr = frame.current;
    if (!cv || !fr || !view || !colors) return;
    const dpr = typeof devicePixelRatio === "number" && devicePixelRatio > 0 ? devicePixelRatio : 1;
    const w = fr.clientWidth;
    const h = fr.clientHeight;
    if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
    }
    const g = cv.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    g.save();
    g.translate(MARGIN.left, MARGIN.top);
    g.font = "11px system-ui, sans-serif";
    g.lineWidth = 1;
    // grid, ticks and labels
    const xt = ticks(ranges.x0, ranges.x1, xScale, Math.max(2, Math.floor(view.width / 90)));
    const yt = ticks(ranges.y0, ranges.y1, yScale, Math.max(2, Math.floor(view.height / 45)));
    g.strokeStyle = colors.grid;
    g.fillStyle = colors.axis;
    g.textAlign = "center";
    g.textBaseline = "top";
    for (const v of xt) {
      const { px } = toScreen(view, v, ranges.y0);
      g.beginPath();
      g.moveTo(px + 0.5, 0);
      g.lineTo(px + 0.5, view.height);
      g.stroke();
      g.fillText(fmt(v, lang), px, view.height + 4);
    }
    g.textAlign = "right";
    g.textBaseline = "middle";
    for (const v of yt) {
      const { py } = toScreen(view, ranges.x0, v);
      g.beginPath();
      g.moveTo(0, py + 0.5);
      g.lineTo(view.width, py + 0.5);
      g.stroke();
      g.fillText(fmt(v, lang), -6, py);
    }
    g.strokeStyle = colors.axis;
    g.strokeRect(0.5, 0.5, view.width - 1, view.height - 1);
    // series, clipped to the plot
    g.beginPath();
    g.rect(0, 0, view.width, view.height);
    g.clip();
    if (data.x) {
      for (let s = 0; s < data.ys.length; s++) {
        const list = drawn.lists[s];
        const y = data.ys[s] as Float64Array;
        if (!list || list.length === 0) continue;
        g.strokeStyle = colors.series[s % SERIES_COLORS.length] || colors.axis;
        if (props.stacked) {
          const below = s > 0 ? (data.ys[s - 1] as Float64Array) : null;
          g.fillStyle = g.strokeStyle;
          g.globalAlpha = 0.35;
          g.beginPath();
          const up: Array<[number, number]> = [];
          for (const k of list) {
            const idx = k + drawn.i0;
            const yv = y[idx] as number;
            if (!Number.isFinite(yv)) continue;
            up.push([data.x.x[idx] as number, yv]);
          }
          if (up.length > 0) {
            const first0 = toScreen(view, (up[0] as [number, number])[0], (up[0] as [number, number])[1]);
            g.moveTo(first0.px, first0.py);
            for (const [xv, yv] of up) {
              const { px, py } = toScreen(view, xv, yv);
              g.lineTo(px, py);
            }
            for (let u = up.length - 1; u >= 0; u--) {
              const [xv] = up[u] as [number, number];
              const idx = lowerBound(data.x.x, xv);
              const base = below ? (below[idx] as number) : 0;
              const { px, py } = toScreen(view, xv, Number.isFinite(base) ? base : ranges.y0);
              g.lineTo(px, py);
            }
            g.closePath();
            g.fill();
          }
          g.globalAlpha = 1;
        }
        g.lineWidth = 1.5;
        g.beginPath();
        let open = false;
        for (const k of list) {
          const idx = k + drawn.i0;
          const yv = y[idx] as number;
          if (!Number.isFinite(yv) || (yScale === "log" && yv <= 0)) {
            open = false;
            continue;
          }
          const { px, py } = toScreen(view, data.x.x[idx] as number, yv);
          if (open) g.lineTo(px, py);
          else g.moveTo(px, py);
          open = true;
        }
        g.stroke();
        if (list.length === 1 || (data.n <= 200 && list.length === data.n)) {
          g.fillStyle = g.strokeStyle;
          for (const k of list) {
            const idx = k + drawn.i0;
            const yv = y[idx] as number;
            if (!Number.isFinite(yv)) continue;
            const { px, py } = toScreen(view, data.x.x[idx] as number, yv);
            g.fillRect(px - 2, py - 2, 4, 4);
          }
        }
      }
      // reference lines
      for (const ref of props.references ?? []) {
        if (!Number.isFinite(ref.y) || (yScale === "log" && ref.y <= 0)) continue;
        const { py } = toScreen(view, ranges.x0, ref.y);
        g.save();
        g.setLineDash([6, 4]);
        g.strokeStyle = colors.text;
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(0, py + 0.5);
        g.lineTo(view.width, py + 0.5);
        g.stroke();
        g.restore();
        g.fillStyle = colors.text;
        g.textAlign = "right";
        g.textBaseline = "bottom";
        g.fillText(ref.label, view.width - 4, py - 2);
      }
      // crosshair
      const c = live.current.cursor;
      if (c !== null && c >= 0 && c < data.n) {
        const cy = (data.ys[0] as Float64Array)[c] as number;
        const { px, py } = toScreen(view, data.x.x[c] as number, Number.isFinite(cy) ? cy : ranges.y0);
        g.strokeStyle = colors.text;
        g.lineWidth = 1;
        g.beginPath();
        g.moveTo(px + 0.5, 0);
        g.lineTo(px + 0.5, view.height);
        g.stroke();
        if (Number.isFinite(cy)) {
          g.fillStyle = colors.text;
          g.fillRect(px - 3, py - 3, 6, 6);
        }
      }
    }
    g.restore();
  }, [view, drawn, colors, cursor, data, ranges, xScale, yScale, lang]);

  // Wheel needs a non-passive listener to stop the page scrolling.
  useEffect(() => {
    const el = plot.current;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      const { size: s } = live.current;
      if (s.w <= 0 || s.h <= 0) return;
      event.preventDefault();
      const r = el.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * WHEEL_RATE);
      if (!Number.isFinite(factor) || factor <= 0) return;
      // A wheel event reports whole pixels; the last pointer move has the exact position when it is the same pixel.
      const last = pointer.current;
      const exact =
        last !== null && Math.abs(last.x - event.clientX) < 1 && Math.abs(last.y - event.clientY) < 1;
      const cx = exact ? last.x : event.clientX;
      const cy = exact ? last.y : event.clientY;
      flushSync(() => zoomBy(factor, cx - r.left, cy - r.top));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  const currentView = (): View | null => {
    const { ranges: r, size: s } = live.current;
    if (s.w <= 0 || s.h <= 0) return null;
    try {
      return makeView({
        x: { min: r.x0, max: r.x1, scale: xScale },
        y: { min: r.y0, max: r.y1, scale: yScale },
        width: s.w,
        height: s.h,
      });
    } catch {
      return null;
    }
  };

  const apply = (v: View) => {
    const next = { x0: v.x.min, x1: v.x.max, y0: v.y.min, y1: v.y.max };
    if (![next.x0, next.x1, next.y0, next.y1].every(Number.isFinite)) return;
    if (!(next.x1 > next.x0) || !(next.y1 > next.y0)) return;
    const ix = initial.x1 - initial.x0;
    const iy = initial.y1 - initial.y0;
    if (xScale === "linear" && (next.x1 - next.x0) * MAX_ZOOM < ix) return;
    if (yScale === "linear" && (next.y1 - next.y0) * MAX_ZOOM < iy) return;
    setRanges(next);
  };

  function zoomBy(factor: number, px: number, py: number) {
    const v = currentView();
    if (v) apply(zoomAt(v, factor, px, py));
  }

  const reset = () => setRanges(initial);

  const indexAt = (px: number): number | null => {
    const v = currentView();
    if (!v || !data.x) return null;
    return nearestIndex(data.x, toData(v, px, 0).x);
  };

  const keepVisible = (index: number) => {
    const v = currentView();
    if (!v || !data.x) return;
    const x = data.x.x[index] as number;
    if (x >= v.x.min && x <= v.x.max) return;
    const { px } = toScreen(v, x, v.y.min);
    apply(pan(v, v.width / 2 - px, 0));
  };

  const move = (to: number) => {
    if (!data.x) return;
    const next = Math.max(0, Math.min(data.n - 1, to));
    flushSync(() => {
      setCursor(next);
      keepVisible(next);
    });
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const v = currentView();
    const c = live.current.cursor;
    const key = event.key;
    if (key === "+" || key === "=") {
      if (v) flushSync(() => zoomBy(ZOOM_STEP, v.width / 2, v.height / 2));
    } else if (key === "-" || key === "_") {
      if (v) flushSync(() => zoomBy(1 / ZOOM_STEP, v.width / 2, v.height / 2));
    } else if (key === "0") {
      flushSync(reset);
    } else if (key === "Home") {
      move(0);
    } else if (key === "End") {
      move(data.n - 1);
    } else if (key.startsWith("Arrow")) {
      if (event.shiftKey) {
        if (!v) return;
        const dx = key === "ArrowRight" ? -0.1 * v.width : key === "ArrowLeft" ? 0.1 * v.width : 0;
        const dy = key === "ArrowUp" ? 0.1 * v.height : key === "ArrowDown" ? -0.1 * v.height : 0;
        flushSync(() => apply(pan(v, dx, dy)));
      } else if (key === "ArrowRight") {
        move((c ?? 0) + 1);
      } else if (key === "ArrowLeft") {
        move((c ?? 0) - 1);
      } else {
        return;
      }
    } else {
      return;
    }
    event.preventDefault();
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    drag.current = { x: event.clientX, y: event.clientY, id: event.pointerId };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    root.current?.focus({ preventScroll: true });
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const r = event.currentTarget.getBoundingClientRect();
    pointer.current = { x: event.clientX, y: event.clientY };
    const d = drag.current;
    if (d && d.id === event.pointerId) {
      const v = currentView();
      if (!v) return;
      const dx = event.clientX - d.x;
      const dy = event.clientY - d.y;
      drag.current = { x: event.clientX, y: event.clientY, id: d.id };
      flushSync(() => apply(pan(v, dx, dy)));
      return;
    }
    const index = indexAt(event.clientX - r.left);
    if (index !== null) flushSync(() => setCursor(index));
  };

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (drag.current?.id === event.pointerId) {
      drag.current = null;
      event.currentTarget.releasePointerCapture?.(event.pointerId);
    }
  };

  // Read-out of the sample under the crosshair.
  const first = inputs[0];
  const readout = (() => {
    if (cursor === null || !data.x || !first || cursor >= data.n) return null;
    const x = data.x.x[cursor] as number;
    const y = (data.ys[0] as Float64Array)[cursor] as number;
    const withSi = (value: number, unit: string, si?: SiUnit) =>
      si && si.unit !== unit
        ? `${fmt(value, lang)} ${unit} (${fmt(toSi(si, value), lang)} ${si.unit})`
        : `${fmt(value, lang)} ${unit}`;
    const xText = withSi(x, xUnit, xSi);
    const yText = Number.isFinite(y) ? withSi(y, first.unit, first.si) : t("notAvailable");
    return { x, y, text: `${xName} ${xText} · ${first.name} ${yText}` };
  })();

  const tableColumns = inputs.map((s) => ({ id: s.id, header: `${s.name} (${s.unit})`, values: s.y }));
  const tableId = `${uid}-table`;

  return (
    <div
      ref={root}
      className={styles.chart}
      data-testid="chart"
      data-chart-id={id}
      data-n={data.n}
      data-drawn={drawn.count}
      data-drawn-ymin={Number.isFinite(drawn.ymin) ? String(drawn.ymin) : undefined}
      data-drawn-ymax={Number.isFinite(drawn.ymax) ? String(drawn.ymax) : undefined}
      data-view-x0={String(ranges.x0)}
      data-view-x1={String(ranges.x1)}
      data-view-y0={String(ranges.y0)}
      data-view-y1={String(ranges.y1)}
      data-series-color={colors?.series[0] || TOKEN_COLORS.series[0]}
      data-axis-color={colors?.axis || TOKEN_COLORS.axis}
      {...props.attrs}
      role="application"
      aria-label={title}
      aria-describedby={`${uid}-help`}
      // biome-ignore lint/a11y/noNoninteractiveTabindex: the chart is a custom widget with a documented keyboard model (FR-020-11)
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      <div className={styles.head}>
        <strong className={styles.title}>{title}</strong>
        <span className={styles.tools}>
          <button type="button" className={styles.button} onClick={() => flushSync(reset)}>
            {t("reset")}
          </button>
          <button
            type="button"
            className={styles.button}
            aria-expanded={tableOpen}
            aria-controls={tableId}
            onClick={() => setTableOpen((open) => !open)}
          >
            {tableOpen ? t("hideData") : t("showData")}
          </button>
        </span>
      </div>
      <div ref={frame} className={styles.frame} style={{ height: height + MARGIN.top + MARGIN.bottom }}>
        <canvas ref={canvas} className={styles.canvas} role="img" aria-label={title} />
        {/* biome-ignore lint/a11y/noStaticElementInteractions: a pointer-only surface; the keyboard model is on the focusable chart */}
        <div
          ref={plot}
          data-testid="chart-plot"
          className={styles.plot}
          style={{ left: MARGIN.left, top: MARGIN.top, right: MARGIN.right, bottom: MARGIN.bottom }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerLeave={() => {
            if (!drag.current && document.activeElement !== root.current) setCursor(null);
          }}
          onDoubleClick={() => flushSync(reset)}
        />
      </div>
      <p className={styles.axes}>
        {xName} ({xUnit})
        {inputs.map((s) => (
          <span key={s.id} className={styles.legend}>
            {" · "}
            {s.name} ({s.unit})
          </span>
        ))}
      </p>
      <p id={`${uid}-help`} className={styles.help}>
        {t("help")}
      </p>
      {readout && (
        <output
          data-testid="readout"
          data-x={String(readout.x)}
          data-y={String(readout.y)}
          className={styles.readout}
        >
          {readout.text}
        </output>
      )}
      <div id={tableId} hidden={!tableOpen}>
        {tableOpen && (
          <DataTable
            label={title}
            x={{ header: `${xName} (${xUnit})`, values: props.x }}
            columns={tableColumns}
            missingText={props.missingText}
          />
        )}
      </div>
      {props.children}
    </div>
  );
}
