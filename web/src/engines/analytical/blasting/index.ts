// Engine `blasting` (spec 018 section 7.1): the minephys.blasting port, case D1. Design (charge, powder factor), Kuz-Ram mean size
// with its two Cunningham variants, the uniformity index, the Swebrec and KCO size distribution, the PPV site law and the
// drag-free flyrock range. Constants are the knowledge rows of the reference (../rows.ts). Upper caps of the request schema belong
// to the host validator; the checks here are the physical domains of the reference and the validity ranges of Cunningham's model.
import { rangeError, schemaError } from "../errors";
import { row } from "../rows";
import { asArray, asEnum, asNumber, asObject, optional } from "../validate";

const POSITIVE = { lo: 0, loOpen: true } as const;
const STANDARD_GRAVITY = 9.80665;
const LN2 = Math.log(2);

export function charge_per_hole(args: Record<string, unknown>): { charge_kg: number } {
  const a = asObject(args, "args");
  const rho = asNumber(a.explosive_density_kg_per_m3, "explosive_density_kg_per_m3", POSITIVE);
  const d = asNumber(a.hole_diameter_m, "hole_diameter_m", POSITIVE);
  const length = asNumber(a.charge_length_m, "charge_length_m", POSITIVE);
  return { charge_kg: rho * (Math.PI / 4) * d * d * length };
}

export function powder_factor(args: Record<string, unknown>): { powder_factor_kg_per_m3: number } {
  const a = asObject(args, "args");
  const q = asNumber(a.charge_kg, "charge_kg", POSITIVE);
  const b = asNumber(a.burden_m, "burden_m", POSITIVE);
  const s = asNumber(a.spacing_m, "spacing_m", POSITIVE);
  const h = asNumber(a.bench_height_m, "bench_height_m", POSITIVE);
  return { powder_factor_kg_per_m3: q / (b * s * h) };
}

export function kuznetsov_x50(args: Record<string, unknown>): { x50_m: number } {
  const a = asObject(args, "args");
  const rockFactor = asNumber(a.rock_factor, "rock_factor", { lo: 0.8, hi: 22 });
  const k = asNumber(a.powder_factor_kg_per_m3, "powder_factor_kg_per_m3", { ...POSITIVE, hi: 5 });
  const q = asNumber(a.charge_kg, "charge_kg", { ...POSITIVE, hi: 1e5 });
  const rws = asNumber(a.rws, "rws", { lo: 20 }); // the 200 cap of the schema is the host validator's
  const variant = optional(
    a.variant,
    (v) => asEnum(v, "variant", ["cunningham1983", "cunningham2005"] as const),
    "cunningham1983" as "cunningham1983" | "cunningham2005",
  );
  const exponent = row(
    variant === "cunningham2005" ? "kuzram_rws_exponent_2005" : "kuzram_rws_exponent_1983",
  );
  const x50cm =
    rockFactor *
    k ** row("kuznetsov_powder_factor_exponent") *
    q ** row("kuznetsov_charge_exponent") *
    (row("kuznetsov_tnt_relative_weight_strength") / rws) ** exponent;
  return { x50_m: x50cm / 100 };
}

export function uniformity_index(args: Record<string, unknown>): { uniformity: number } {
  const a = asObject(args, "args");
  const b = asNumber(a.burden_m, "burden_m", POSITIVE);
  const s = asNumber(a.spacing_m, "spacing_m", POSITIVE);
  const d = asNumber(a.hole_diameter_m, "hole_diameter_m", POSITIVE);
  const w = asNumber(a.drilling_deviation_m, "drilling_deviation_m", { lo: 0 });
  const length = asNumber(a.charge_length_m, "charge_length_m", POSITIVE);
  const h = asNumber(a.bench_height_m, "bench_height_m", POSITIVE);
  const hasBottom = a.bottom_charge_length_m !== undefined;
  const hasColumn = a.column_charge_length_m !== undefined;
  if (hasBottom !== hasColumn)
    throw schemaError("bottom_charge_length_m and column_charge_length_m are given together or not at all");
  const bcl = hasBottom ? asNumber(a.bottom_charge_length_m, "bottom_charge_length_m", { lo: 0 }) : length;
  const ccl = hasColumn ? asNumber(a.column_charge_length_m, "column_charge_length_m", { lo: 0 }) : 0;
  const first = row("cunningham_n_constant") - (row("cunningham_n_burden_coefficient") * b) / (d * 1000);
  if (first <= 0)
    throw rangeError("the burden is too large for the hole diameter: 14 B / d must stay below 2.2");
  if (w >= b) throw rangeError("drilling_deviation_m must be smaller than the burden");
  if (hasBottom && bcl + ccl > length)
    throw rangeError("bottom plus column charge must not exceed charge_length_m");
  const n =
    first *
    Math.sqrt((1 + s / b) / 2) *
    (1 - w / b) *
    (Math.abs(bcl - ccl) / length + row("cunningham_n_charge_offset")) **
      row("cunningham_n_charge_exponent") *
    (length / h);
  return { uniformity: n };
}

function checkX50(x50: number, xmax: number): void {
  if (x50 >= xmax) throw rangeError("x50_m must be smaller than xmax_m (ln(xmax / x50) must be positive)");
}

export function swebrec_passing(args: Record<string, unknown>): { passing: Float64Array } {
  const a = asObject(args, "args");
  const raw = a.sizes_m;
  const sizes =
    raw instanceof Float64Array ? Array.from(raw) : asArray(raw, "sizes_m", 0, 1024).map((v) => v as number);
  if (sizes.length === 0) throw schemaError("sizes_m must hold at least one size");
  const x50 = asNumber(a.x50_m, "x50_m", POSITIVE);
  const xmax = asNumber(a.xmax_m, "xmax_m", POSITIVE);
  const b = asNumber(a.undulation, "undulation", POSITIVE);
  checkX50(x50, xmax);
  const passing = new Float64Array(sizes.length);
  sizes.forEach((x, i) => {
    const size = asNumber(x, `sizes_m[${i}]`, POSITIVE);
    passing[i] = size < xmax ? 1 / (1 + (Math.log(xmax / size) / Math.log(xmax / x50)) ** b) : 1;
  });
  return { passing };
}

export function kco_undulation(args: Record<string, unknown>): { undulation: number } {
  const a = asObject(args, "args");
  const n = asNumber(a.uniformity, "uniformity", POSITIVE);
  const x50 = asNumber(a.x50_m, "x50_m", POSITIVE);
  const xmax = asNumber(a.xmax_m, "xmax_m", POSITIVE);
  checkX50(x50, xmax);
  return { undulation: 2 * LN2 * Math.log(xmax / x50) * n };
}

export function ppv_scaled_distance(args: Record<string, unknown>): {
  scaled_distance_m_per_kg_half: number;
  ppv_m_per_s: number;
} {
  const a = asObject(args, "args");
  const d = asNumber(a.distance_m, "distance_m", POSITIVE);
  const w = asNumber(a.charge_per_delay_kg, "charge_per_delay_kg", POSITIVE);
  const k = asNumber(a.k_site_m_per_s, "k_site_m_per_s", POSITIVE);
  const beta = asNumber(a.site_exponent, "site_exponent", POSITIVE);
  const scaled = d / Math.sqrt(w);
  return { scaled_distance_m_per_kg_half: scaled, ppv_m_per_s: k * scaled ** -beta };
}

export function flyrock_range_no_drag(args: Record<string, unknown>): { range_m: number } {
  const a = asObject(args, "args");
  const v = asNumber(a.launch_speed_m_per_s, "launch_speed_m_per_s", POSITIVE);
  const theta = asNumber(a.launch_angle_rad, "launch_angle_rad", { lo: 0, hi: Math.PI / 2 });
  const g = optional(a.gravity_m_per_s2, (x) => asNumber(x, "gravity_m_per_s2", POSITIVE), STANDARD_GRAVITY);
  return { range_m: (v * v * Math.sin(2 * theta)) / g };
}
