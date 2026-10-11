import { type KeyboardEvent, type ReactNode, useRef } from "react";
import styles from "~/cases/cases.module.css";

export interface TabSpec {
  id: string;
  label: string;
}

export interface TabsProps {
  tabs: readonly TabSpec[];
  selected: string;
  onSelect: (id: string) => void;
  /** Unique prefix of the element ids on the page. */
  idBase: string;
  label: string;
  /** Content of the selected panel; the other panels stay empty and hidden. */
  children: ReactNode;
}

/**
 * WAI-ARIA tabs with manual activation: roving tabindex, arrow keys move focus (wrapping), Home and End jump to the
 * ends, Enter or Space select the focused tab. Every tab names its panel; only the selected panel is exposed.
 */
export function Tabs({ tabs, selected, onSelect, idBase, label, children }: TabsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (index: number) => {
    const target = (index + tabs.length) % tabs.length;
    refs.current[target]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent, index: number) => {
    const keys: Record<string, number> = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    const next = keys[event.key];
    if (next === undefined) return;
    event.preventDefault();
    move(next);
  };

  return (
    <div className={styles.tabs}>
      <div role="tablist" aria-label={label} className={styles.tabList}>
        {tabs.map((tab, index) => {
          const active = tab.id === selected;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[index] = el;
              }}
              type="button"
              role="tab"
              id={`${idBase}-tab-${tab.id}`}
              aria-selected={active}
              aria-controls={`${idBase}-panel-${tab.id}`}
              tabIndex={active ? 0 : -1}
              className={styles.tab}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(event) => onKeyDown(event, index)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => {
        const active = tab.id === selected;
        return (
          <div
            key={tab.id}
            role="tabpanel"
            id={`${idBase}-panel-${tab.id}`}
            aria-labelledby={`${idBase}-tab-${tab.id}`}
            hidden={!active}
            className={styles.tabPanel}
          >
            {active ? children : null}
          </div>
        );
      })}
    </div>
  );
}
