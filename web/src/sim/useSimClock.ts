import { useEffect, useMemo } from "react";
import { createClock, performanceTime, type SimClock } from "./clock";

/** The page's default time axis when no replay media gives one (seconds). */
export const DEFAULT_DURATION_S = 60;
const MAX_PARAM = 2000;
const DECIMAL = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/;

/**
 * The time `?t=` asks for, or null when the parameter is absent or unusable (FR-018-42): a non-decimal, negative, non-finite or
 * over-long value is ignored; a larger one than the duration is clamped to it. No resource is ever requested from the value.
 */
export function parseTimeParam(raw: string | null | undefined, duration: number): number | null {
  if (typeof raw !== "string" || raw.length === 0 || raw.length > MAX_PARAM) return null;
  if (!DECIMAL.test(raw)) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.min(value, duration);
}

/** Exposes the page clock to the browser tests and to the console: `window.__pitstudio.clock`. */
export function exposeClock(clock: SimClock): void {
  const w = window as unknown as { __pitstudio?: Record<string, unknown> };
  w.__pitstudio = { ...(w.__pitstudio ?? {}), clock };
}

/**
 * The clock of a page: paused at t = 0, seeded from `?t=` once the page is hydrated (never played by the seed). A new duration or
 * frame rate makes a new clock.
 */
export function useSimClock(opts: { duration: number; fps: number; seed?: string | null }): SimClock {
  const { duration, fps, seed } = opts;
  const clock = useMemo(() => createClock({ duration, fps, timeSource: performanceTime }), [duration, fps]);
  useEffect(() => {
    exposeClock(clock);
  }, [clock]);
  useEffect(() => {
    const t = parseTimeParam(seed, clock.duration);
    if (t !== null) clock.seek(t);
  }, [clock, seed]);
  return clock;
}
