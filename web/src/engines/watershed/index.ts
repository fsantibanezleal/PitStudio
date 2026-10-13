// Engine `watershed` (spec 018 section 7.1): the marker-controlled watershed of the spec 012 baseline with the fragment sizes x50 and x80
// (case D1). The flooding follows scikit-image's `watershed` (priority queue on (elevation, age), the label of a pixel is the label of the
// neighbour that queued it first). The PSD is FR-012-24 and FR-012-26: equivalent-circle sizes of the instances, area-weighted passing,
// a Swebrec fit by bounded least squares, x80 by the inverse of the fitted curve.
import { rangeError, schemaError, sizeError } from "../analytical/errors";
import { asInteger, asNumber, asObject } from "../analytical/validate";

const MAX_SIDE = 1024;
const MIN_SIDE = 16;

export interface Segmentation {
  labels: Int32Array;
  instance_count: number;
  status: "fit" | "no-fit";
  x50_m?: number;
  x80_m?: number;
}

/** Binary min-heap on (value, age) with the sift rules of scikit-image's watershed heap. */
class Heap {
  private readonly value: Float64Array;
  private readonly age: Float64Array;
  private readonly index: Int32Array;
  size = 0;

  constructor(capacity: number) {
    this.value = new Float64Array(capacity);
    this.age = new Float64Array(capacity);
    this.index = new Int32Array(capacity);
  }

  private smaller(v1: number, a1: number, v2: number, a2: number): boolean {
    return v1 < v2 || (v1 === v2 && a1 < a2);
  }

  push(v: number, a: number, i: number): void {
    let child = this.size++;
    while (child > 0) {
      const parent = (child - 1) >> 1;
      if (!this.smaller(v, a, this.value[parent] as number, this.age[parent] as number)) break;
      this.value[child] = this.value[parent] as number;
      this.age[child] = this.age[parent] as number;
      this.index[child] = this.index[parent] as number;
      child = parent;
    }
    this.value[child] = v;
    this.age[child] = a;
    this.index[child] = i;
  }

  /** Index of the smallest element, which is removed. */
  pop(): number {
    const top = this.index[0] as number;
    this.size--;
    if (this.size > 0) {
      const v = this.value[this.size] as number;
      const a = this.age[this.size] as number;
      const i = this.index[this.size] as number;
      let parent = 0;
      for (;;) {
        let child = 2 * parent + 1;
        if (child >= this.size) break;
        if (
          child + 1 < this.size &&
          this.smaller(
            this.value[child + 1] as number,
            this.age[child + 1] as number,
            this.value[child] as number,
            this.age[child] as number,
          )
        )
          child++;
        if (!this.smaller(this.value[child] as number, this.age[child] as number, v, a)) break;
        this.value[parent] = this.value[child] as number;
        this.age[parent] = this.age[child] as number;
        this.index[parent] = this.index[child] as number;
        parent = child;
      }
      this.value[parent] = v;
      this.age[parent] = a;
      this.index[parent] = i;
    }
    return top;
  }
}

const OFFSETS: Record<1 | 2, Array<[number, number]>> = {
  1: [
    [-1, 0],
    [0, -1],
    [0, 1],
    [1, 0],
  ],
  2: [
    [-1, -1],
    [-1, 0],
    [-1, 1],
    [0, -1],
    [0, 1],
    [1, -1],
    [1, 0],
    [1, 1],
  ],
};

function flood(
  elevation: Float32Array,
  markers: Int32Array,
  mask: Uint8Array | null,
  rows: number,
  cols: number,
  connectivity: 1 | 2,
): Int32Array {
  const n = rows * cols;
  const out = new Int32Array(n);
  const heap = new Heap(n);
  for (let i = 0; i < n; i++) {
    const m = markers[i] as number;
    if (m !== 0 && (mask === null || mask[i] !== 0)) {
      out[i] = m;
      heap.push(elevation[i] as number, 0, i);
    }
  }
  const offs = OFFSETS[connectivity];
  let age = 1;
  while (heap.size > 0) {
    const i = heap.pop();
    const r = Math.floor(i / cols);
    const c = i - r * cols;
    const label = out[i] as number;
    for (const [dr, dc] of offs) {
      const rr = r + dr;
      const cc = c + dc;
      if (rr < 0 || rr >= rows || cc < 0 || cc >= cols) continue;
      const j = rr * cols + cc;
      if (mask !== null && mask[j] === 0) continue;
      if (out[j] !== 0) continue;
      age += 1;
      out[j] = label;
      heap.push(elevation[j] as number, age, j);
    }
  }
  return out;
}

// --- PSD of the instances: FR-012-24 and FR-012-26 ---------------------------------------------------------------------------------

function swebrec(x: number, x50: number, xmax: number, b: number): number {
  const r = Math.log(xmax / x) / Math.log(xmax / x50);
  return 1 / (1 + r ** b);
}

interface Fit {
  x50: number;
  b: number;
}

/** Bounded Levenberg-Marquardt on the sum of squares of S(x_j) - P_j over the points below x_max. */
function fitSwebrec(x: number[], p: number[], start: Fit): Fit | null {
  const n = x.length - 1;
  const xmax = x[n] as number;
  const lo = [1e-6 * xmax, 0.05];
  const hi = [(1 - 1e-6) * xmax, 50];
  const clamp = (v: number, k: 0 | 1) => Math.min(Math.max(v, lo[k] as number), hi[k] as number);
  let x50 = clamp(start.x50, 0);
  let b = clamp(start.b, 1);
  const cost = (a: number, bb: number) => {
    let s = 0;
    for (let j = 0; j < n; j++) {
      const d = swebrec(x[j] as number, a, xmax, bb) - (p[j] as number);
      s += d * d;
    }
    return s;
  };
  let f = cost(x50, b);
  let lambda = 1e-3;
  for (let iteration = 0; iteration < 500; iteration++) {
    let jtj00 = 0;
    let jtj01 = 0;
    let jtj11 = 0;
    let g0 = 0;
    let g1 = 0;
    const lxmax50 = Math.log(xmax / x50);
    for (let j = 0; j < n; j++) {
      const xj = x[j] as number;
      const r = Math.log(xmax / xj) / lxmax50;
      const u = r ** b;
      const s = 1 / (1 + u);
      const res = s - (p[j] as number);
      const d50 = (-s * s * b * u) / (x50 * lxmax50);
      const db = -s * s * u * Math.log(r);
      jtj00 += d50 * d50;
      jtj01 += d50 * db;
      jtj11 += db * db;
      g0 += d50 * res;
      g1 += db * res;
    }
    if (Math.max(Math.abs(g0 * x50), Math.abs(g1 * b)) < 1e-15 * Math.max(f, 1e-300)) break;
    let moved = false;
    for (let attempt = 0; attempt < 60 && !moved; attempt++) {
      const m00 = jtj00 * (1 + lambda) + 1e-300;
      const m11 = jtj11 * (1 + lambda) + 1e-300;
      const det = m00 * m11 - jtj01 * jtj01;
      if (det > 0) {
        const d0 = (-g0 * m11 + g1 * jtj01) / det;
        const d1 = (g0 * jtj01 - g1 * m00) / det;
        const nx = clamp(x50 + d0, 0);
        const nb = clamp(b + d1, 1);
        const nf = cost(nx, nb);
        if (nf <= f) {
          const rel = Math.max(Math.abs(nx - x50) / x50, Math.abs(nb - b) / b);
          x50 = nx;
          b = nb;
          const done = rel < 1e-15;
          f = nf;
          lambda = Math.max(lambda / 10, 1e-15);
          moved = true;
          if (done && iteration > 3) return { x50, b };
        }
      }
      if (!moved) lambda *= 10;
    }
    if (!moved) break;
  }
  return Number.isFinite(x50) && Number.isFinite(b) ? { x50, b } : null;
}

function areasOf(labels: Int32Array): Map<number, number> {
  const areas = new Map<number, number>();
  for (let i = 0; i < labels.length; i++) {
    const l = labels[i] as number;
    if (l !== 0) areas.set(l, (areas.get(l) ?? 0) + 1);
  }
  return areas;
}

function psd(labels: Int32Array, minArea: number, pixelSize: number): { x50: number; x80: number } | null {
  const areas = new Map<number, number>();
  for (let i = 0; i < labels.length; i++) {
    const l = labels[i] as number;
    if (l !== 0) areas.set(l, (areas.get(l) ?? 0) + 1);
  }
  const bySize = new Map<number, number>();
  let total = 0;
  for (const area of areas.values()) {
    if (area < minArea) continue;
    const d = 2 * Math.sqrt(area / Math.PI);
    bySize.set(d, (bySize.get(d) ?? 0) + area);
    total += area;
  }
  const sizes = [...bySize.keys()].sort((a, b) => a - b);
  if (!(total > 0)) return null;
  if (sizes.length < 3) {
    // fewer than three distinct sizes: the curve is a step, x50 and x80 are the sizes at which it reaches 0.5 and 0.8
    let run = 0;
    let x50 = 0;
    let x80 = 0;
    for (const sz of sizes) {
      run += (bySize.get(sz) as number) / total;
      if (x50 === 0 && run >= 0.5) x50 = sz * pixelSize;
      if (x80 === 0 && run >= 0.8) x80 = sz * pixelSize;
    }
    return { x50, x80 };
  }
  const px: number[] = [];
  const pp: number[] = [];
  let run = 0;
  for (const s of sizes) {
    run += bySize.get(s) as number;
    px.push(s * pixelSize);
    pp.push(run / total);
  }
  const xmax = px[px.length - 1] as number;
  let median = xmax;
  for (let j = 0; j < px.length; j++)
    if ((pp[j] as number) >= 0.5) {
      median = px[j] as number;
      break;
    }
  const fit = fitSwebrec(px, pp, { x50: median, b: 2 });
  if (fit === null) return null;
  const x80 = xmax * (fit.x50 / xmax) ** (((1 - 0.8) / 0.8) ** (1 / fit.b));
  return Number.isFinite(x80) && x80 > 0 && fit.x50 > 0 ? { x50: fit.x50, x80 } : null;
}

export function segment(args: Record<string, unknown>): Segmentation {
  const a = asObject(args, "args");
  for (const [name, v] of [
    ["rows", a.rows],
    ["cols", a.cols],
  ] as const)
    if (typeof v === "number" && Number.isFinite(v) && v > MAX_SIDE)
      throw sizeError(`${name} above the ${MAX_SIDE} cap`);
  const rows = asInteger(a.rows, "rows", { lo: MIN_SIDE, hi: MAX_SIDE });
  const cols = asInteger(a.cols, "cols", { lo: MIN_SIDE, hi: MAX_SIDE });
  const n = rows * cols;
  const connectivity = a.connectivity === undefined ? 1 : a.connectivity;
  if (connectivity !== 1 && connectivity !== 2) throw schemaError("connectivity must be 1 or 2");
  const minArea =
    a.min_area_px === undefined ? 4 : asInteger(a.min_area_px, "min_area_px", { lo: 1, hi: 1024 });
  const pixelSize = asNumber(a.pixel_size_m, "pixel_size_m", { lo: 0, loOpen: true });
  const elevation = toTyped(a.elevation, Float32Array, "elevation", n);
  const markers = toTyped(a.markers, Int32Array, "markers", n);
  const mask = a.mask === undefined ? null : toTyped(a.mask, Uint8Array, "mask", n);
  for (let i = 0; i < n; i++) {
    if (!Number.isFinite(elevation[i] as number)) throw rangeError(`elevation[${i}] is not finite`);
    if ((markers[i] as number) < 0) throw rangeError(`markers[${i}] is negative`);
  }
  const labels = flood(elevation, markers, mask, rows, cols, connectivity);
  const distinct = new Set<number>();
  for (let i = 0; i < n; i++) if (labels[i] !== 0) distinct.add(labels[i] as number);
  const kept = [...areasOf(labels).values()].filter((a) => a >= minArea).length;
  const fit = kept < 3 ? null : psd(labels, minArea, pixelSize);
  if (fit === null) return { labels, instance_count: distinct.size, status: "no-fit" };
  return { labels, instance_count: distinct.size, status: "fit", x50_m: fit.x50, x80_m: fit.x80 };
}

type TypedCtor<T> = { new (a: ArrayLike<number>): T; name: string };

function toTyped<T extends Float32Array | Int32Array | Uint8Array>(
  value: unknown,
  ctor: TypedCtor<T>,
  name: string,
  n: number,
): T {
  let out: T;
  if (value instanceof ctor) out = value;
  else if (Array.isArray(value)) out = new ctor(value.map((v) => (v === null ? Number.NaN : (v as number))));
  else if (ArrayBuffer.isView(value)) out = new ctor(value as unknown as ArrayLike<number>);
  else throw schemaError(`${name} must be a ${ctor.name}`);
  if (out.length !== n) throw schemaError(`${name} holds ${out.length} values, rows x cols is ${n}`);
  return out;
}
