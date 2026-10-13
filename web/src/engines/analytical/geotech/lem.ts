// Limit equilibrium of a fixed slip surface on slice data: Bishop's simplified method and Spencer's method. Port of
// minephys.geotech._lem (FR-018-51; the iterations are those of the reference, so the counts agree).
import { AnalyticalError, rangeError, runtimeError } from "../errors";
import { asArray, asInteger, asNumber, asObject, optional } from "../validate";

export const HALF_PI = Math.PI / 2;
export const PHI_MAX = Math.PI / 3; // 60 degrees, the cap of the engine schema
const FD_STEP = 1e-6;
const BACKTRACKS = 40;

export interface SliceData {
  b: Float64Array;
  w: Float64Array;
  alpha: Float64Array;
  u: Float64Array;
}

export function parseSlices(raw: unknown, name: string, minSlices: number): SliceData {
  const list = asArray(raw, name, minSlices, 200);
  const n = list.length;
  const out: SliceData = {
    b: new Float64Array(n),
    w: new Float64Array(n),
    alpha: new Float64Array(n),
    u: new Float64Array(n),
  };
  list.forEach((entry, i) => {
    const s = asObject(entry, `${name}[${i}]`);
    out.b[i] = asNumber(s.width_m, `${name}[${i}].width_m`, { lo: 0, loOpen: true, hi: 1e4 });
    out.w[i] = asNumber(s.weight_n_per_m, `${name}[${i}].weight_n_per_m`, { lo: 0, hi: 1e10 });
    out.alpha[i] = asNumber(s.base_angle_rad, `${name}[${i}].base_angle_rad`, {
      lo: -HALF_PI,
      hi: HALF_PI,
      loOpen: true,
      hiOpen: true,
    });
    out.u[i] = asNumber(s.pore_pressure_pa, `${name}[${i}].pore_pressure_pa`, { lo: 0, hi: 1e8 });
  });
  let drive = 0;
  for (let i = 0; i < n; i++) drive += (out.w[i] as number) * Math.sin(out.alpha[i] as number);
  if (!(drive > 0)) throw rangeError("the driving moment sum(W sin(alpha)) must be positive");
  return out;
}

export function parseStrength(args: Record<string, unknown>): { c: number; phi: number } {
  return {
    c: asNumber(args.cohesion_pa, "cohesion_pa", { lo: 0, hi: 1e8 }),
    phi: asNumber(args.friction_angle_rad, "friction_angle_rad", { lo: 0, hi: PHI_MAX }),
  };
}

export function parseControls(args: Record<string, unknown>): { tol: number; maxIter: number } {
  return {
    tol: optional(args.tolerance, (v) => asNumber(v, "tolerance", { lo: 1e-15, hi: 1e-9 }), 1e-12),
    maxIter: optional(args.max_iterations, (v) => asInteger(v, "max_iterations", { lo: 1, hi: 10000 }), 200),
  };
}

export function bishopCore(
  s: SliceData,
  c: number,
  phi: number,
  tol: number,
  maxIter: number,
): { fos: number; iterations: number } {
  const n = s.b.length;
  const tanPhi = Math.tan(phi);
  const cosA = new Float64Array(n);
  const shear = new Float64Array(n);
  const resisting = new Float64Array(n);
  let drive = 0;
  for (let i = 0; i < n; i++) {
    const a = s.alpha[i] as number;
    const sinA = Math.sin(a);
    cosA[i] = Math.cos(a);
    shear[i] = tanPhi * sinA;
    resisting[i] =
      c * (s.b[i] as number) + ((s.w[i] as number) - (s.u[i] as number) * (s.b[i] as number)) * tanPhi;
    drive += (s.w[i] as number) * sinA;
  }
  let f = 1;
  for (let iteration = 1; iteration <= maxIter; iteration++) {
    let sum = 0;
    for (let i = 0; i < n; i++) {
      const m = (cosA[i] as number) + (shear[i] as number) / f;
      if (!(m > 0))
        throw runtimeError(`m_alpha <= 0 at slice ${i} during iteration ${iteration}: no factor of safety`);
      sum += (resisting[i] as number) / m;
    }
    const next = sum / drive;
    const step = Math.abs(next - f);
    f = next;
    if (step <= tol * Math.abs(next)) return { fos: f, iterations: iteration };
  }
  throw runtimeError(`no convergence to tol=${tol} in ${maxIter} iterations`);
}

export function bishop(args: Record<string, unknown>): { fos: number; iterations: number } {
  const a = asObject(args, "args");
  const slices = parseSlices(a.slices, "slices", 1);
  const { c, phi } = parseStrength(a);
  const { tol, maxIter } = parseControls(a);
  return bishopCore(slices, c, phi, tol, maxIter);
}

class Breakdown extends Error {}

type Triple = [number, number, number];

function residuals(
  f: number,
  theta: number,
  ell: Float64Array,
  s: SliceData,
  c: number,
  tanPhi: number,
): Triple {
  const n = ell.length;
  let sumQ = 0;
  let sumQc = 0;
  let scale = 0;
  for (let i = 0; i < n; i++) {
    const a = s.alpha[i] as number;
    const den = Math.cos(a - theta) + (Math.sin(a - theta) * tanPhi) / f;
    if (!(den > 0)) throw new Breakdown(String(i));
    const q =
      ((c * (ell[i] as number)) / f +
        (((s.w[i] as number) * Math.cos(a) - (s.u[i] as number) * (ell[i] as number)) * tanPhi) / f -
        (s.w[i] as number) * Math.sin(a)) /
      den;
    sumQ += q;
    sumQc += q * Math.cos(a - theta);
    scale += Math.abs(q);
  }
  return [sumQ, sumQc, scale || 1];
}

/** Gaussian elimination with partial pivoting of a 2 x 2 system (what numpy.linalg.solve does); null when singular. */
function solve2(j: number[][], r: [number, number]): [number, number] | null {
  let a = j[0]?.[0] as number;
  let b = j[0]?.[1] as number;
  let c = j[1]?.[0] as number;
  let d = j[1]?.[1] as number;
  let r0 = r[0];
  let r1 = r[1];
  if (Math.abs(c) > Math.abs(a)) {
    [a, b, c, d] = [c, d, a, b];
    [r0, r1] = [r1, r0];
  }
  if (a === 0) return null;
  const l = c / a;
  const d2 = d - l * b;
  if (d2 === 0) return null;
  const x1 = (r1 - l * r0) / d2;
  const x0 = (r0 - b * x1) / a;
  return [x0, x1];
}

function breakdownError(e: unknown): never {
  if (e instanceof Breakdown)
    throw runtimeError(`the Spencer denominator is not positive at slice ${e.message}`);
  throw e;
}

function spencerNewton(
  s: SliceData,
  c: number,
  phi: number,
  tol: number,
  maxIter: number,
): { fos: number; theta: number; iterations: number } {
  const n = s.b.length;
  const ell = new Float64Array(n);
  for (let i = 0; i < n; i++) ell[i] = (s.b[i] as number) / Math.cos(s.alpha[i] as number);
  const tanPhi = Math.tan(phi);
  let f: number;
  try {
    f = bishopCore(s, c, phi, 1e-6, 10000).fos;
  } catch {
    f = 1;
  }
  let theta = 0;
  let last = Number.POSITIVE_INFINITY;
  for (let iteration = 1; iteration <= maxIter; iteration++) {
    let now: Triple;
    try {
      now = residuals(f, theta, ell, s, c, tanPhi);
    } catch (e) {
      return breakdownError(e);
    }
    const [force, moment, scale] = now;
    last = Math.max(Math.abs(force), Math.abs(moment)) / scale;
    if (last <= tol) return { fos: f, theta, iterations: iteration };
    const hf = FD_STEP * Math.max(Math.abs(f), 1);
    const ht = FD_STEP;
    let fp: Triple;
    let fm: Triple;
    let tp: Triple;
    let tm: Triple;
    try {
      fp = residuals(f + hf, theta, ell, s, c, tanPhi);
      fm = residuals(f - hf, theta, ell, s, c, tanPhi);
      tp = residuals(f, theta + ht, ell, s, c, tanPhi);
      tm = residuals(f, theta - ht, ell, s, c, tanPhi);
    } catch (e) {
      return breakdownError(e);
    }
    const jac = [
      [(fp[0] - fm[0]) / (2 * hf), (tp[0] - tm[0]) / (2 * ht)],
      [(fp[1] - fm[1]) / (2 * hf), (tp[1] - tm[1]) / (2 * ht)],
    ];
    const step = solve2(jac, [-force, -moment]);
    if (step === null) throw runtimeError("the Jacobian of Spencer's equations is singular");
    let damping = 1;
    let fNew = f;
    let tNew = theta;
    for (let k = 0; k < BACKTRACKS; k++) {
      fNew = f + damping * step[0];
      tNew = theta + damping * step[1];
      if (fNew > 0) {
        let trial: Triple | null = null;
        try {
          trial = residuals(fNew, tNew, ell, s, c, tanPhi);
        } catch (e) {
          if (!(e instanceof Breakdown)) throw e;
        }
        if (trial !== null) {
          if (Math.max(Math.abs(trial[0]), Math.abs(trial[1])) / trial[2] < last || damping < 2 * FD_STEP)
            break;
        }
      }
      damping /= 2;
    }
    f = fNew;
    theta = tNew;
  }
  throw runtimeError(`no convergence to tol=${tol} in ${maxIter} iterations`);
}

/**
 * Levenberg-Marquardt on the scaled force and moment residuals, from the Bishop value. Used only after the reference's damped
 * Newton iteration has failed: with equal base angles the interslice inclination is not identifiable (both equations hold for
 * every theta at the root), the Jacobian is singular and the relative residual of the reference never reaches zero, although F is
 * fixed by the force equation.
 */
function spencerRegularised(
  s: SliceData,
  c: number,
  phi: number,
  tol: number,
  maxIter: number,
): { fos: number; theta: number; iterations: number } {
  const n = s.b.length;
  const ell = new Float64Array(n);
  for (let i = 0; i < n; i++) ell[i] = (s.b[i] as number) / Math.cos(s.alpha[i] as number);
  const tanPhi = Math.tan(phi);
  // scaled by the driving force: the reference's scale sum|Q| also vanishes at the root, so with equal angles the ratio stays at 1
  let drive = 0;
  for (let i = 0; i < n; i++) drive += (s.w[i] as number) * Math.sin(s.alpha[i] as number);
  const scaled = (f: number, theta: number): [number, number] => {
    const [force, moment] = residuals(f, theta, ell, s, c, tanPhi);
    return [force / drive, moment / drive];
  };
  let f: number;
  try {
    f = bishopCore(s, c, phi, 1e-6, 10000).fos;
  } catch {
    f = 1;
  }
  let theta = 0;
  let lambda = 1e-9;
  for (let iteration = 1; iteration <= maxIter; iteration++) {
    let r: [number, number];
    try {
      r = scaled(f, theta);
    } catch (e) {
      return breakdownError(e);
    }
    const size = Math.max(Math.abs(r[0]), Math.abs(r[1]));
    if (size <= tol) return { fos: f, theta, iterations: iteration };
    const hf = FD_STEP * Math.max(Math.abs(f), 1);
    let a: [number, number];
    let b: [number, number];
    let cc: [number, number];
    let d: [number, number];
    try {
      a = scaled(f + hf, theta);
      b = scaled(f - hf, theta);
      cc = scaled(f, theta + FD_STEP);
      d = scaled(f, theta - FD_STEP);
    } catch (e) {
      return breakdownError(e);
    }
    const j00 = (a[0] - b[0]) / (2 * hf);
    const j10 = (a[1] - b[1]) / (2 * hf);
    const j01 = (cc[0] - d[0]) / (2 * FD_STEP);
    const j11 = (cc[1] - d[1]) / (2 * FD_STEP);
    const g0 = j00 * r[0] + j10 * r[1];
    const g1 = j01 * r[0] + j11 * r[1];
    let accepted = false;
    for (let k = 0; k < BACKTRACKS && !accepted; k++) {
      const m00 = j00 * j00 + j10 * j10 + lambda;
      const m01 = j00 * j01 + j10 * j11;
      const m11 = j01 * j01 + j11 * j11 + lambda;
      const det = m00 * m11 - m01 * m01;
      if (det > 0) {
        const df = (-g0 * m11 + g1 * m01) / det;
        const dt = (g0 * m01 - g1 * m00) / det;
        const fNew = f + df;
        if (fNew > 0) {
          try {
            const rn = scaled(fNew, theta + dt);
            if (Math.max(Math.abs(rn[0]), Math.abs(rn[1])) < size) {
              f = fNew;
              theta += dt;
              lambda = Math.max(lambda / 10, 1e-14);
              accepted = true;
            }
          } catch (e) {
            if (!(e instanceof Breakdown)) throw e;
          }
        }
      }
      if (!accepted) lambda *= 10;
    }
    if (!accepted) throw runtimeError("the regularised Spencer iteration cannot reduce the residual");
  }
  throw runtimeError(`no convergence to tol=${tol} in ${maxIter} iterations`);
}

export function spencerCore(
  s: SliceData,
  c: number,
  phi: number,
  tol: number,
  maxIter: number,
): { fos: number; theta: number; iterations: number } {
  try {
    return spencerNewton(s, c, phi, tol, maxIter);
  } catch (e) {
    if (!(e instanceof AnalyticalError) || e.code !== "E_RUNTIME") throw e;
    return spencerRegularised(s, c, phi, tol, maxIter);
  }
}

export function spencer(args: Record<string, unknown>): {
  fos: number;
  theta_rad: number;
  iterations: number;
} {
  const a = asObject(args, "args");
  const slices = parseSlices(a.slices, "slices", 2);
  const { c, phi } = parseStrength(a);
  const { tol, maxIter } = parseControls(a);
  const r = spencerCore(slices, c, phi, tol, maxIter);
  return { fos: r.fos, theta_rad: r.theta, iterations: r.iterations };
}
