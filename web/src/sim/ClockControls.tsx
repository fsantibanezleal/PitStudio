import { type KeyboardEvent, useEffect, useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import styles from "~/cases/cases.module.css";
import "~/shell/i18n";
import type { SimClock } from "./clock";

/** Re-renders with the clock state, and ticks the clock on every animation frame while it plays. */
export function useClockState(clock: SimClock) {
  const state = useSyncExternalStore(
    (listener) => clock.subscribe(listener),
    () => clock.getState(),
    () => clock.getState(),
  );
  useEffect(() => {
    if (!state.playing || typeof requestAnimationFrame !== "function") return;
    let frame = 0;
    const loop = () => {
      clock.tick();
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [clock, state.playing]);
  return state;
}

/**
 * Play or pause, step back and forward by one frame, and a Time slider (FR-018-22). The slider takes the arrows (one frame),
 * Home and End; its key handler stops the browser's own range stepping so a key never moves the clock twice.
 */
export function ClockControls({ clock }: { clock: SimClock }) {
  const { t } = useTranslation("cases");
  const state = useClockState(clock);

  const onSliderKey = (event: KeyboardEvent<HTMLInputElement>) => {
    const key = event.key;
    if (key === "ArrowRight" || key === "ArrowUp") clock.step(1);
    else if (key === "ArrowLeft" || key === "ArrowDown") clock.step(-1);
    else if (key === "Home") clock.seek(0);
    else if (key === "End") clock.seek(clock.duration);
    else return;
    event.preventDefault();
  };

  return (
    <div
      className={styles.clock}
      data-testid="sim-clock"
      data-t={state.t}
      data-playing={state.playing}
      data-duration={clock.duration}
    >
      <button type="button" className={styles.button} onClick={() => clock.toggle()}>
        {state.playing ? t("clock.pause") : t("clock.play")}
      </button>
      <button type="button" className={styles.button} onClick={() => clock.step(-1)}>
        {t("clock.stepBack")}
      </button>
      <button type="button" className={styles.button} onClick={() => clock.step(1)}>
        {t("clock.stepForward")}
      </button>
      <input
        type="range"
        aria-label={t("clock.time")}
        min={0}
        max={clock.duration}
        step={1 / clock.fps}
        value={state.t}
        aria-valuenow={state.t}
        aria-valuetext={t("clock.seconds", { t: state.t.toFixed(2) })}
        onChange={(event) => clock.seek(Number(event.target.value))}
        onKeyDown={onSliderKey}
      />
      <output className={styles.unit}>{t("clock.seconds", { t: state.t.toFixed(2) })}</output>
    </div>
  );
}
