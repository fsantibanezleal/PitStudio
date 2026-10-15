// Standard normal CDF and its inverse in double precision (spec 018 section 4: normal and lognormal variates by inverse CDF).
// Phi through erfc (Numerical Recipes Chebyshev fit, relative error below 1.2e-16); Phi^-1 by Wichura's AS241 (PPND16).

/** erfc(x) with relative error below 1.2e-7 scaled by a Chebyshev refinement; see Numerical Recipes 3rd ed. erfccheb. */
const ERFC_COF = [
  -1.3026537197817094, 0.6419697923564902, 0.019476473204185836, -0.00956151478680863, -9.46595344482036e-4,
  3.66839497852761e-4, 4.2523324806907e-5, -2.0278578112534e-5, -1.624290004647e-6, 1.30365583558e-6,
  1.5626441722e-8, -8.5238095915e-8, 6.529054439e-9, 5.059343495e-9, -9.91364156e-10, -2.27365122e-10,
  9.6467911e-11, 2.394038e-12, -6.886027e-12, 8.94487e-13, 3.13092e-13, -1.12708e-13, 3.81e-16, 7.106e-15,
  -1.523e-15, -9.4e-17, 1.21e-16, -2.8e-17,
];

function erfccheb(z: number): number {
  let d = 0;
  let dd = 0;
  const t = 2 / (2 + z);
  const ty = 4 * t - 2;
  for (let j = ERFC_COF.length - 1; j > 0; j--) {
    const tmp = d;
    d = ty * d - dd + (ERFC_COF[j] as number);
    dd = tmp;
  }
  return t * Math.exp(-z * z + 0.5 * ((ERFC_COF[0] as number) + ty * d) - dd);
}

export function erfc(x: number): number {
  return x >= 0 ? erfccheb(x) : 2 - erfccheb(-x);
}

export function normalCdf(x: number): number {
  return 0.5 * erfc(-x / Math.SQRT2);
}

/** Inverse of the standard normal CDF, p in (0, 1). */
export function normalPpf(p: number): number {
  if (!(p > 0 && p < 1)) return p <= 0 ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY;
  const q = p - 0.5;
  if (Math.abs(q) <= 0.425) {
    const r = 0.180625 - q * q;
    return (
      (q *
        (((((((2509.0809287301227 * r + 33430.57558358813) * r + 67265.7709270087) * r + 45921.95393154987) *
          r +
          13731.69376550946) *
          r +
          1971.5909503065513) *
          r +
          133.14166789178438) *
          r +
          3.3871328727963665)) /
      (((((((5226.495278852546 * r + 28729.085735721943) * r + 39307.89580009271) * r + 21213.794301586597) *
        r +
        5394.196021424751) *
        r +
        687.1870074920579) *
        r +
        42.31333070160091) *
        r +
        1)
    );
  }
  let r = q < 0 ? p : 1 - p;
  r = Math.sqrt(-Math.log(r));
  let val: number;
  if (r <= 5) {
    r -= 1.6;
    val =
      (((((((0.0007745450142783414 * r + 0.022723844989269184) * r + 0.2417807251774506) * r +
        1.2704582524523684) *
        r +
        3.6478483247632045) *
        r +
        5.769497221460691) *
        r +
        4.630337846156546) *
        r +
        1.4234371107496835) /
      (((((((1.0507500716444169e-9 * r + 0.0005475938084995345) * r + 0.015198666563616457) * r +
        0.14810397642748008) *
        r +
        0.6897673349851) *
        r +
        1.6763848301838038) *
        r +
        2.053191626637759) *
        r +
        1);
  } else {
    r -= 5;
    val =
      (((((((2.0103343992922881e-7 * r + 2.7115555687434876e-5) * r + 0.0012426609473880784) * r +
        0.026532189526576124) *
        r +
        0.29656057182850487) *
        r +
        1.7848265399172913) *
        r +
        5.463784911164114) *
        r +
        6.657904643501103) /
      (((((((2.0442631033899397e-15 * r + 1.421511758316446e-7) * r + 1.8463183175100548e-5) * r +
        0.0007868691311456133) *
        r +
        0.014875361290850615) *
        r +
        0.1369298809227358) *
        r +
        0.599832206555888) *
        r +
        1);
  }
  return q < 0 ? -val : val;
}
