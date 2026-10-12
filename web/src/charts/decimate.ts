// Min/max-per-column decimation (FR-020-15): the series is cut into `columns` consecutive index ranges and each range keeps the
// index of its minimum and of its maximum, so a one-sample needle always survives. The statistics are computed on the full data.

/**
 * The indices of the samples to draw. Range j is [floor(j n / columns), floor((j + 1) n / columns)). With n <= 2 columns every
 * index is kept. NaN samples (gaps) are never chosen as an extreme; a range that is all NaN keeps its first index. Among equal
 * values the lowest index wins. The result is strictly increasing.
 */
export function decimate(y: ArrayLike<number>, columns: number): Uint32Array {
  if (typeof columns !== "number" || !Number.isInteger(columns) || columns < 1) {
    throw new RangeError(`columns must be an integer >= 1, got ${String(columns)}`);
  }
  const n = y.length;
  if (n <= 2 * columns) {
    const all = new Uint32Array(n);
    for (let i = 0; i < n; i++) all[i] = i;
    return all;
  }
  const out = new Uint32Array(2 * columns);
  let count = 0;
  for (let j = 0; j < columns; j++) {
    const a = Math.floor((j * n) / columns);
    const b = Math.floor(((j + 1) * n) / columns);
    let lo = -1;
    let hi = -1;
    let loValue = 0;
    let hiValue = 0;
    for (let i = a; i < b; i++) {
      const v = y[i] as number;
      if (Number.isNaN(v)) continue;
      if (lo < 0) {
        lo = i;
        hi = i;
        loValue = v;
        hiValue = v;
        continue;
      }
      if (v < loValue) {
        lo = i;
        loValue = v;
      }
      if (v > hiValue) {
        hi = i;
        hiValue = v;
      }
    }
    if (lo < 0) {
      out[count++] = a;
    } else if (lo === hi) {
      out[count++] = lo;
    } else if (lo < hi) {
      out[count++] = lo;
      out[count++] = hi;
    } else {
      out[count++] = hi;
      out[count++] = lo;
    }
  }
  return out.slice(0, count);
}
