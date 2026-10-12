// T-018-040 [red] · FR-018-21 (paused at t = 0 by default), FR-018-22 (play, pause, step, scrub by keyboard), FR-018-68 (hostile
// calls), P-018-01, P-018-02, P-018-03 (clock properties on a fake time source).
//
// Expected API
//   module `~/sim/clock` (web/src/sim/clock.ts):
//     interface TimeSource { now(): number }                    wall-clock time in SECONDS (the app wraps performance.now() / 1000)
//     interface ClockState { t: number; rate: number; playing: boolean }       t in seconds, rate >= 0
//     createClock(opts: { duration: number; fps?: number; timeSource: TimeSource }): SimClock
//         duration D > 0 finite, fps > 0 finite (default 10); otherwise RangeError. Starts paused at t = 0, rate 1.
//     SimClock:
//         getState(): ClockState                                state as of the last settle
//         tick(): void                                          settles elapsed wall time: while playing, t += min(rate * dt, D - t)
//         play(): void   pause(): void   toggle(): void
//         seek(t: number): void                                 scrub; clamps to D; ignores non-finite, negative and non-number values
//         step(direction: 1 | -1): void                         moves by direction / fps seconds, clamped to [0, D]; other values ignored
//         setRate(rate: number): void                           ignores non-finite, negative and non-number values (0 is valid)
//         subscribe(listener: (s: ClockState) => void): () => void      called after every call that changed the state
//         readonly duration: number; readonly fps: number
//       Every operation first settles the elapsed time (as tick() does), so pause() banks the time that passed while playing.
//   module `~/sim/ClockControls` (web/src/sim/ClockControls.tsx): default-less named export ClockControls({ clock: SimClock }):
//       a button named "Play" (named "Pause" while playing), buttons "Step back" and "Step forward", and an input range named
//       "Time" (role slider, min 0, max = duration, step = 1 / fps, aria-valuenow = t). Keyboard on the slider: ArrowRight and
//       ArrowUp step forward, ArrowLeft and ArrowDown step back, Home -> 0, End -> duration. Enter or Space on a button activates it. The slider's key handler calls
//       preventDefault, so the browser's own range stepping never applies a second step.
//
// Oracles: the EARS text of FR-018-21/22/68; P-018-01..03 as written in spec section 4, checked against an independent model
// state machine written in this file (t = min(t + r * dt, D) while playing) on dyadic numbers, where binary64 arithmetic is exact.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fc from "fast-check";
import { createElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { ClockControls } from "~/sim/ClockControls";
import { createClock } from "~/sim/clock";

function fakeSource(start = 0) {
  let now = start;
  return {
    now: () => now,
    advance(seconds: number) {
      now += seconds;
    },
  };
}

describe("default state (FR-018-21)", () => {
  it("FR-018-21 · a new clock is paused at t = 0 with rate 1", () => {
    const clock = createClock({ duration: 60, timeSource: fakeSource() });
    expect(clock.getState()).toEqual({ t: 0, rate: 1, playing: false });
    expect(clock.duration).toBe(60);
    expect(clock.fps).toBe(10);
  });

  it("FR-018-21 · 10 s of wall time pass and nothing moves: t stays 0, playing stays false, no subscriber is called", () => {
    const source = fakeSource();
    const clock = createClock({ duration: 60, timeSource: source });
    const listener = vi.fn();
    clock.subscribe(listener);
    for (let i = 0; i < 100; i++) {
      source.advance(0.1);
      clock.tick();
    }
    expect(clock.getState()).toEqual({ t: 0, rate: 1, playing: false });
    expect(listener).not.toHaveBeenCalled();
  });

  it("FR-018-22 · fps comes from the options (registry value) and defaults to 10", () => {
    expect(createClock({ duration: 5, fps: 25, timeSource: fakeSource() }).fps).toBe(25);
    expect(createClock({ duration: 5, timeSource: fakeSource() }).fps).toBe(10);
  });

  for (const duration of [0, -1, Number.NaN, Number.POSITIVE_INFINITY, "60", null]) {
    it(`FR-018-68 · createClock rejects the duration ${String(duration)} with a RangeError`, () => {
      expect(() => createClock({ duration: duration as number, timeSource: fakeSource() })).toThrow(
        RangeError,
      );
    });
  }
  for (const fps of [0, -5, Number.NaN, Number.POSITIVE_INFINITY]) {
    it(`FR-018-68 · createClock rejects the fps ${fps} with a RangeError`, () => {
      expect(() => createClock({ duration: 10, fps, timeSource: fakeSource() })).toThrow(RangeError);
    });
  }
});

describe("play, pause, step, scrub (FR-018-22)", () => {
  it("FR-018-22 · playing at rate 1 for 2.5 s moves t by 2.5 s; pause banks the time and later time does not count", () => {
    const source = fakeSource();
    const clock = createClock({ duration: 60, timeSource: source });
    clock.play();
    expect(clock.getState().playing).toBe(true);
    source.advance(2.5);
    clock.pause();
    expect(clock.getState()).toEqual({ t: 2.5, rate: 1, playing: false });
    source.advance(100);
    clock.tick();
    expect(clock.getState().t).toBe(2.5);
  });

  it("FR-018-22 · rate 4 advances four times faster", () => {
    const source = fakeSource();
    const clock = createClock({ duration: 60, timeSource: source });
    clock.setRate(4);
    clock.play();
    source.advance(1.5);
    clock.tick();
    expect(clock.getState().t).toBe(6);
  });

  it("FR-018-22 · toggle alternates play and pause", () => {
    const clock = createClock({ duration: 60, timeSource: fakeSource() });
    clock.toggle();
    expect(clock.getState().playing).toBe(true);
    clock.toggle();
    expect(clock.getState().playing).toBe(false);
  });

  it("FR-018-22 · step moves by exactly 1/fps seconds, forward and back, and stops at 0 and at D", () => {
    const clock = createClock({ duration: 1, fps: 8, timeSource: fakeSource() });
    clock.step(1);
    expect(clock.getState().t).toBe(0.125);
    clock.step(1);
    expect(clock.getState().t).toBe(0.25);
    clock.step(-1);
    expect(clock.getState().t).toBe(0.125);
    clock.step(-1);
    clock.step(-1);
    expect(clock.getState().t).toBe(0);
    clock.seek(1);
    clock.step(1);
    expect(clock.getState().t).toBe(1);
  });

  it("FR-018-22 · the default step at 10 fps is 0.1 s", () => {
    const clock = createClock({ duration: 10, timeSource: fakeSource() });
    clock.step(1);
    expect(clock.getState().t).toBeCloseTo(0.1, 12);
  });

  it("FR-018-22 · scrub sets t, also while playing, and playing continues from the new time", () => {
    const source = fakeSource();
    const clock = createClock({ duration: 60, timeSource: source });
    clock.play();
    source.advance(1);
    clock.seek(30);
    source.advance(2);
    clock.tick();
    expect(clock.getState().t).toBe(32);
  });

  it("FR-018-22 · subscribers hear about every change and stop after unsubscribing", () => {
    const clock = createClock({ duration: 60, timeSource: fakeSource() });
    const listener = vi.fn();
    const off = clock.subscribe(listener);
    clock.play();
    clock.seek(5);
    clock.setRate(2);
    expect(listener).toHaveBeenCalledTimes(3);
    expect(listener).toHaveBeenLastCalledWith({ t: 5, rate: 2, playing: true });
    off();
    clock.pause();
    expect(listener).toHaveBeenCalledTimes(3);
  });
});

describe("hostile calls (FR-018-68)", () => {
  const badTimes: Array<[string, unknown]> = [
    ["NaN", Number.NaN],
    ["-1", -1],
    ["-0.001", -0.001],
    ["+Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
    ["a string", "5"],
    ["undefined", undefined],
    ["null", null],
    ["an object", { valueOf: () => 5 }],
  ];
  for (const [name, value] of badTimes) {
    it(`FR-018-68 · seek(${name}) is ignored: state and subscribers are untouched`, () => {
      const clock = createClock({ duration: 60, timeSource: fakeSource() });
      clock.seek(12);
      const listener = vi.fn();
      clock.subscribe(listener);
      clock.seek(value as number);
      expect(clock.getState()).toEqual({ t: 12, rate: 1, playing: false });
      expect(listener).not.toHaveBeenCalled();
    });
  }

  const badRates: Array<[string, unknown]> = [
    ["-2", -2],
    ["NaN", Number.NaN],
    ["+Infinity", Number.POSITIVE_INFINITY],
    ["-Infinity", Number.NEGATIVE_INFINITY],
    ["a string", "2"],
    ["undefined", undefined],
  ];
  for (const [name, value] of badRates) {
    it(`FR-018-68 · setRate(${name}) is ignored`, () => {
      const clock = createClock({ duration: 60, timeSource: fakeSource() });
      clock.setRate(3);
      clock.setRate(value as number);
      expect(clock.getState().rate).toBe(3);
    });
  }

  it("FR-018-68 · a seek beyond the duration D clamps to D; seek(D) is D", () => {
    const clock = createClock({ duration: 60, timeSource: fakeSource() });
    clock.seek(61);
    expect(clock.getState().t).toBe(60);
    clock.seek(1e300);
    expect(clock.getState().t).toBe(60);
    clock.seek(0);
    clock.seek(60);
    expect(clock.getState().t).toBe(60);
  });

  it("FR-018-68 · rate 0 is valid: the clock plays without moving", () => {
    const source = fakeSource();
    const clock = createClock({ duration: 60, timeSource: source });
    clock.setRate(0);
    clock.play();
    source.advance(5);
    clock.tick();
    expect(clock.getState()).toEqual({ t: 0, rate: 0, playing: true });
  });

  it("FR-018-68 · a step with a direction other than 1 or -1 is ignored", () => {
    const clock = createClock({ duration: 60, timeSource: fakeSource() });
    clock.seek(5);
    for (const d of [0, 2, -2, Number.NaN, "1", undefined]) clock.step(d as 1);
    expect(clock.getState().t).toBe(5);
  });

  it("FR-018-68 · property: any sequence of arbitrary calls leaves t in [0, D], rate finite and non-negative, and never throws", () => {
    const arbitrary = fc.oneof(
      fc.double(),
      fc.integer(),
      fc.constantFrom(Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY, -0, 0, 1e308),
    );
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.record({ op: fc.constant("seek"), v: arbitrary }),
            fc.record({ op: fc.constant("rate"), v: arbitrary }),
            fc.record({ op: fc.constant("play"), v: fc.constant(0) }),
            fc.record({ op: fc.constant("pause"), v: fc.constant(0) }),
            fc.record({ op: fc.constant("step"), v: fc.constantFrom(1, -1) }),
            fc.record({ op: fc.constant("wait"), v: fc.double({ min: 0, max: 5, noNaN: true }) }),
          ),
          { maxLength: 100 },
        ),
        (ops) => {
          const source = fakeSource();
          const clock = createClock({ duration: 37, timeSource: source });
          for (const { op, v } of ops) {
            if (op === "seek") clock.seek(v);
            else if (op === "rate") clock.setRate(v);
            else if (op === "play") clock.play();
            else if (op === "pause") clock.pause();
            else if (op === "step") clock.step(v as 1 | -1);
            else {
              source.advance(v);
              clock.tick();
            }
            const s = clock.getState();
            if (!(s.t >= 0 && s.t <= 37 && Number.isFinite(s.rate) && s.rate >= 0)) return false;
          }
          return true;
        },
      ),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Properties against an independent model (dyadic numbers, so binary64 arithmetic is exact)
// ---------------------------------------------------------------------------------------------------------------------
const D = 64;
const FPS = 8; // step = 0.125
const RATES = [0, 0.25, 0.5, 1, 1.5, 2, 4, 8];
type Op =
  | { op: "play" }
  | { op: "pause" }
  | { op: "seek"; t: number }
  | { op: "step"; d: 1 | -1 }
  | { op: "rate"; r: number }
  | { op: "wait"; dt: number };

const opArb: fc.Arbitrary<Op> = fc.oneof(
  fc.constant<Op>({ op: "play" }),
  fc.constant<Op>({ op: "pause" }),
  fc.integer({ min: 0, max: D * 8 }).map((k): Op => ({ op: "seek", t: k / 8 })),
  fc.constantFrom<1 | -1>(1, -1).map((d): Op => ({ op: "step", d })),
  fc.constantFrom(...RATES).map((r): Op => ({ op: "rate", r })),
  fc.integer({ min: 0, max: 32 }).map((k): Op => ({ op: "wait", dt: k / 8 })), // dyadic in [0, 4] s
);

describe("clock properties (P-018-01, P-018-02, P-018-03)", () => {
  it("P-018-01 · for any sequence of play, pause, seek, step, rate and wait operations t follows min(t + r dt, D) exactly and stays in [0, D]", () => {
    fc.assert(
      fc.property(fc.array(opArb, { maxLength: 200 }), (ops) => {
        const source = fakeSource();
        const clock = createClock({ duration: D, fps: FPS, timeSource: source });
        let t = 0;
        let rate = 1;
        let playing = false;
        for (const o of ops) {
          if (o.op === "play") {
            clock.play();
            playing = true;
          } else if (o.op === "pause") {
            clock.pause();
            playing = false;
          } else if (o.op === "seek") {
            clock.seek(o.t);
            t = o.t;
          } else if (o.op === "step") {
            clock.step(o.d);
            t = Math.min(D, Math.max(0, t + o.d / FPS));
          } else if (o.op === "rate") {
            clock.setRate(o.r);
            rate = o.r;
          } else {
            source.advance(o.dt);
            clock.tick();
            if (playing) t = Math.min(t + rate * o.dt, D);
          }
          const s = clock.getState();
          if (s.t !== t || s.t < 0 || s.t > D || s.rate !== rate) return false;
        }
        return true;
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-02 · doubling the rate for the same wall intervals doubles the advance until the clamp at D", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...RATES.filter((r) => r > 0 && r <= 4)),
        fc.array(
          fc.integer({ min: 0, max: 32 }).map((k) => k / 8),
          { minLength: 1, maxLength: 20 },
        ),
        (r, waits) => {
          const run = (rate: number) => {
            const source = fakeSource();
            const clock = createClock({ duration: D, fps: FPS, timeSource: source });
            clock.setRate(rate);
            clock.play();
            for (const dt of waits) {
              source.advance(dt);
              clock.tick();
            }
            return clock.getState().t;
          };
          const slow = run(r);
          const fast = run(2 * r);
          const total = waits.reduce((a, b) => a + b, 0);
          return 2 * r * total <= D ? fast === 2 * slow : fast === D;
        },
      ),
      { numRuns: 200 },
    );
  });

  it("P-018-03 · seek(t) twice equals seek(t) once", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: D * 8 }), (k) => {
        const t = k / 8;
        const once = createClock({ duration: D, fps: FPS, timeSource: fakeSource() });
        once.seek(t);
        const twice = createClock({ duration: D, fps: FPS, timeSource: fakeSource() });
        twice.seek(t);
        twice.seek(t);
        return JSON.stringify(once.getState()) === JSON.stringify(twice.getState());
      }),
      { numRuns: 200 },
    );
  });

  it("P-018-03 · pause, then play and pause with zero elapsed time, leaves t unchanged", () => {
    fc.assert(
      fc.property(fc.integer({ min: 0, max: D * 8 }), fc.constantFrom(...RATES), (k, r) => {
        const source = fakeSource();
        const clock = createClock({ duration: D, fps: FPS, timeSource: source });
        clock.setRate(r);
        clock.seek(k / 8);
        clock.pause();
        clock.play();
        clock.pause();
        return clock.getState().t === k / 8 && !clock.getState().playing;
      }),
      { numRuns: 200 },
    );
  });
});

// ---------------------------------------------------------------------------------------------------------------------
// Keyboard (FR-018-22)
// ---------------------------------------------------------------------------------------------------------------------
describe("keyboard controls (FR-018-22)", () => {
  function setup(fps = 10, duration = 12) {
    const source = fakeSource();
    const clock = createClock({ duration, fps, timeSource: source });
    render(createElement(ClockControls, { clock }));
    return { clock, source, user: userEvent.setup() };
  }

  it("FR-018-22 · the controls expose Play, Step back, Step forward and a Time slider by role and name", () => {
    setup();
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Step back" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Step forward" })).toBeTruthy();
    const slider = screen.getByRole("slider", { name: "Time" });
    expect(slider.getAttribute("min")).toBe("0");
    expect(slider.getAttribute("max")).toBe("12");
    expect(Number(slider.getAttribute("step"))).toBeCloseTo(0.1, 12);
    expect(Number(slider.getAttribute("aria-valuenow") ?? (slider as HTMLInputElement).value)).toBe(0);
  });

  it("FR-018-22 · Tab reaches the controls and Enter or Space on Play starts and pauses the clock; the button name follows", async () => {
    const { clock, user } = setup();
    await user.tab();
    const play = screen.getByRole("button", { name: "Play" });
    expect(document.activeElement === play || document.activeElement?.tagName === "BUTTON").toBe(true);
    play.focus();
    await user.keyboard("{Enter}");
    expect(clock.getState().playing).toBe(true);
    const pause = screen.getByRole("button", { name: "Pause" });
    pause.focus();
    await user.keyboard(" ");
    expect(clock.getState().playing).toBe(false);
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
  });

  it("FR-018-22 · Enter on the step buttons steps by one frame", async () => {
    const { clock, user } = setup(8);
    screen.getByRole("button", { name: "Step forward" }).focus();
    await user.keyboard("{Enter}");
    await user.keyboard("{Enter}");
    expect(clock.getState().t).toBe(0.25);
    screen.getByRole("button", { name: "Step back" }).focus();
    await user.keyboard("{Enter}");
    expect(clock.getState().t).toBe(0.125);
  });

  it("FR-018-22 · on the Time slider the arrow keys step by one frame, Home goes to 0 and End to the duration", async () => {
    const { clock, user } = setup(8, 2);
    const slider = screen.getByRole("slider", { name: "Time" });
    slider.focus();
    await user.keyboard("{ArrowRight}");
    await user.keyboard("{ArrowUp}");
    expect(clock.getState().t).toBe(0.25);
    await user.keyboard("{ArrowLeft}");
    await user.keyboard("{ArrowDown}");
    expect(clock.getState().t).toBe(0);
    await user.keyboard("{End}");
    expect(clock.getState().t).toBe(2);
    await user.keyboard("{Home}");
    expect(clock.getState().t).toBe(0);
  });

  it("FR-018-22 · the slider follows the clock: after a seek its value is the new time", () => {
    const { clock } = setup(10, 12);
    act(() => clock.seek(7));
    const slider = screen.getByRole("slider", { name: "Time" }) as HTMLInputElement;
    expect(Number(slider.value)).toBe(7);
  });
});
