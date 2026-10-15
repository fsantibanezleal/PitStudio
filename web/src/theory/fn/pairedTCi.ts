// Paired-t confidence interval (FR-020-49): mean -/+ t_{(1 + level)/2, n - 1} sd / sqrt(n).
import { finite } from "./guard";
import { studentTwoSidedQuantile } from "./special";

export function pairedTCi({
  n,
  mean,
  sd,
  level = 0.95,
}: {
  n: number;
  mean: number;
  sd: number;
  level?: number;
}): { lo: number; hi: number } {
  if (typeof n !== "number" || !Number.isInteger(n) || n < 2) {
    throw new RangeError("n must be an integer of at least 2");
  }
  finite("mean", mean);
  finite("sd", sd);
  if (sd < 0) throw new RangeError("sd must be at least 0");
  finite("level", level);
  if (!(level > 0 && level < 1)) throw new RangeError("level must be in the open interval (0, 1)");
  const half = (studentTwoSidedQuantile(1 - level, n - 1) * sd) / Math.sqrt(n);
  return { lo: mean - half, hi: mean + half };
}
