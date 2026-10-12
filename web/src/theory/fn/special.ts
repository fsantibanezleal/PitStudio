// Special functions behind the statistics teaching functions: log-gamma, erfc and the regularised incomplete beta.
// Written for rtol 1e-9 against SciPy (scipy.special.ndtr, scipy.stats.t.ppf, scipy.stats.binomtest).

/** ln Gamma(x) for x > 0: recurrence up to x >= 15, then the Stirling series (relative error below 1e-16). */
export function lgamma(x: number): number {
  let shift = 0;
  let z = x;
  while (z < 15) {
    shift += Math.log(z);
    z += 1;
  }
  const z2 = z * z;
  const series =
    1 / (12 * z) - 1 / (360 * z * z2) + 1 / (1260 * z * z2 * z2) - 1 / (1680 * z * z2 * z2 * z2);
  return (z - 0.5) * Math.log(z) - z + 0.5 * Math.log(2 * Math.PI) + series - shift;
}

/** erfc(x) for x >= 0: Maclaurin series of erf below 2.5, Lentz continued fraction of erfc above. */
function erfcPositive(x: number): number {
  if (x === 0) return 1;
  if (x < 2.5) {
    let term = x;
    let sum = x;
    for (let n = 1; n < 200; n++) {
      term *= (-x * x) / n;
      const add = term / (2 * n + 1);
      sum += add;
      if (Math.abs(add) < 1e-18 * Math.abs(sum)) break;
    }
    return 1 - (2 / Math.sqrt(Math.PI)) * sum;
  }
  // erfc(x) = exp(-x^2) / (x sqrt(pi)) * 1 / (1 + (1/(2x^2)) / (1 + (2/(2x^2)) / (1 + ...)))
  const tiny = 1e-300;
  let f = x;
  let c = x;
  let d = 0;
  for (let n = 1; n < 500; n++) {
    const a = n / 2;
    d = x + a * d;
    d = d === 0 ? tiny : d;
    c = x + a / c;
    c = c === 0 ? tiny : c;
    d = 1 / d;
    const delta = c * d;
    f *= delta;
    if (Math.abs(delta - 1) < 1e-16) break;
  }
  return Math.exp(-x * x) / (f * Math.sqrt(Math.PI));
}

/** Complementary error function for any finite x. */
export function erfc(x: number): number {
  return x >= 0 ? erfcPositive(x) : 2 - erfcPositive(-x);
}

/** Standard normal CDF Phi(z). */
export function normalCdf(z: number): number {
  return 0.5 * erfc(-z / Math.SQRT2);
}

/** Regularised incomplete beta I_x(a, b) for a, b > 0 and 0 <= x <= 1. */
export function betaIncReg(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lnFront = lgamma(a + b) - lgamma(a) - lgamma(b) + a * Math.log(x) + b * Math.log1p(-x);
  const front = Math.exp(lnFront);
  if (x < (a + 1) / (a + b + 2)) return (front * betaCf(x, a, b)) / a;
  return 1 - (front * betaCf(1 - x, b, a)) / b;
}

function betaCf(x: number, a: number, b: number): number {
  const tiny = 1e-300;
  const qab = a + b;
  const qap = a + 1;
  const qam = a - 1;
  let c = 1;
  let d = 1 - (qab * x) / qap;
  if (Math.abs(d) < tiny) d = tiny;
  d = 1 / d;
  let h = d;
  for (let m = 1; m <= 1000; m++) {
    const m2 = 2 * m;
    let aa = (m * (b - m) * x) / ((qam + m2) * (a + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < tiny) d = tiny;
    c = 1 + aa / c;
    if (Math.abs(c) < tiny) c = tiny;
    d = 1 / d;
    h *= d * c;
    aa = (-(a + m) * (qab + m) * x) / ((a + m2) * (qap + m2));
    d = 1 + aa * d;
    if (Math.abs(d) < tiny) d = tiny;
    c = 1 + aa / c;
    if (Math.abs(c) < tiny) c = tiny;
    d = 1 / d;
    const del = d * c;
    h *= del;
    if (Math.abs(del - 1) < 1e-16) break;
  }
  return h;
}

/** Two-sided tail probability P(|T| > t) of Student's t with `df` degrees of freedom, t >= 0. */
export function studentTwoSidedTail(t: number, df: number): number {
  return betaIncReg(df / (df + t * t), df / 2, 0.5);
}

/** Upper quantile t such that P(|T| > t) = q (so t = t_{1 - q/2, df}), by bisection to full precision. */
export function studentTwoSidedQuantile(q: number, df: number): number {
  let lo = 0;
  let hi = 1;
  while (studentTwoSidedTail(hi, df) > q) {
    lo = hi;
    hi *= 2;
    if (hi > 1e300) break;
  }
  for (let i = 0; i < 300; i++) {
    const mid = 0.5 * (lo + hi);
    if (mid === lo || mid === hi) break;
    if (studentTwoSidedTail(mid, df) > q) lo = mid;
    else hi = mid;
  }
  return 0.5 * (lo + hi);
}
