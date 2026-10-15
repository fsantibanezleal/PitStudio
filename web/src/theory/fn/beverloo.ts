// Beverloo discharge (FR-020-49): W = C rho_b sqrt(g) (D - k d)^(5/2), Beverloo, Leniger and van de Velde,
// Chem. Eng. Sci. 15, 260-269, 1961.
import { positive } from "./guard";

export type BeverlooArgs = { D: number; d: number; C: number; k: number; rhoB: number };

/** Mass discharge rate in kg/s through an orifice of diameter D (m) for grains of diameter d (m); 0 when D <= k d. */
export function beverloo({ D, d, C, k, rhoB }: BeverlooArgs, g = 9.80665): number {
  positive("D", D);
  positive("d", d);
  positive("C", C);
  positive("k", k);
  positive("rhoB", rhoB);
  positive("g", g);
  const open = D - k * d;
  if (open <= 0) return 0;
  return C * rhoB * Math.sqrt(g) * open ** 2.5;
}
