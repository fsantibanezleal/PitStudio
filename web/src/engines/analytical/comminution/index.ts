// Engine `comminution` (spec 018 section 7.1): the minephys.comminution port, case D5. Bond's third law, the size at a passing
// fraction (log-log interpolation), and the mine-to-mill chain: blast curve -> class masses -> crusher matrix model -> cumulative
// passing -> F80 -> Bond energy -> throughput (Bond only, as in the engine schema; Morrell is a reference-only model).
import { rangeError, schemaError } from "../errors";
import { row } from "../rows";
import { asArray, asEnum, asNumber, asObject } from "../validate";

const UM_PER_M = 1e6;
const SUM_TOL = 1e-12;
const POSITIVE = { lo: 0, loOpen: true } as const;

export function bond_energy(args: Record<string, unknown>): { specific_energy_j_per_kg: number } {
  const a = asObject(args, "args");
  const wi = asNumber(a.work_index_j_per_kg, "work_index_j_per_kg", { ...POSITIVE, hi: 360000 });
  const f80 = asNumber(a.f80_m, "f80_m", { ...POSITIVE, hi: 1 });
  const p80 = asNumber(a.p80_m, "p80_m", { lo: row("bond_min_product_size") / UM_PER_M, hi: 1 });
  if (!(p80 < f80)) throw rangeError("p80_m must be finer than f80_m");
  return { specific_energy_j_per_kg: bondEnergy(wi, f80, p80) };
}

function bondEnergy(wi: number, f80: number, p80: number): number {
  return wi * (row("bond_law_coefficient") * (1 / Math.sqrt(p80 * UM_PER_M) - 1 / Math.sqrt(f80 * UM_PER_M)));
}

/** Validated (sizes, passing) of a cumulative curve, returned coarse to fine. */
function curve(
  sizesRaw: unknown,
  passingRaw: unknown,
  names: [string, string],
  opts: { decreasing?: boolean; max: number },
): { s: number[]; p: number[] } {
  const [sn, pn] = names;
  const s = asArray(sizesRaw, sn, 2, opts.max).map((v, i) => asNumber(v, `${sn}[${i}]`, POSITIVE));
  const stepsDown = s.every((v, i) => i === 0 || v < (s[i - 1] as number));
  const stepsUp = s.every((v, i) => i === 0 || v > (s[i - 1] as number));
  if (opts.decreasing ? !stepsDown : !(stepsDown || stepsUp))
    throw rangeError(
      `${sn} must be strictly ${opts.decreasing ? "decreasing (coarse to fine)" : "monotone"}`,
    );
  const pRaw = asArray(passingRaw, pn);
  if (pRaw.length !== s.length)
    throw schemaError(`${sn} and ${pn} differ in length: ${s.length} and ${pRaw.length}`);
  let p = pRaw.map((v, i) => asNumber(v, `${pn}[${i}]`, { lo: 0, hi: 1 }));
  let sizes = s;
  if ((s[0] as number) < (s[s.length - 1] as number)) {
    sizes = [...s].reverse();
    p = [...p].reverse();
  }
  for (let i = 1; i < p.length; i++)
    if ((p[i] as number) > (p[i - 1] as number))
      throw rangeError(`${pn} must not increase towards finer sizes`);
  return { s: sizes, p };
}

/** Size at which the coarse-to-fine curve equals `target`: exact at grid points, (ln x, ln P) between them. */
function interpolateSize(s: number[], p: number[], target: number): number {
  const hit = p.indexOf(target);
  if (hit >= 0) return s[hit] as number;
  let i = 0;
  for (; i < p.length - 1; i++) if ((p[i] as number) >= target && target >= (p[i + 1] as number)) break;
  const lx0 = Math.log(s[i] as number);
  const lx1 = Math.log(s[i + 1] as number);
  const p0 = p[i] as number;
  const p1 = p[i + 1] as number;
  let lp0: number;
  let lp1: number;
  let lt: number;
  if (p1 > 0) {
    lp0 = Math.log(p0);
    lp1 = Math.log(p1);
    lt = Math.log(target);
  } else {
    lp0 = p0;
    lp1 = p1;
    lt = target;
  }
  return Math.exp(lx0 + ((lt - lp0) * (lx1 - lx0)) / (lp1 - lp0));
}

/** Cumulative passing at `size` of the coarse-to-fine curve (exact at grid sizes, (ln x, ln P) between them). */
function passingAt(s: number[], p: number[], size: number): number {
  const hit = s.indexOf(size);
  if (hit >= 0) return p[hit] as number;
  let i = 0;
  for (; i < s.length - 1; i++) if ((s[i] as number) >= size && size >= (s[i + 1] as number)) break;
  const lx0 = Math.log(s[i] as number);
  const lx1 = Math.log(s[i + 1] as number);
  const lx = Math.log(size);
  const p0 = p[i] as number;
  const p1 = p[i + 1] as number;
  if (p1 > 0) {
    const a = Math.log(p0);
    const b = Math.log(p1);
    return Math.exp(a + ((lx - lx0) * (b - a)) / (lx1 - lx0));
  }
  return p0 + ((lx - lx0) * (p1 - p0)) / (lx1 - lx0);
}

export function passing_size(args: Record<string, unknown>): { size_m: number } {
  const a = asObject(args, "args");
  const { s, p } = curve(a.sizes_m, a.passing, ["sizes_m", "passing"], { max: 10000 });
  const f = asNumber(a.fraction, "fraction");
  if (!((p[p.length - 1] as number) <= f && f <= (p[0] as number)))
    throw rangeError(`fraction must lie in [${p[p.length - 1]}, ${p[0]}], got ${f}`);
  return { size_m: interpolateSize(s, p, f) };
}

function parseBreakage(raw: unknown, n: number, active: number[]): number[][] {
  const rows = asArray(raw, "breakage");
  if (rows.length !== n) throw schemaError(`breakage must have ${n} rows, got ${rows.length}`);
  const b = rows.map((r, i) => {
    const cells = asArray(r, `breakage[${i}]`);
    if (cells.length !== n) throw schemaError(`breakage[${i}] must have ${n} entries, got ${cells.length}`);
    return cells.map((v, j) => asNumber(v, `breakage[${i}][${j}]`, { lo: 0, hi: 1 }));
  });
  for (let i = 0; i < n; i++)
    for (let j = i; j < n; j++)
      if ((b[i] as number[])[j] !== 0) throw rangeError("breakage must be strictly lower triangular");
  for (let j = 0; j < n; j++) {
    let sum = 0;
    for (let i = 0; i < n; i++) sum += (b[i] as number[])[j] as number;
    if ((active[j] as number) > 0 && Math.abs(sum - 1) > SUM_TOL)
      throw rangeError(`breakage column ${j} sums to ${sum}, not 1`);
  }
  return b;
}

export interface ChainResult {
  f80_m: number;
  fines_fraction: number;
  specific_energy_j_per_kg: number;
  crusher_feed_kg_per_s: number;
  mill_product_kg_per_s: number;
}

export function mine_to_mill_chain(args: Record<string, unknown>): ChainResult {
  const a = asObject(args, "args");
  const { s, p } = curve(a.sizes_m, a.blast_passing, ["sizes_m", "blast_passing"], {
    decreasing: true,
    max: 200,
  });
  asEnum(a.energy_model, "energy_model", ["bond"] as const);
  const target = asNumber(a.target_p80_m, "target_p80_m", {
    lo: row("bond_min_product_size") / UM_PER_M,
    hi: 1,
  });
  const power = asNumber(a.installed_power_w, "installed_power_w", { ...POSITIVE, hi: 1e8 });
  const wi = asNumber(a.work_index_j_per_kg, "work_index_j_per_kg", { ...POSITIVE, hi: 360000 });
  const fines = asNumber(a.fines_size_m, "fines_size_m", { ...POSITIVE, hi: 1 });
  const n = s.length;
  const clRaw = asArray(a.classification, "classification");
  if (clRaw.length !== n) throw schemaError(`classification must have ${n} entries, got ${clRaw.length}`);
  const c = clRaw.map((v, i) => asNumber(v, `classification[${i}]`, { lo: 0, hi: 1 }));
  if (c[n - 1] !== 0) throw rangeError("the finest class cannot be broken (classification must end in 0)");
  const b = parseBreakage(a.breakage, n, c);
  // class masses m_i = P_i - P_(i+1), m_n = P_n; crusher x = f + B C x (forward substitution), product (1 - c) x
  const x: number[] = [];
  for (let i = 0; i < n; i++) {
    const feed = i < n - 1 ? (p[i] as number) - (p[i + 1] as number) : (p[i] as number);
    let acc = 0;
    const bi = b[i] as number[];
    for (let j = 0; j < i; j++) acc += (bi[j] as number) * ((c[j] as number) * (x[j] as number));
    x.push(feed + acc);
  }
  const product = x.map((xi, i) => (1 - (c[i] as number)) * xi);
  const cum = new Array<number>(n);
  let run = 0;
  for (let i = n - 1; i >= 0; i--) {
    run += product[i] as number;
    cum[i] = run;
  }
  if (!((cum[n - 1] as number) <= 0.8 && 0.8 <= (cum[0] as number)))
    throw rangeError("blast_passing does not reach 80 % passing, so F80 is undefined");
  const f80 = interpolateSize(s, cum, 0.8);
  if (!(target < f80)) throw rangeError(`target_p80_m must be finer than the crusher product F80 (${f80} m)`);
  if (!((s[n - 1] as number) <= fines && fines <= (s[0] as number)))
    throw rangeError("fines_size_m must lie within the size grid");
  const energy = bondEnergy(wi, f80, target);
  const throughput = power / energy;
  return {
    f80_m: f80,
    fines_fraction: passingAt(s, cum, fines),
    specific_energy_j_per_kg: energy,
    crusher_feed_kg_per_s: throughput,
    mill_product_kg_per_s: throughput,
  };
}
