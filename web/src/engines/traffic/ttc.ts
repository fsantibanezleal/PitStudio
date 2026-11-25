// Constant-velocity time to collision and the near-miss rate of the `traffic` engine (FR-018-55, DC-018-02 function "ttc").
// p = position of b minus position of a, w = velocity of b minus velocity of a; TTC is the smallest positive root tau of
// |p + w tau| = R. Pure closed form: no Rapier, no randomness.
import { rangeError, schemaError } from "../analytical/errors";

const POSITION_LIMIT_M = 1e5;
const VELOCITY_LIMIT_M_PER_S = 60;

type Vec = [number, number];

export type TtcResult =
  | { status: "closing"; ttc_s: number }
  | { status: "overlapping"; ttc_s: 0 }
  | { status: "not-closing" };

function pair(value: unknown, name: string, limit: number): Vec {
  if (!Array.isArray(value) || value.length !== 2) throw schemaError(`${name} must be a pair of numbers`);
  for (const v of value) {
    if (typeof v !== "number") throw schemaError(`${name} must hold numbers`);
    if (!Number.isFinite(v)) throw rangeError(`${name} holds a non-finite number`);
    if (Math.abs(v) > limit) throw rangeError(`${name} component ${v} is beyond +-${limit}`);
  }
  return [value[0] as number, value[1] as number];
}

export function ttc(args: {
  relative_position_m: [number, number];
  relative_velocity_m_per_s: [number, number];
  radius_m: number;
}): TtcResult {
  if (args === null || typeof args !== "object") throw schemaError("args must be an object");
  const p = pair(args.relative_position_m, "relative_position_m", POSITION_LIMIT_M);
  const w = pair(args.relative_velocity_m_per_s, "relative_velocity_m_per_s", VELOCITY_LIMIT_M_PER_S);
  const radius = args.radius_m;
  if (typeof radius !== "number") throw schemaError("radius_m must be a number");
  if (!Number.isFinite(radius) || radius <= 0) throw rangeError("radius_m must be positive and finite");
  const pp = p[0] * p[0] + p[1] * p[1];
  if (pp <= radius * radius) return { status: "overlapping", ttc_s: 0 };
  const ww = w[0] * w[0] + w[1] * w[1];
  const pw = p[0] * w[0] + p[1] * w[1];
  if (ww === 0 || pw >= 0) return { status: "not-closing" };
  const gap = pp - radius * radius;
  const disc = pw * pw - ww * gap;
  if (disc < 0) return { status: "not-closing" };
  // the smaller root of ww tau^2 + 2 pw tau + gap = 0 as gap / (-pw + sqrt(disc)): no cancellation near a grazing contact
  return { status: "closing", ttc_s: gap / (-pw + Math.sqrt(disc)) };
}

/** Near-misses per 1,000 hours of exposure. */
export function nearMissesPer1000h(nearMisses: number, exposureSeconds: number): number {
  if (!Number.isInteger(nearMisses) || nearMisses < 0)
    throw new RangeError("the near-miss count must be a non-negative integer");
  if (!Number.isFinite(exposureSeconds) || exposureSeconds <= 0)
    throw new RangeError("the exposure must be positive and finite");
  return (nearMisses * 1000) / (exposureSeconds / 3600);
}
