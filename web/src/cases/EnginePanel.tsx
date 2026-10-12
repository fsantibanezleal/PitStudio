import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./cases.module.css";
import { type ControlSpec, parseControl } from "./controls";

export type EngineState = "idle" | "loading" | "running" | "done" | "error" | "replay";
export type PanelTier = "t1" | "t2" | "t0";

export interface EnginePanelProps {
  engine: string;
  mode: "live" | "replay";
  state: EngineState;
  /** Engine requests sent so far: +1 per accepted request, never for a rejected input. */
  requests: number;
  tier: PanelTier;
  notice?: string | null;
  controls?: ControlSpec[];
  /** Called with the new value of a control once a value was accepted (or clamped to the cap). */
  onCommit?: (name: string, value: number) => void;
  /** Progress of a runtime download (bytes received of the manifest size), when one is under way. */
  children?: React.ReactNode;
}

interface Draft {
  text: string;
  /** The last valid value the control shows again after a rejected one. */
  valid: number;
  message: boolean;
  note: number | null;
}

/** A number as a plain decimal text (no digit grouping, so the message reads the same in every locale). */
const plain = (n: number): string => String(n);

function Control({
  spec,
  onCommit,
}: {
  spec: ControlSpec;
  onCommit?: (name: string, value: number) => void;
}) {
  const { t } = useTranslation("cases");
  const [draft, setDraft] = useState<Draft>({
    text: plain(spec.value),
    valid: spec.value,
    message: false,
    note: null,
  });

  const commit = () => {
    const parsed = parseControl(draft.text, spec);
    if (parsed.kind === "rejected") {
      setDraft({ text: plain(draft.valid), valid: draft.valid, message: true, note: null });
      return;
    }
    const changed = parsed.value !== draft.valid;
    setDraft({
      text: plain(parsed.value),
      valid: parsed.value,
      message: false,
      note: parsed.kind === "clamped" ? parsed.cap : null,
    });
    if (changed) onCommit?.(spec.name, parsed.value);
  };

  const label = t(`engine.control.${spec.name}`, { defaultValue: spec.name });
  const id = `control-${spec.name}`;
  return (
    <div className={styles.control}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        spellCheck={false}
        value={draft.text}
        data-control={spec.name}
        data-min={spec.min}
        data-max={spec.max}
        data-unit={spec.unit}
        data-cap={spec.cap}
        aria-invalid={draft.message}
        aria-describedby={draft.message ? `${id}-message` : undefined}
        onChange={(event) => setDraft({ ...draft, text: event.target.value })}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            commit();
          }
        }}
      />
      <span className={styles.unit}>{spec.unit}</span>
      {draft.message && (
        <output
          id={`${id}-message`}
          data-testid="control-message"
          data-control={spec.name}
          className={styles.controlMessage}
        >
          {t("engine.range", { min: plain(spec.min), max: plain(spec.max), unit: spec.unit })}
        </output>
      )}
      {draft.note !== null && (
        <output data-testid="control-note" data-control={spec.name} className={styles.controlNote}>
          {t("engine.capNote", { cap: plain(draft.note), unit: spec.unit })}
        </output>
      )}
    </div>
  );
}

/**
 * One engine of a case (FR-018-14): its lane badge (LIVE only for a result computed in this browser, REPLAY otherwise), the
 * state, the tier it runs on, the number of requests sent, a notice when there is one, and its numeric controls.
 */
export function EnginePanel(props: EnginePanelProps) {
  const { engine, mode, state, requests, tier, notice, controls, onCommit, children } = props;
  const { t } = useTranslation("cases");
  return (
    <section
      className={styles.panel}
      data-testid="engine-panel"
      data-engine={engine}
      data-state={state}
      data-requests={requests}
      data-tier={tier}
      aria-label={engine}
    >
      <div className={styles.chips}>
        <h3>{engine}</h3>
        <span className={styles.lane} data-lane={mode} data-testid="lane-badge">
          {mode === "live" ? t("lane.live") : t("lane.replay")}
        </span>
        <span className={styles.chip}>{t(`tier.${tier}`)}</span>
        <span className={styles.unit}>{t(`engine.state.${state}`)}</span>
      </div>
      {notice && (
        <p data-testid="engine-notice" className={styles.unit}>
          {notice}
        </p>
      )}
      {controls?.map((spec) => (
        <Control key={spec.name} spec={spec} onCommit={onCommit} />
      ))}
      {children}
    </section>
  );
}
