import { useId, useState } from "react";
import type { Range } from "~/engines/surrogates/envelope";
import styles from "./surrogates.module.css";

/**
 * A numeric control of a surrogate scene: a spin button whose `min` and `max` are the training range of DC-011-02. A value outside
 * the range is accepted (FR-011-11, FR-011-39: the scene still runs and labels the result as an extrapolation); a text that is not
 * a finite number keeps the last accepted value. `onChange` is called with every newly accepted value, on blur or Enter.
 */
export function NumberControl({
  label,
  value,
  range,
  step = "any",
  max,
  onChange,
}: {
  label: string;
  value: number;
  range: Range;
  step?: string;
  /** The `max` attribute when it differs from the training range (an engine size cap). */
  max?: number;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const [text, setText] = useState(String(value));
  const commit = () => {
    const parsed = Number(text.trim());
    if (text.trim() === "" || !Number.isFinite(parsed)) {
      setText(String(value));
      return;
    }
    setText(String(parsed));
    if (parsed !== value) onChange(parsed);
  };
  return (
    <div className={styles.control}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        inputMode="decimal"
        step={step}
        min={range.min}
        max={max ?? range.max}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
        }}
      />
    </div>
  );
}
