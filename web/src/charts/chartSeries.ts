// The reader side of the chart-series contract (DC-020-05, contracts/chart-series.schema.json). A published chart file is
// untrusted data: `readChartSeries` accepts it only when it satisfies the contract and the rules a schema cannot state (equal
// lengths, order of x, cells of a raster, width of a table row), and returns null otherwise: an invalid file is nothing
// published (FR-020-55, ADR-0040). The corpus of the contract (specs/020-web-knowledge/contracts/examples) is its test oracle.
import type { ChartSeries as ChartDoc } from "~/contracts/generated/chart-series";

export type { ChartDoc };

type Rec = Record<string, unknown>;

const CASES = new Set(["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"]);
const TYPES = new Set(["line", "bar", "scatter", "ecdf", "raster", "section", "table"]);
const COLORMAPS = new Set(["viridis", "cividis", "inferno", "magma"]);
const SLUG = /^[a-z0-9][a-z0-9-]{0,63}$/;
const TOOL = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const VERSION = /^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$/;
const KPI = /^[a-z][a-z0-9_]{0,63}$/;
const SERVES = /^(FR|NFR|SC|DC)-[0-9]{3}-[0-9]{2,3}$/;
const MAX_POINTS = 20000;

const isRec = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const numOrNull = (v: unknown): v is number | null => v === null || num(v);
const text = (v: unknown, max: number): v is string =>
  typeof v === "string" && v.length >= 1 && v.length <= max;
const slug = (v: unknown): v is string => typeof v === "string" && SLUG.test(v);
const only = (o: Rec, keys: readonly string[]) => Object.keys(o).every((k) => keys.includes(k));
const list = (v: unknown, min: number, max: number): v is unknown[] =>
  Array.isArray(v) && v.length >= min && v.length <= max;

function nameEnEs(v: unknown): boolean {
  return isRec(v) && only(v, ["en", "es"]) && text(v.en, 200) && text(v.es, 200);
}

function axis(v: unknown): boolean {
  return (
    isRec(v) &&
    only(v, ["label", "unit", "scale"]) &&
    nameEnEs(v.label) &&
    text(v.unit, 32) &&
    (v.scale === undefined || v.scale === "linear" || v.scale === "log")
  );
}

const numbers = (v: unknown, nullable: boolean): v is Array<number | null> =>
  list(v, 1, MAX_POINTS) && v.every(nullable ? numOrNull : num);

function series(v: unknown, chart: string): boolean {
  if (!isRec(v) || !only(v, ["id", "label", "unit", "draw", "n", "x", "y", "lo", "hi", "band_label"]))
    return false;
  if (!slug(v.id) || !nameEnEs(v.label) || !numbers(v.y, true)) return false;
  if (v.unit !== undefined && !text(v.unit, 32)) return false;
  if (v.draw !== undefined && v.draw !== "line" && v.draw !== "step" && v.draw !== "points") return false;
  if (v.n !== undefined && !(Number.isInteger(v.n) && (v.n as number) >= 1)) return false;
  const n = v.y.length;
  if (chart === "bar") {
    if (v.x !== undefined) return false;
  } else {
    if (!numbers(v.x, false) || v.x.length !== n) return false;
    const xs = v.x as number[];
    if ((chart === "line" || chart === "ecdf") && xs.some((x, i) => i > 0 && x < (xs[i - 1] as number)))
      return false;
  }
  if ((v.lo === undefined) !== (v.hi === undefined)) return false;
  if (v.band_label !== undefined && (v.lo === undefined || !nameEnEs(v.band_label))) return false;
  if (v.lo !== undefined) {
    if (!numbers(v.lo, true) || !numbers(v.hi, true) || v.lo.length !== n || v.hi.length !== n) return false;
    for (let i = 0; i < n; i++) {
      const lo = v.lo[i];
      const y = v.y[i];
      const hi = v.hi[i];
      if (typeof lo === "number" && typeof y === "number" && typeof hi === "number" && !(lo <= y && y <= hi))
        return false;
    }
  }
  if (chart === "ecdf") {
    const ys = v.y.filter((y): y is number => y !== null);
    if (ys.some((y, i) => y < 0 || y > 1 || (i > 0 && y < (ys[i - 1] as number)))) return false;
  }
  return true;
}

function marker(v: unknown): boolean {
  if (!isRec(v) || !only(v, ["id", "label", "value_text", "orientation", "x", "y"])) return false;
  if (!slug(v.id) || !nameEnEs(v.label) || !text(v.value_text, 60)) return false;
  const o = v.orientation;
  if (o !== "vertical" && o !== "horizontal" && o !== "point") return false;
  if (v.x !== undefined && !num(v.x)) return false;
  if (v.y !== undefined && !num(v.y)) return false;
  if ((o === "vertical" || o === "point") && v.x === undefined) return false;
  return !((o === "horizontal" || o === "point") && v.y === undefined);
}

function raster(v: unknown): boolean {
  if (!isRec(v) || !only(v, ["nx", "ny", "extent", "values", "colour"])) return false;
  const { nx, ny } = v;
  if (!(Number.isInteger(nx) && Number.isInteger(ny))) return false;
  const [w, h] = [nx as number, ny as number];
  if (w < 2 || h < 2 || w > 200 || h > 200) return false;
  const e = v.extent;
  if (!isRec(e) || !only(e, ["x0", "x1", "y0", "y1"]) || !(num(e.x0) && num(e.x1) && num(e.y0) && num(e.y1)))
    return false;
  if (!(e.x1 > e.x0 && e.y1 > e.y0)) return false;
  if (!list(v.values, 4, 40000) || v.values.length !== w * h || !v.values.every(numOrNull)) return false;
  const c = v.colour;
  return (
    isRec(c) &&
    only(c, ["colormap", "vmin", "vmax", "unit", "label"]) &&
    typeof c.colormap === "string" &&
    COLORMAPS.has(c.colormap) &&
    num(c.vmin) &&
    num(c.vmax) &&
    c.vmax > c.vmin &&
    text(c.unit, 32) &&
    nameEnEs(c.label)
  );
}

function section(v: unknown): boolean {
  if (!isRec(v) || !only(v, ["polylines", "circles"]) || !list(v.polylines, 1, 64)) return false;
  const roles = ["ground", "bench", "shell", "water", "other"];
  const lines = v.polylines.every(
    (p) =>
      isRec(p) &&
      only(p, ["id", "label", "role", "points"]) &&
      slug(p.id) &&
      nameEnEs(p.label) &&
      (p.role === undefined || (typeof p.role === "string" && roles.includes(p.role))) &&
      list(p.points, 2, 5000) &&
      p.points.every((q) => Array.isArray(q) && q.length === 2 && q.every(num)),
  );
  if (!lines) return false;
  if (v.circles === undefined) return true;
  return (
    list(v.circles, 0, 64) &&
    v.circles.every(
      (c) =>
        isRec(c) &&
        only(c, ["id", "label", "role", "cx", "cy", "r"]) &&
        slug(c.id) &&
        nameEnEs(c.label) &&
        (c.role === undefined || c.role === "critical" || c.role === "other") &&
        num(c.cx) &&
        num(c.cy) &&
        num(c.r) &&
        c.r > 0,
    )
  );
}

function table(v: unknown): boolean {
  if (!isRec(v) || !only(v, ["columns", "rows"]) || !list(v.columns, 1, 24) || !list(v.rows, 1, 200))
    return false;
  const cols = v.columns;
  const ok = cols.every(
    (c) =>
      isRec(c) &&
      only(c, ["id", "label", "type", "unit"]) &&
      slug(c.id) &&
      nameEnEs(c.label) &&
      (c.type === "number" || c.type === "text") &&
      (c.unit === undefined || text(c.unit, 32)) &&
      (c.type !== "number" || c.unit !== undefined),
  );
  if (!ok) return false;
  return v.rows.every(
    (row) =>
      Array.isArray(row) &&
      row.length === cols.length &&
      row.every((cell, k) => {
        if (cell === null) return true;
        return (cols[k] as Rec).type === "number"
          ? num(cell)
          : typeof cell === "string" && cell.length <= 200;
      }),
  );
}

const KEYS = [
  "schema_version",
  "kind",
  "id",
  "case",
  "chart_type",
  "kpi",
  "status",
  "title",
  "caption",
  "producer",
  "serves",
  "not_run_reason",
  "x_axis",
  "y_axis",
  "categories",
  "series",
  "markers",
  "raster",
  "section",
  "table",
];

/** The chart of a published file, or null when the file is not a chart series of the contract (never a partial chart). */
export function readChartSeries(raw: unknown): ChartDoc | null {
  if (!isRec(raw) || !only(raw, KEYS)) return null;
  if (raw.schema_version !== "1.0" || raw.kind !== "chart-series" || !slug(raw.id)) return null;
  if (typeof raw.case !== "string" || !CASES.has(raw.case)) return null;
  const type = raw.chart_type;
  if (typeof type !== "string" || !TYPES.has(type)) return null;
  if (raw.status !== "ok" && raw.status !== "not-run") return null;
  if (raw.kpi !== undefined && !(typeof raw.kpi === "string" && KPI.test(raw.kpi))) return null;
  if (!nameEnEs(raw.title) || (raw.caption !== undefined && !nameEnEs(raw.caption))) return null;
  const p = raw.producer;
  if (
    !(
      isRec(p) &&
      only(p, ["tool", "method", "version", "label"]) &&
      typeof p.tool === "string" &&
      TOOL.test(p.tool) &&
      text(p.method, 160) &&
      typeof p.version === "string" &&
      VERSION.test(p.version) &&
      text(p.label, 200)
    )
  )
    return null;
  const s = raw.serves;
  if (
    !list(s, 1, 8) ||
    !s.every((x) => typeof x === "string" && SERVES.test(x)) ||
    new Set(s).size !== s.length
  )
    return null;
  const data = ["series", "categories", "raster", "section", "table"] as const;
  if (raw.status === "not-run") {
    if (!nameEnEs(raw.not_run_reason) || data.some((k) => raw[k] !== undefined)) return null;
    return raw as unknown as ChartDoc;
  }
  if (raw.not_run_reason !== undefined) return null;
  for (const k of ["x_axis", "y_axis"] as const) if (raw[k] !== undefined && !axis(raw[k])) return null;
  if (raw.markers !== undefined && !(list(raw.markers, 0, 24) && raw.markers.every(marker))) return null;
  if (raw.categories !== undefined) {
    const c = raw.categories;
    if (
      !list(c, 1, 64) ||
      !c.every((x) => isRec(x) && only(x, ["id", "label"]) && slug(x.id) && nameEnEs(x.label))
    )
      return null;
  }
  if (raw.series !== undefined && !(list(raw.series, 1, 12) && raw.series.every((x) => series(x, type))))
    return null;
  if (raw.raster !== undefined && !raster(raw.raster)) return null;
  if (raw.section !== undefined && !section(raw.section)) return null;
  if (raw.table !== undefined && !table(raw.table)) return null;
  const has = (k: string) => raw[k] !== undefined;
  const need: Record<string, string[]> = {
    line: ["x_axis", "y_axis", "series"],
    scatter: ["x_axis", "y_axis", "series"],
    ecdf: ["x_axis", "y_axis", "series"],
    bar: ["y_axis", "categories", "series"],
    raster: ["x_axis", "y_axis", "raster"],
    section: ["x_axis", "y_axis", "section"],
    table: ["table"],
  };
  if (!(need[type] as string[]).every(has)) return null;
  const extra: Record<string, string[]> = {
    line: ["categories"],
    scatter: ["categories"],
    ecdf: ["categories"],
    bar: [],
    raster: ["series", "section", "table"],
    section: ["series", "raster", "table"],
    table: ["series", "raster", "section"],
  };
  if ((extra[type] as string[]).some(has)) return null;
  if (type === "bar") {
    const n = (raw.categories as unknown[]).length;
    if ((raw.series as Array<{ y: unknown[] }>).some((x) => x.y.length !== n)) return null;
  }
  return raw as unknown as ChartDoc;
}
