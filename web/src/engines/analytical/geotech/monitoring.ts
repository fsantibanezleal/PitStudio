// Inverse velocity (Fukuzono) and the conjugate Bayesian failure band. Port of minephys.geotech._monitoring
// (FR-018-51). The posterior draws use the PCG64 port of T-018-051 and Box-Muller normals.
import { PCG64 } from "../../random/pcg64";
import { SeedSequence } from "../../random/seedSequence";
import { rangeError, schemaError } from "../errors";
import { asArray, asInteger, asNumber, asObject, optional } from "../validate";

const V_MAX = 0.01; // the velocity cap of the engine schema (minephys tripwire, m/s)
const T_LIM = 1e10;

interface Used {
  t: number[];
  y: number[];
}

function parseRecord(raw: unknown, windowRaw: unknown): Used {
  const rec = asArray(raw, "record", 3, 100000);
  const t: number[] = [];
  const v: number[] = [];
  rec.forEach((p, i) => {
    const o = asObject(p, `record[${i}]`);
    t.push(asNumber(o.t_s, `record[${i}].t_s`, { lo: -T_LIM, hi: T_LIM }));
    v.push(asNumber(o.velocity_m_per_s, `record[${i}].velocity_m_per_s`, { lo: 0, loOpen: true, hi: V_MAX }));
  });
  const keep = windowRaw === undefined ? null : asInteger(windowRaw, "window", { lo: 3, hi: 100000 });
  for (let i = 1; i < t.length; i++)
    if (!((t[i] as number) > (t[i - 1] as number)))
      throw rangeError("record times must be strictly increasing");
  const start = keep === null ? 0 : Math.max(0, t.length - keep);
  return { t: t.slice(start), y: v.slice(start).map((x) => 1 / x) };
}

function mean(x: number[]): number {
  let s = 0;
  for (const v of x) s += v;
  return s / x.length;
}

export interface InverseVelocityResult {
  accelerating: boolean;
  failure_time_s?: number;
  slope_per_m: number;
  intercept_s_per_m: number;
  r_squared: number;
  n_used: number;
}

export function inverse_velocity(args: Record<string, unknown>): InverseVelocityResult {
  const a = asObject(args, "args");
  const used = parseRecord(a.record, a.window);
  const n = used.t.length;
  const tMean = mean(used.t);
  const yMean = mean(used.y);
  let sxx = 0;
  let sxy = 0;
  let syy = 0;
  for (let i = 0; i < n; i++) {
    const c = (used.t[i] as number) - tMean;
    const dy = (used.y[i] as number) - yMean;
    sxx += c * c;
    sxy += c * dy;
    syy += dy * dy;
  }
  const slope = sxy / sxx;
  const accelerating = slope < 0;
  const out: InverseVelocityResult = {
    accelerating,
    slope_per_m: slope,
    intercept_s_per_m: yMean - slope * tMean,
    r_squared: syy > 0 ? Math.min(1, (sxy * sxy) / (sxx * syy)) : 0, // rounding can exceed 1 by 4e-16
    n_used: n,
  };
  if (accelerating) out.failure_time_s = tMean - yMean / slope;
  return out;
}

export interface FailureBandResult {
  status: "band" | "no-accelerating-draw";
  median_s?: number;
  lower_s?: number;
  upper_s?: number;
  fraction_not_accelerating: number;
  posterior_mean: number[];
  posterior_cov: number[][];
}

type Mat = [[number, number], [number, number]];
type Vec = [number, number];

function inv2(m: Mat): Mat {
  const det = m[0][0] * m[1][1] - m[0][1] * m[1][0];
  return [
    [m[1][1] / det, -m[0][1] / det],
    [-m[1][0] / det, m[0][0] / det],
  ];
}
const mul2 = (a: Mat, b: Mat): Mat => [
  [a[0][0] * b[0][0] + a[0][1] * b[1][0], a[0][0] * b[0][1] + a[0][1] * b[1][1]],
  [a[1][0] * b[0][0] + a[1][1] * b[1][0], a[1][0] * b[0][1] + a[1][1] * b[1][1]],
];
const tr2 = (a: Mat): Mat => [
  [a[0][0], a[1][0]],
  [a[0][1], a[1][1]],
];
const mv2 = (a: Mat, v: Vec): Vec => [a[0][0] * v[0] + a[0][1] * v[1], a[1][0] * v[0] + a[1][1] * v[1]];

/** Standard normal stream of a PCG64 generator (Box-Muller; the spare of each pair is kept). */
export class NormalStream {
  private spare: number | null = null;
  private readonly gen: PCG64;
  constructor(gen: PCG64) {
    this.gen = gen;
  }
  next(): number {
    if (this.spare !== null) {
      const s = this.spare;
      this.spare = null;
      return s;
    }
    const u1 = 1 - this.gen.random();
    const u2 = this.gen.random();
    const r = Math.sqrt(-2 * Math.log(u1));
    this.spare = r * Math.sin(2 * Math.PI * u2);
    return r * Math.cos(2 * Math.PI * u2);
  }
}

function quantile(sorted: number[], q: number): number {
  const pos = q * (sorted.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.min(lo + 1, sorted.length - 1);
  return (sorted[lo] as number) + ((sorted[hi] as number) - (sorted[lo] as number)) * (pos - lo);
}

function parsePrior(a: Record<string, unknown>): { mu0: Vec; cov0: Mat } | null {
  if (a.prior_mean === undefined && a.prior_cov === undefined) return null;
  if (a.prior_mean === undefined || a.prior_cov === undefined)
    throw schemaError("prior_mean and prior_cov are required together");
  const pm = asArray(a.prior_mean, "prior_mean", 2, 2);
  const mu0: Vec = [asNumber(pm[0], "prior_mean[0]"), asNumber(pm[1], "prior_mean[1]")];
  const pc = asArray(a.prior_cov, "prior_cov", 2, 2).map((r, i) =>
    asArray(r, `prior_cov[${i}]`, 2, 2).map((x, j) => asNumber(x, `prior_cov[${i}][${j}]`)),
  );
  const cov0: Mat = [
    [pc[0]?.[0] as number, pc[0]?.[1] as number],
    [pc[1]?.[0] as number, pc[1]?.[1] as number],
  ];
  const off = Math.max(Math.abs(cov0[0][1]), Math.abs(cov0[1][0]));
  const symmetric = Math.abs(cov0[0][1] - cov0[1][0]) <= 1e-9 * off;
  const det = cov0[0][0] * cov0[1][1] - cov0[0][1] * cov0[1][0];
  if (!symmetric || !(cov0[0][0] > 0) || !(det > 0))
    throw rangeError("prior_cov must be a symmetric positive-definite 2 x 2 matrix");
  return { mu0, cov0 };
}

export function failure_band(args: Record<string, unknown>): FailureBandResult {
  const a = asObject(args, "args");
  const used = parseRecord(a.record, a.window);
  const seed = asInteger(a.seed, "seed", { lo: 0, hi: Number.MAX_SAFE_INTEGER });
  const draws = asInteger(a.n_draws, "n_draws", { lo: 100, hi: 100000 });
  const level = optional(
    a.credible,
    (v) => asNumber(v, "credible", { lo: 0, hi: 1, loOpen: true, hiOpen: true }),
    0.9,
  );
  const given: number | null =
    a.noise_sd_s_per_m === undefined
      ? null
      : asNumber(a.noise_sd_s_per_m, "noise_sd_s_per_m", { lo: 0, loOpen: true, hi: 1e12 });
  const prior = parsePrior(a);
  const n = used.t.length;
  const tMean = mean(used.t);
  const s = used.t.map((x) => x - tMean);
  let sxx = 0;
  for (const v of s) sxx += v * v;
  const y = used.y;
  let sigma = given;
  if (sigma === null) {
    const yMean = mean(y);
    let sxy = 0;
    for (let i = 0; i < n; i++) sxy += (s[i] as number) * ((y[i] as number) - yMean);
    const slope = sxy / sxx;
    let ss = 0;
    for (let i = 0; i < n; i++) {
      const r = (y[i] as number) - yMean - slope * (s[i] as number);
      ss += r * r;
    }
    const variance = ss / (n - 2);
    if (!(variance > 0)) throw rangeError("the residuals are zero: pass noise_sd_s_per_m");
    sigma = Math.sqrt(variance);
  }
  const s2 = sigma * sigma;
  const shift: Mat = [
    [1, tMean],
    [0, 1],
  ];
  let precision: Mat = [
    [n / s2, 0],
    [0, sxx / s2],
  ];
  let sumY = 0;
  let sumSY = 0;
  for (let i = 0; i < n; i++) {
    sumY += y[i] as number;
    sumSY += (s[i] as number) * (y[i] as number);
  }
  let rhs: Vec = [sumY / s2, sumSY / s2];
  if (prior !== null) {
    const pp = inv2(mul2(mul2(shift, prior.cov0), tr2(shift)));
    precision = [
      [precision[0][0] + pp[0][0], precision[0][1] + pp[0][1]],
      [precision[1][0] + pp[1][0], precision[1][1] + pp[1][1]],
    ];
    const add = mv2(pp, mv2(shift, prior.mu0));
    rhs = [rhs[0] + add[0], rhs[1] + add[1]];
  }
  const covC = inv2(precision);
  const meanC = mv2(covC, rhs);
  const back: Mat = [
    [1, -tMean],
    [0, 1],
  ];
  const raw = mul2(mul2(back, covC), tr2(back));
  const off = (raw[0][1] + raw[1][0]) / 2;
  const cov: Mat = [
    [raw[0][0], off],
    [off, raw[1][1]],
  ];
  const meanV = mv2(back, meanC);
  const l00 = Math.sqrt(cov[0][0]);
  const l10 = cov[1][0] / l00;
  const l11 = Math.sqrt(cov[1][1] - l10 * l10);
  const normals = new NormalStream(new PCG64(new SeedSequence(seed)));
  const tf: number[] = [];
  let notAccelerating = 0;
  for (let i = 0; i < draws; i++) {
    const z0 = normals.next();
    const z1 = normals.next();
    const b0 = meanV[0] + l00 * z0;
    const b1 = meanV[1] + l10 * z0 + l11 * z1;
    if (b1 < 0) tf.push(-b0 / b1);
    else notAccelerating += 1;
  }
  const out: FailureBandResult = {
    status: tf.length > 0 ? "band" : "no-accelerating-draw",
    fraction_not_accelerating: notAccelerating / draws,
    posterior_mean: [meanV[0], meanV[1]],
    posterior_cov: [
      [cov[0][0], cov[0][1]],
      [cov[1][0], cov[1][1]],
    ],
  };
  if (tf.length > 0) {
    tf.sort((p, q) => p - q);
    out.lower_s = quantile(tf, (1 - level) / 2);
    out.median_s = quantile(tf, 0.5);
    out.upper_s = quantile(tf, (1 + level) / 2);
  }
  return out;
}
