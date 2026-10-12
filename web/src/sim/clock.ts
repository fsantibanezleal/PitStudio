// The simulation clock of a page (FR-018-21, FR-018-22, FR-018-68): paused at t = 0 until the user plays it, with play, pause,
// step by one frame and scrub. Every view (video, replay frame, chart cursor) reads it; none starts it. The wall time comes from
// an injected source, so the same code runs on a fake one in the tests. Hostile calls are ignored, never thrown.

export interface TimeSource {
  /** Wall-clock time in seconds. */
  now(): number;
}

export interface ClockState {
  t: number;
  rate: number;
  playing: boolean;
}

export interface SimClock {
  getState(): ClockState;
  /** Settles the elapsed wall time: while playing, t += min(rate * dt, D - t). */
  tick(): void;
  play(): void;
  pause(): void;
  toggle(): void;
  /** Scrub: clamps to the duration; ignores non-finite, negative and non-number values. */
  seek(t: number): void;
  /** One frame (1 / fps seconds) forwards or backwards, clamped to [0, duration]; any other value is ignored. */
  step(direction: 1 | -1): void;
  /** Ignores non-finite, negative and non-number values (0 is valid: the clock plays without moving). */
  setRate(rate: number): void;
  subscribe(listener: (state: ClockState) => void): () => void;
  readonly duration: number;
  readonly fps: number;
}

const isPositiveFinite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n) && n > 0;
const isNonNegativeFinite = (n: unknown): n is number =>
  typeof n === "number" && Number.isFinite(n) && n >= 0;

export function createClock(opts: { duration: number; fps?: number; timeSource: TimeSource }): SimClock {
  if (!isPositiveFinite(opts?.duration)) throw new RangeError("duration must be a finite number > 0");
  const fps = opts.fps === undefined ? 10 : opts.fps;
  if (!isPositiveFinite(fps)) throw new RangeError("fps must be a finite number > 0");
  const duration = opts.duration;
  const source = opts.timeSource;

  let state: ClockState = { t: 0, rate: 1, playing: false };
  let last = 0;
  const listeners = new Set<(s: ClockState) => void>();

  const publish = (next: ClockState) => {
    if (next.t === state.t && next.rate === state.rate && next.playing === state.playing) return;
    state = next;
    for (const listener of [...listeners]) listener(state);
  };

  /** Banks the wall time that passed while playing. Returns the state to build on (not yet published). */
  const settle = (): ClockState => {
    if (!state.playing) return state;
    const now = source.now();
    const dt = now - last;
    last = now;
    if (!(dt > 0)) return state;
    return { ...state, t: Math.min(state.t + state.rate * dt, duration) };
  };

  const tick = () => publish(settle());
  const play = () => {
    const base = settle();
    if (base.playing) {
      publish(base);
      return;
    }
    last = source.now();
    publish({ ...base, playing: true });
  };
  const pause = () => publish({ ...settle(), playing: false });

  return {
    duration,
    fps,
    getState: () => state,
    tick,
    play,
    pause,
    toggle: () => (state.playing ? pause() : play()),
    seek(t) {
      if (!isNonNegativeFinite(t)) return;
      publish({ ...settle(), t: Math.min(t, duration) });
    },
    step(direction) {
      if (direction !== 1 && direction !== -1) return;
      const base = settle();
      publish({ ...base, t: Math.min(duration, Math.max(0, base.t + direction / fps)) });
    },
    setRate(rate) {
      if (!isNonNegativeFinite(rate)) return;
      publish({ ...settle(), rate });
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
/** The clock's wall time source in the browser: performance.now() in seconds. */
export const performanceTime: TimeSource = { now: () => performance.now() / 1000 };
