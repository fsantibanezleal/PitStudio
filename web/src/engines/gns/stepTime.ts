// Step-time bookkeeping of the GNS scene (NFR-011-02): the median of the last 100 steps and the T2 particle cap, the largest
// particle count whose median step time met the budget. Pure and dependency free.

export const WINDOW = 100;

/** Median of a list of numbers; NaN for an empty list. Finite values only: others are ignored. */
export function median(values: readonly number[]): number {
  const v = values.filter((x) => Number.isFinite(x)).sort((a, b) => a - b);
  if (v.length === 0) return Number.NaN;
  const mid = v.length >> 1;
  return v.length % 2 === 1 ? (v[mid] as number) : ((v[mid - 1] as number) + (v[mid] as number)) / 2;
}

/** A ring of the last `size` step times. */
export class StepTimer {
  private readonly times: number[] = [];

  constructor(private readonly size: number = WINDOW) {}

  record(ms: number): void {
    if (!Number.isFinite(ms) || ms < 0) return;
    this.times.push(ms);
    if (this.times.length > this.size) this.times.shift();
  }

  get count(): number {
    return this.times.length;
  }

  /** The median of the recorded window, NaN before the first step. */
  median(): number {
    return median(this.times);
  }
}

export interface CapMeasurement {
  particles: number;
  medianMs: number;
}

/**
 * The T2 particle cap: the largest measured particle count whose median step time is within the budget, never above `engineCap`
 * (5,000 particles in the table of spec 018). Null when no measured count met the budget (nothing is claimed then).
 */
export function particleCap(
  measurements: readonly CapMeasurement[],
  budgetMs: number,
  engineCap: number,
): number | null {
  let best: number | null = null;
  for (const m of measurements) {
    if (!Number.isFinite(m.medianMs) || !Number.isInteger(m.particles) || m.particles < 1) continue;
    if (m.medianMs <= budgetMs && m.particles <= engineCap && (best === null || m.particles > best))
      best = m.particles;
  }
  return best;
}
