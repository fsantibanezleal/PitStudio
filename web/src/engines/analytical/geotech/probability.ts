// Monte-Carlo probability of failure of fixed slip surfaces (spec 010 FR-010-03, spec 018 FR-018-52): independent strength
// draws by inverse CDF (never by rejection) from the PCG64 port, F = minimum over the candidate surfaces, failure = F < 1.
import { PCG64 } from "../../random/pcg64";
import { SeedSequence } from "../../random/seedSequence";
import { rangeError, runtimeError, schemaError } from "../errors";
import { normalCdf, normalPpf } from "../normal";
import { asArray, asInteger, asNumber, asObject } from "../validate";
import { bishopCore, PHI_MAX, parseSlices, type SliceData, spencerCore } from "./lem";

const WILSON_Z = 1.96;

export interface PofResult {
  n_samples: number;
  failures: number;
  pof: number;
  wilson_low: number;
  wilson_high: number;
}

function wilson(k: number, n: number): PofResult {
  const p = k / n;
  const z2 = WILSON_Z * WILSON_Z;
  const denom = 1 + z2 / n;
  const centre = (p + z2 / (2 * n)) / denom;
  const half = (WILSON_Z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n))) / denom;
  return {
    n_samples: n,
    failures: k,
    pof: p,
    wilson_low: Math.max(0, centre - half),
    wilson_high: Math.min(1, centre + half),
  };
}

function parseSurfaces(raw: unknown): SliceData[] {
  const list = asArray(raw, "surfaces", 1, 64);
  return list.map((s, i) => parseSlices(s, `surfaces[${i}]`, 2));
}

function parseMethod(raw: unknown): "bishop" | "spencer" {
  if (raw !== "bishop" && raw !== "spencer") throw schemaError("method must be 'bishop' or 'spencer'");
  return raw;
}

/** F of a sample on its weakest surface; a surface that does not converge counts as a failure (F undefined, taken below 1). */
function failsSample(surfaces: SliceData[], method: "bishop" | "spencer", c: number, phi: number): boolean {
  for (const s of surfaces) {
    try {
      const f =
        method === "bishop" ? bishopCore(s, c, phi, 1e-12, 200).fos : spencerCore(s, c, phi, 1e-12, 200).fos;
      if (f < 1) return true;
    } catch {
      return true;
    }
  }
  return false;
}

export function pof_from_samples(args: Record<string, unknown>): PofResult {
  const a = asObject(args, "args");
  const surfaces = parseSurfaces(a.surfaces);
  const method = parseMethod(a.method);
  const samples = asArray(a.samples, "samples", 1, 100000);
  let failures = 0;
  samples.forEach((raw, i) => {
    const s = asObject(raw, `samples[${i}]`);
    const c = asNumber(s.cohesion_pa, `samples[${i}].cohesion_pa`, { lo: 0, hi: 1e8 });
    const phi = asNumber(s.friction_angle_rad, `samples[${i}].friction_angle_rad`, { lo: 0, hi: PHI_MAX });
    if (failsSample(surfaces, method, c, phi)) failures += 1;
  });
  return wilson(failures, samples.length);
}

interface Distribution {
  kind: "normal" | "lognormal" | "uniform";
  mean: number;
  sd: number;
  lower: number;
  upper: number;
}

function parseDistribution(raw: unknown, name: string, hardMax: number): Distribution {
  const o = asObject(raw, name);
  const kind = o.distribution;
  if (kind !== "normal" && kind !== "lognormal" && kind !== "uniform")
    throw schemaError(`${name}.distribution must be normal, lognormal or uniform`);
  const bound = (key: string, fallback: number) =>
    o[key] === undefined ? fallback : asNumber(o[key], `${name}.${key}`, { lo: 0, hi: hardMax });
  if (kind === "uniform") {
    if (o.lower === undefined || o.upper === undefined)
      throw schemaError(`${name}: uniform needs lower and upper`);
    const lower = bound("lower", 0);
    const upper = bound("upper", hardMax);
    if (!(lower < upper)) throw rangeError(`${name}: lower must be below upper`);
    return { kind, mean: 0, sd: 0, lower, upper };
  }
  if (o.mean === undefined || o.sd === undefined) throw schemaError(`${name}: ${kind} needs mean and sd`);
  const mean = asNumber(o.mean, `${name}.mean`, { lo: 0, hi: hardMax });
  const sd = asNumber(o.sd, `${name}.sd`, { lo: 0, loOpen: true, hi: hardMax });
  return { kind, mean, sd, lower: bound("lower", 0), upper: bound("upper", hardMax) };
}

/** One draw by inverse CDF of the distribution truncated to [lower, upper]. */
function draw(gen: PCG64, d: Distribution): number {
  const u = gen.random();
  if (d.kind === "uniform") return d.lower + u * (d.upper - d.lower);
  let mu = d.mean;
  let sigma = d.sd;
  let lo = d.lower;
  let hi = d.upper;
  const log = d.kind === "lognormal";
  if (log) {
    const s2 = Math.log(1 + (d.sd / d.mean) ** 2);
    sigma = Math.sqrt(s2);
    mu = Math.log(d.mean) - s2 / 2;
    lo = lo > 0 ? Math.log(lo) : Number.NEGATIVE_INFINITY;
    hi = Math.log(hi);
  }
  const pa = Number.isFinite(lo) ? normalCdf((lo - mu) / sigma) : 0;
  const pb = Number.isFinite(hi) ? normalCdf((hi - mu) / sigma) : 1;
  if (!(pb - pa > 1e-300)) throw runtimeError("the truncation leaves no probability mass");
  const p = Math.min(Math.max(pa + u * (pb - pa), Number.MIN_VALUE), 1 - 1e-16);
  const x = mu + sigma * normalPpf(p);
  return log ? Math.exp(x) : Math.min(Math.max(x, d.lower), d.upper);
}

export function pof_monte_carlo(args: Record<string, unknown>): PofResult {
  const a = asObject(args, "args");
  const surfaces = parseSurfaces(a.surfaces);
  const method = parseMethod(a.method);
  const n = asInteger(a.n_samples, "n_samples", { lo: 1, hi: 100000 });
  const seed = asInteger(a.seed, "seed", { lo: 0, hi: Number.MAX_SAFE_INTEGER });
  const cohesion = parseDistribution(a.cohesion_pa, "cohesion_pa", 1e8);
  const friction = parseDistribution(a.friction_angle_rad, "friction_angle_rad", PHI_MAX);
  const gen = new PCG64(new SeedSequence(seed));
  let failures = 0;
  for (let i = 0; i < n; i++) {
    const c = draw(gen, cohesion);
    const phi = draw(gen, friction);
    if (failsSample(surfaces, method, c, phi)) failures += 1;
  }
  return wilson(failures, n);
}
