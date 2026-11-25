// Ritter dam break on a dry bed (FR-020-49): Ritter 1892; Stoker 1957. Dam at x = 0, reservoir depth h0 for x < 0.
import { finite, nonNegative, positive } from "./guard";

/** Depth h(x, t) in m; c0 = sqrt(g h0). */
export function ritter({ x, t, h0 }: { x: number; t: number; h0: number }, g = 9.80665): number {
  finite("x", x);
  nonNegative("t", t);
  positive("h0", h0);
  positive("g", g);
  if (t === 0) return x < 0 ? h0 : 0;
  const c0 = Math.sqrt(g * h0);
  if (x <= -c0 * t) return h0;
  if (x >= 2 * c0 * t) return 0;
  const r = 2 * c0 - x / t;
  return (r * r) / (9 * g);
}

/** Position of the wave front, 2 sqrt(g h0) t, in m. */
export function ritterFront({ t, h0 }: { t: number; h0: number }, g = 9.80665): number {
  nonNegative("t", t);
  positive("h0", h0);
  positive("g", g);
  return 2 * Math.sqrt(g * h0) * t;
}
