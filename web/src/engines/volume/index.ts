// Engine `volume` (spec 018 section 7.1): survey cut/fill between two DEM epochs inside a polygon, case C2 (spec 017: FR-017-30,
// FR-017-33, FR-017-47, FR-017-48). The sums are exactly rounded (Shewchuk's algorithm, what Python's math.fsum does), so the
// volumes do not depend on the order of the cells. Grid geometry: `origin_m` is the upper-left corner, cell (row, col) has its
// centre at (x0 + (col + 1/2) c, y0 - (row + 1/2) c) (T-018-072, flagged in the report). A null in an array read from JSON is no data.
import { rangeError, schemaError, sizeError } from "../analytical/errors";
import { asArray, asInteger, asNumber, asObject } from "../analytical/validate";

const MAX_SIDE = 2048;
const MAX_VERTICES = 10000;

/** Exactly rounded sum of binary64 values (Shewchuk's partials, as in Python's math.fsum). */
export function fsum(values: Iterable<number>): number {
  const partials: number[] = [];
  for (let x of values) {
    let i = 0;
    for (let j = 0; j < partials.length; j++) {
      let y = partials[j] as number;
      if (Math.abs(x) < Math.abs(y)) [x, y] = [y, x];
      const hi = x + y;
      const lo = y - (hi - x);
      if (lo !== 0) partials[i++] = lo;
      x = hi;
    }
    partials.length = i;
    partials.push(x);
  }
  // sum the partials from the top, stopping at the first exact result; round half to even on the last step
  let n = partials.length;
  let hi = 0;
  if (n > 0) {
    hi = partials[--n] as number;
    let lo = 0;
    while (n > 0) {
      const x = hi;
      const y = partials[--n] as number;
      hi = x + y;
      const yr = hi - x;
      lo = y - yr;
      if (lo !== 0) break;
    }
    if (
      n > 0 &&
      ((lo < 0 && (partials[n - 1] as number) < 0) || (lo > 0 && (partials[n - 1] as number) > 0))
    ) {
      const y = lo * 2;
      const x = hi + y;
      if (y === x - hi) hi = x;
    }
  }
  return hi;
}

export interface CutFillResult {
  fill_m3: number;
  cut_m3: number;
  net_m3: number;
  valid_cells: number;
  nodata_cells: number;
  nodata_fraction: number;
  bound_uncorrelated_m3: number;
  bound_correlated_m3: number;
}

function heights(raw: unknown, name: string, n: number): ArrayLike<number | null> {
  if (raw instanceof Float32Array || raw instanceof Float64Array) {
    if (raw.length !== n) throw schemaError(`${name} holds ${raw.length} heights, rows x cols is ${n}`);
    return raw;
  }
  if (!Array.isArray(raw)) throw schemaError(`${name} must be a height buffer`);
  if (raw.length !== n) throw schemaError(`${name} holds ${raw.length} heights, rows x cols is ${n}`);
  return raw as Array<number | null>;
}

type Point = [number, number];

function orient(a: Point, b: Point, c: Point): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function onSegment(a: Point, b: Point, p: Point): boolean {
  return (
    Math.min(a[0], b[0]) <= p[0] &&
    p[0] <= Math.max(a[0], b[0]) &&
    Math.min(a[1], b[1]) <= p[1] &&
    p[1] <= Math.max(a[1], b[1])
  );
}

function segmentsIntersect(a: Point, b: Point, c: Point, d: Point): boolean {
  const o1 = orient(a, b, c);
  const o2 = orient(a, b, d);
  const o3 = orient(c, d, a);
  const o4 = orient(c, d, b);
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) return true;
  return (
    (o1 === 0 && onSegment(a, b, c)) ||
    (o2 === 0 && onSegment(a, b, d)) ||
    (o3 === 0 && onSegment(c, d, a)) ||
    (o4 === 0 && onSegment(c, d, b))
  );
}

function selfIntersects(poly: Point[]): boolean {
  const n = poly.length;
  for (let i = 0; i < n; i++) {
    const a = poly[i] as Point;
    const b = poly[(i + 1) % n] as Point;
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue;
      if (segmentsIntersect(a, b, poly[j] as Point, poly[(j + 1) % n] as Point)) return true;
    }
  }
  return false;
}

/** Even-odd rule: the crossings of a ray towards +x with the half-open edges. */
function inside(poly: Point[], x: number, y: number): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i] as Point;
    const [xj, yj] = poly[j] as Point;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

export function cut_fill(args: Record<string, unknown>): CutFillResult {
  const a = asObject(args, "args");
  const rowsRaw = a.rows;
  const colsRaw = a.cols;
  for (const [name, v] of [
    ["rows", rowsRaw],
    ["cols", colsRaw],
  ] as const)
    if (typeof v === "number" && Number.isFinite(v) && v > MAX_SIDE)
      throw sizeError(`${name} above the ${MAX_SIDE} cap`);
  const rows = asInteger(rowsRaw, "rows", { lo: 1, hi: MAX_SIDE });
  const cols = asInteger(colsRaw, "cols", { lo: 1, hi: MAX_SIDE });
  const cell = asNumber(a.cell_size_m, "cell_size_m", { lo: 0, loOpen: true });
  const origin = asArray(a.origin_m, "origin_m", 2, 2).map((v, i) => asNumber(v, `origin_m[${i}]`)) as Point;
  const s0 = asNumber(a.rmse_before_m, "rmse_before_m", { lo: 0 });
  const s1 = asNumber(a.rmse_after_m, "rmse_after_m", { lo: 0 });
  const rawPoly = asArray(a.polygon_m, "polygon_m");
  if (rawPoly.length > MAX_VERTICES)
    throw sizeError(`the polygon has ${rawPoly.length} vertices, above ${MAX_VERTICES}`);
  if (rawPoly.length < 3) throw schemaError("the polygon needs at least 3 vertices");
  const poly: Point[] = rawPoly.map((p, i) => {
    const pt = asArray(p, `polygon_m[${i}]`, 2, 2);
    return [asNumber(pt[0], `polygon_m[${i}][0]`), asNumber(pt[1], `polygon_m[${i}][1]`)] as Point;
  });
  const n = rows * cols;
  const before = heights(a.before, "before", n);
  const after = heights(a.after, "after", n);
  if (selfIntersects(poly)) throw rangeError("the polygon intersects itself");
  const fill: number[] = [];
  const cut: number[] = [];
  let nodata = 0;
  let touched = 0;
  for (let r = 0; r < rows; r++) {
    const y = origin[1] - (r + 0.5) * cell;
    for (let c = 0; c < cols; c++) {
      const x = origin[0] + (c + 0.5) * cell;
      if (!inside(poly, x, y)) continue;
      touched++;
      const z0 = before[r * cols + c];
      const z1 = after[r * cols + c];
      if (
        z0 === null ||
        z1 === null ||
        z0 === undefined ||
        z1 === undefined ||
        !Number.isFinite(z0) ||
        !Number.isFinite(z1)
      ) {
        nodata++;
        continue;
      }
      const d = z1 - z0;
      fill.push(Math.max(d, 0));
      cut.push(Math.max(-d, 0));
    }
  }
  if (touched === 0) throw rangeError("the polygon covers no cell of the grid");
  const valid = fill.length;
  if (valid === 0) throw rangeError("no cell of the polygon holds data in both epochs");
  const area = cell * cell;
  const vFill = area * fsum(fill);
  const vCut = area * fsum(cut);
  const sigma = Math.sqrt(s0 * s0 + s1 * s1);
  return {
    fill_m3: vFill,
    cut_m3: vCut,
    net_m3: vFill - vCut,
    valid_cells: valid,
    nodata_cells: nodata,
    nodata_fraction: nodata / (valid + nodata),
    bound_uncorrelated_m3: area * Math.sqrt(valid) * sigma,
    bound_correlated_m3: area * valid * sigma,
  };
}
