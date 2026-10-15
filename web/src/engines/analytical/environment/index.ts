// Engine `plume` (spec 018 section 7.1): the minephys.environment port, cases D2 and D3. AP-42 section 13.2.2 unpaved-road emission
// factor (equation 1a), the ISC3 dispersion coefficients (rural Pasquill-Gifford, urban Briggs) and the Gaussian plume on a receptor
// grid with ground reflection and an optional mixing lid. Constants are the knowledge rows of the reference (../rows.ts).
import { sizeError } from "../errors";
import { ROWS, row } from "../rows";
import { asEnum, asInteger, asNumber, asObject, optional } from "../validate";

const CLASSES = ["A", "B", "C", "D", "E", "F"] as const;
type StabilityClass = (typeof CLASSES)[number];
const TERRAINS = ["rural", "urban"] as const;
type Terrain = (typeof TERRAINS)[number];
const SIZE_SUFFIX = { "PM2.5": "pm25", PM10: "pm10", PM30: "pm30" } as const;
const MAX_GRID = 256;
const MAX_IMAGE_TERMS = 1000;
const TINY = 1e-16;

export function ap42_emission_factor(args: Record<string, unknown>): { emission_factor_kg_per_m: number } {
  const a = asObject(args, "args");
  const silt = asNumber(a.silt_fraction, "silt_fraction", { lo: 0.018, hi: 0.252 });
  const weight = asNumber(a.mean_weight_kg, "mean_weight_kg", { lo: 1814.36948, hi: 263083.5746 });
  const size = asEnum(a.size_class, "size_class", ["PM2.5", "PM10", "PM30"] as const);
  const sfx = SIZE_SUFFIX[size];
  const s = 100 * silt;
  const w = weight / row("ap42_short_ton_in_kg");
  const eLb =
    row(`ap42_industrial_k_${sfx}`) *
    (s / row("ap42_silt_reference")) ** row(`ap42_industrial_a_${sfx}`) *
    (w / row("ap42_weight_reference")) ** row(`ap42_industrial_b_${sfx}`);
  return { emission_factor_kg_per_m: (eLb * row("pound")) / row("ap42_mile_in_m") };
}

interface Band {
  upper: number;
  a: number;
  b: number;
}

const BANDS: Record<string, Band[]> = {};
function bands(key: string): Band[] {
  let cached = BANDS[key];
  if (cached === undefined) {
    cached = [];
    for (let k = 1; `isc3_pg_sigma_z_${key}_${k}_a` in ROWS; k++) {
      const xmax = ROWS[`isc3_pg_sigma_z_${key}_${k}_xmax`];
      cached.push({
        upper: typeof xmax === "number" ? xmax : Number.POSITIVE_INFINITY,
        a: row(`isc3_pg_sigma_z_${key}_${k}_a`),
        b: row(`isc3_pg_sigma_z_${key}_${k}_b`),
      });
    }
    BANDS[key] = cached;
  }
  return cached;
}

/** ISC3 (sigma_y, sigma_z) in metres at the downwind distance x (m, > 0). */
export function sigmas(x: number, cls: StabilityClass, terrain: Terrain): [number, number] {
  const key = cls.toLowerCase();
  if (terrain === "urban") {
    const one = (axis: "y" | "z") =>
      row(`isc3_briggs_urban_${axis}_${key}_coef`) *
      x *
      (1 + row(`isc3_briggs_urban_${axis}_${key}_slope`) * x) **
        row(`isc3_briggs_urban_${axis}_${key}_exponent`);
    return [one("y"), one("z")];
  }
  const km = x / 1000;
  const c = row(`isc3_pg_sigma_y_c_${key}`);
  const d = row(`isc3_pg_sigma_y_d_${key}`);
  const sy = row("isc3_sigma_y_scale") * km * Math.tan(row("isc3_deg_to_rad") * (c - d * Math.log(km)));
  const list = bands(key);
  // numpy.searchsorted(uppers, km, side="left"): the first band whose upper distance is not below km
  let idx = list.findIndex((band) => band.upper >= km);
  if (idx < 0) idx = list.length - 1;
  const band = list[idx] as Band;
  let sz = band.a * km ** band.b;
  if (cls === "A" || cls === "B" || cls === "C") sz = Math.min(sz, row("isc3_sigma_z_cap"));
  return [sy, sz];
}

export function pasquill_sigmas(args: Record<string, unknown>): { sigma_y_m: number; sigma_z_m: number } {
  const a = asObject(args, "args");
  // the 100 km cap of the request schema is the host validator's; the function itself accepts any finite distance > 0
  // (the monotonicity property of T-018-066 evaluates up to 1.5 x the cap)
  const x = asNumber(a.downwind_distance_m, "downwind_distance_m", { lo: 0, loOpen: true });
  const cls = asEnum(a.stability_class, "stability_class", CLASSES);
  const terrain = asEnum(a.terrain, "terrain", TERRAINS);
  const [sy, sz] = sigmas(x, cls, terrain);
  return { sigma_y_m: sy, sigma_z_m: sz };
}

const vTerm = (z: number, h: number, sz: number) =>
  Math.exp(-((z - h) ** 2) / (2 * sz ** 2)) + Math.exp(-((z + h) ** 2) / (2 * sz ** 2));

/** Vertical term with a mixing lid: the image series of ISC3 eq. 1-50, or the well-mixed form of eq. 1-51. */
function lidTerm(z: number, h: number, sz: number, zi: number): number {
  if (h > zi) return 0;
  if (sz / zi >= row("isc3_lid_uniform_ratio")) return (Math.sqrt(2 * Math.PI) * sz) / zi;
  let v = vTerm(z, h, sz);
  for (let i = 1; i <= MAX_IMAGE_TERMS; i++) {
    const shift = 2 * i * zi;
    const t =
      Math.exp(-((z - h + shift) ** 2) / (2 * sz ** 2)) +
      Math.exp(-((z - h - shift) ** 2) / (2 * sz ** 2)) +
      Math.exp(-((z + h + shift) ** 2) / (2 * sz ** 2)) +
      Math.exp(-((z + h - shift) ** 2) / (2 * sz ** 2));
    v += t;
    if (t <= TINY * v) break;
  }
  return v;
}

export interface PlumeGridResult {
  concentration_kg_per_m3: Float64Array;
  rows: number;
  cols: number;
  max_concentration_kg_per_m3: number;
  max_x_m: number;
  max_y_m: number;
}

export function plume_grid(args: Record<string, unknown>): PlumeGridResult {
  const a = asObject(args, "args");
  const nxRaw = a.nx;
  const nyRaw = a.ny;
  // a grid above the cap is E_SIZE whatever else is wrong with the request
  for (const [name, v] of [
    ["nx", nxRaw],
    ["ny", nyRaw],
  ] as const) {
    if (typeof v === "number" && Number.isFinite(v) && v > MAX_GRID)
      throw sizeError(`${name} above the ${MAX_GRID} cap`);
  }
  const q = asNumber(a.source_strength_kg_per_s, "source_strength_kg_per_s", { lo: 0, hi: 1000 });
  const u = asNumber(a.wind_speed_m_per_s, "wind_speed_m_per_s", { lo: 0, loOpen: true, hi: 50 });
  const cls = asEnum(a.stability_class, "stability_class", CLASSES);
  const terrain = asEnum(a.terrain, "terrain", TERRAINS);
  const h = asNumber(a.release_height_m, "release_height_m", { lo: 0, hi: 500 });
  const zi = optional(
    a.mixing_height_m,
    (v) => asNumber(v, "mixing_height_m", { lo: 0, loOpen: true, hi: 10000 }),
    null as number | null,
  );
  const x0 = asNumber(a.x_start_m, "x_start_m", { lo: 0, loOpen: true, hi: 1e5 });
  const dx = asNumber(a.x_step_m, "x_step_m", { lo: 0, loOpen: true, hi: 1e4 });
  const nx = asInteger(nxRaw, "nx", { lo: 1, hi: MAX_GRID });
  const y0 = asNumber(a.y_start_m, "y_start_m", { lo: -1e5, hi: 1e5 });
  const dy = asNumber(a.y_step_m, "y_step_m", { lo: 0, loOpen: true, hi: 1e4 });
  const ny = asInteger(nyRaw, "ny", { lo: 1, hi: MAX_GRID });
  const z = asNumber(a.receptor_height_m, "receptor_height_m", { lo: 0, hi: 500 });
  const out = new Float64Array(nx * ny);
  let best = -1;
  let bestX = x0;
  let bestY = y0;
  const columns = Array.from({ length: nx }, (_, ix) => {
    const x = x0 + ix * dx;
    const [sy, sz] = sigmas(x, cls, terrain);
    return {
      x,
      sy,
      pre: q / (2 * Math.PI * u * sy * sz),
      v: zi === null ? vTerm(z, h, sz) : lidTerm(z, h, sz, zi),
    };
  });
  for (let iy = 0; iy < ny; iy++) {
    const y = y0 + iy * dy;
    for (let ix = 0; ix < nx; ix++) {
      const col = columns[ix] as { x: number; sy: number; pre: number; v: number };
      const c = col.pre * Math.exp(-(y ** 2) / (2 * col.sy ** 2)) * col.v;
      out[iy * nx + ix] = c;
      if (c > best) {
        best = c;
        bestX = col.x;
        bestY = y;
      }
    }
  }
  return {
    concentration_kg_per_m3: out,
    rows: ny,
    cols: nx,
    max_concentration_kg_per_m3: Math.max(best, 0),
    max_x_m: bestX,
    max_y_m: bestY,
  };
}
