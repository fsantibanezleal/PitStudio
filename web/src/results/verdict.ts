// The decision rule of FR-020-22. A verdict is always derived here from the interval or the counts; the stored
// `verdict` field of a results entry is never shown.

export type Verdict = "challenger" | "baseline" | "none" | "unavailable";

export interface Interval {
  lo: number;
  hi: number;
}

const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

/**
 * Paired comparison: the interval is oriented by the metric (flipped when lower is better); the challenger wins only
 * when the oriented lower bound is above 0, the baseline only when the oriented upper bound is below 0, and an
 * interval that touches 0 is no difference. A non-finite or reversed interval, or an unknown orientation, claims nothing.
 */
export function pairedVerdict(interval: Interval | undefined, orientation: string): Verdict {
  if (!interval || !finite(interval.lo) || !finite(interval.hi) || interval.lo > interval.hi)
    return "unavailable";
  if (orientation !== "higher-is-better" && orientation !== "lower-is-better") return "unavailable";
  const lo = orientation === "higher-is-better" ? interval.lo : -interval.hi;
  const hi = orientation === "higher-is-better" ? interval.hi : -interval.lo;
  if (lo > 0) return "challenger";
  if (hi < 0) return "baseline";
  return "none";
}

/** McNemar: p must be below 0.05; the direction comes from the discordant counts (b: challenger right, baseline wrong). */
export function mcnemarVerdict(b: number, c: number, p: number): Verdict {
  if (!finite(b) || !finite(c) || !finite(p)) return "unavailable";
  if (!(p < 0.05) || b === c) return "none";
  return b > c ? "challenger" : "baseline";
}
