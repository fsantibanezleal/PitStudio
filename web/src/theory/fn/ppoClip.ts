// PPO clipped surrogate objective (FR-020-49): min(r A, clip(r, 1 - eps, 1 + eps) A), Schulman et al.,
// arXiv:1707.06347, eq. 7.
import { finite, nonNegative } from "./guard";

export function ppoClip({ r, A, eps }: { r: number; A: number; eps: number }): number {
  nonNegative("r", r);
  finite("A", A);
  finite("eps", eps);
  if (!(eps > 0 && eps < 1)) throw new RangeError("eps must be in the open interval (0, 1)");
  const clipped = Math.min(Math.max(r, 1 - eps), 1 + eps);
  return Math.min(r * A, clipped * A);
}
