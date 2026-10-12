// Series in typed arrays (FR-020-15): the full data is copied into Float64Array once and every query (the nearest sample of the
// read-out, the visible slice) runs on the full data, never on the decimated points.

export interface Series {
  x: Float64Array;
  y: Float64Array;
  n: number;
}

/** x must be finite and non-decreasing; y may hold NaN for a gap. Lengths are equal and n >= 1. */
export function makeSeries(x: ArrayLike<number>, y: ArrayLike<number>): Series {
  if (x.length !== y.length)
    throw new RangeError(`x and y must have the same length, got ${x.length} and ${y.length}`);
  if (x.length < 1) throw new RangeError("a series needs at least one sample (x is empty)");
  const fx = Float64Array.from(x);
  const fy = Float64Array.from(y);
  for (let i = 0; i < fx.length; i++) {
    const v = fx[i] as number;
    if (!Number.isFinite(v)) throw new RangeError(`x must be finite, got ${v} at index ${i}`);
    if (i > 0 && v < (fx[i - 1] as number))
      throw new RangeError(`x must be non-decreasing, it drops at index ${i}`);
  }
  return { x: fx, y: fy, n: fx.length };
}

/** First index whose x is >= value (n when there is none). */
export function lowerBound(x: ArrayLike<number>, value: number): number {
  let lo = 0;
  let hi = x.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if ((x[mid] as number) < value) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The index of the sample whose x is nearest to `x` (the lower index on a tie), by binary search on the full data. */
export function nearestIndex(series: Series, x: number): number {
  const i = lowerBound(series.x, x);
  if (i <= 0) return 0;
  if (i >= series.n) return series.n - 1;
  const before = x - (series.x[i - 1] as number);
  const after = (series.x[i] as number) - x;
  return before <= after ? i - 1 : i;
}
