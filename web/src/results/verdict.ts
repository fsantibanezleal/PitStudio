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
  // The discordant counts of a McNemar table are integers >= 0.
  if (!Number.isInteger(b) || !Number.isInteger(c) || b < 0 || c < 0 || !finite(p)) return "unavailable";
  if (!(p < 0.05) || b === c) return "none";
  return b > c ? "challenger" : "baseline";
}

/** "single" exactly when the comparison rests on one real event (n === 1): no significance test is possible. */
export function singleEventVerdict(n: number): "single" | null {
  return n === 1 ? "single" : null;
}

/**
 * The words of the display. An unusable verdict prints no claim at all (FR-000-05); the names are used verbatim, so the
 * caller escapes them by rendering them as text.
 */
export function verdictLabel(verdict: Verdict | "single", challenger: string, baseline: string): string {
  switch (verdict) {
    case "challenger":
      return `${challenger} better than ${baseline}`;
    case "baseline":
      return `${baseline} better than ${challenger}`;
    case "none":
      return "no significant difference";
    case "single":
      return "single real event — no significance test";
    default:
      return "";
  }
}
