// Slope-radar line of sight: the projection of each displacement on the unit vector from the radar to its target, positive
// away from the radar. Port of minephys.geotech.slope_radar_los (FR-018-51).
import { rangeError, schemaError } from "../errors";
import { asArray, asNumber, asObject } from "../validate";

function buffer(value: unknown, name: string): ArrayLike<number> {
  if (value instanceof Float64Array) return value;
  if (Array.isArray(value)) return value as number[];
  throw schemaError(`${name} must be a Float64Array or a number array`);
}

export function slope_radar_los(args: Record<string, unknown>): { los_m: Float64Array } {
  const a = asObject(args, "args");
  const rp = asArray(a.radar_position_m, "radar_position_m", 3, 3).map((v, i) =>
    asNumber(v, `radar_position_m[${i}]`, { lo: -1e7, hi: 1e7 }),
  ) as [number, number, number];
  const targets = buffer(a.targets_m, "targets_m");
  const disp = buffer(a.displacements_m, "displacements_m");
  if (targets.length !== disp.length || targets.length === 0 || targets.length % 3 !== 0)
    throw schemaError("targets_m and displacements_m must have the same length, a positive multiple of 3");
  const pixels = targets.length / 3;
  const los = new Float64Array(pixels);
  for (let p = 0; p < pixels; p++) {
    const d = [0, 0, 0];
    const u = [0, 0, 0];
    for (let k = 0; k < 3; k++) {
      const t = targets[3 * p + k] as number;
      const x = disp[3 * p + k] as number;
      if (!Number.isFinite(t) || !Number.isFinite(x)) throw rangeError(`pixel ${p} holds a non-finite value`);
      d[k] = t - (rp[k] as number);
      u[k] = x;
    }
    const scale = Math.max(Math.abs(d[0] as number), Math.abs(d[1] as number), Math.abs(d[2] as number));
    if (!Number.isFinite(scale)) throw rangeError("the radar-target vector overflows");
    if (scale === 0) throw rangeError("radar_position and the target must be distinct");
    const e = d.map((x) => x / scale);
    const norm = Math.sqrt((e[0] as number) ** 2 + (e[1] as number) ** 2 + (e[2] as number) ** 2);
    let proj = 0;
    for (let k = 0; k < 3; k++) proj += (u[k] as number) * ((e[k] as number) / norm);
    los[p] = proj;
  }
  return { los_m: los };
}
