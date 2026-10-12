// Exact two-sided McNemar test (FR-020-49): p = min(1, 2 P(X <= min(b, c))), X ~ Binomial(b + c, 1/2).
import { lgamma } from "./special";

function count(name: string, v: unknown): number {
  if (typeof v !== "number" || !Number.isInteger(v) || v < 0) {
    throw new RangeError(`${name} must be an integer count of at least 0`);
  }
  return v;
}

export function mcnemar({ b, c }: { b: number; c: number }): number {
  count("b", b);
  count("c", c);
  const lo = Math.min(b, c);
  const hi = Math.max(b, c);
  const n = lo + hi;
  if (n === 0 || lo === hi) return 1;
  if (n <= 1000) {
    // Small n: forward recurrence from 2^-n, accurate to a few ulp.
    let t = 2 ** -n;
    let acc = t;
    for (let k = 0; k < lo; k++) {
      t *= (n - k) / (k + 1);
      acc += t;
    }
    return Math.min(1, 2 * acc);
  }
  // Sum P(X = k), k = lo..0, starting from the k = lo term in log space and stepping down.
  const lnTerm = lgamma(n + 1) - lgamma(lo + 1) - lgamma(hi + 1) - n * Math.LN2;
  let term = Math.exp(lnTerm);
  let sum = term;
  for (let k = lo; k > 0; k--) {
    term *= k / (n - k + 1);
    sum += term;
    if (term < sum * 1e-18) break;
  }
  return Math.min(1, 2 * sum);
}
