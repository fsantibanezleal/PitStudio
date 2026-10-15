// Lidar range equation of an extended Lambertian target (FR-020-49): P = p0 rho A eta exp(-2 sigma R) / (pi R^2),
// with the two-way Beer-Lambert transmittance exp(-2 sigma R) (Weitkamp (ed.), Lidar, Springer 2005, chapter 1).
import { finite, nonNegative, positive } from "./guard";

type Common = { rho: number; sigma: number; p0?: number; area?: number; eta?: number };

function checkCommon({ rho, sigma, p0 = 1, area = 1, eta = 1 }: Common): void {
  finite("rho", rho);
  if (rho < 0 || rho > 1) throw new RangeError("rho must be in [0, 1]");
  nonNegative("sigma", sigma);
  positive("p0", p0);
  positive("area", area);
  positive("eta", eta);
}

/** Received power in W at range R (m). */
export function lidarRange(args: Common & { R: number }): number {
  const { R, rho, sigma, p0 = 1, area = 1, eta = 1 } = args;
  positive("R", R);
  checkCommon(args);
  return (p0 * rho * area * eta * Math.exp(-2 * sigma * R)) / (Math.PI * R * R);
}

/** Range in m where the received power falls to `threshold` (W): the root of lidarRange(R) = threshold. */
export function lidarMaxRange(args: Common & { threshold: number }): number {
  const { rho, sigma, threshold, p0 = 1, area = 1, eta = 1 } = args;
  positive("threshold", threshold);
  checkCommon(args);
  if (rho === 0) return 0;
  const k = (p0 * rho * area * eta) / (Math.PI * threshold);
  const r0 = Math.sqrt(k); // without extinction
  if (sigma === 0) return r0;
  // Solve g(u) = 2u + 2 sigma e^u - ln k = 0 with u = ln R; g increases strictly, g(ln r0) >= 0.
  const c = Math.log(k);
  const g = (u: number) => 2 * u + 2 * sigma * Math.exp(u) - c;
  let hi = Math.log(r0);
  let lo = hi - 1;
  while (g(lo) > 0) lo -= (hi - lo) * 2;
  for (let i = 0; i < 200; i++) {
    const mid = 0.5 * (lo + hi);
    if (g(mid) > 0) hi = mid;
    else lo = mid;
  }
  return Math.exp(0.5 * (lo + hi));
}
