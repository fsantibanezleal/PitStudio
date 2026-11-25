// AUC of two equal-variance normal score distributions (FR-020-49): AUC = Phi(deltaMu / (sigma sqrt 2)).
import { finite, positive } from "./guard";
import { normalCdf } from "./special";

export function gaussianAuc({ deltaMu, sigma }: { deltaMu: number; sigma: number }): number {
  finite("deltaMu", deltaMu);
  positive("sigma", sigma);
  const z = deltaMu / (sigma * Math.SQRT2);
  return normalCdf(Number.isFinite(z) ? z : Math.sign(deltaMu) * 1e3);
}
