import { Mountain } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "~/shell/shell.module.css";
import { ThemeToggle } from "~/shell/ThemeToggle";
import { BUILD_MARKER } from "./build-marker";
import { LanguageSelect, useLanguageSync } from "./LanguageSelect";
import { NewJob } from "./NewJob";
import { Queue } from "./Queue";
import { Recipes } from "./Recipes";
import { Runs } from "./Runs";

const TABS = [
  { id: "recipes", Panel: Recipes },
  { id: "queue", Panel: Queue },
  { id: "runs", Panel: Runs },
  { id: "newJob", Panel: NewJob },
] as const;
type TabId = (typeof TABS)[number]["id"];

export function App() {
  const { t } = useTranslation();
  const shell = useTranslation("shell");
  useLanguageSync();
  const [tab, setTab] = useState<TabId>("recipes");
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});

  const onKey = (e: React.KeyboardEvent, i: number) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    const next = TABS[(i + step + TABS.length) % TABS.length];
    if (next) {
      setTab(next.id);
      buttons.current[next.id]?.focus();
    }
  };

  return (
    <div data-build={BUILD_MARKER}>
      <a href="#main" className={styles.skip}>
        {shell.t("skip")}
      </a>
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <span className={styles.brand}>
            <Mountain aria-hidden="true" size={22} />
            <span>PitStudio</span>
          </span>
          <div className={styles.tools}>
            <LanguageSelect />
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main id="main" className={styles.main} tabIndex={-1}>
        <h1>{t("title")}</h1>
        <p className="muted">{t("intro")}</p>
        <div role="tablist" aria-label={t("tabs.label")} className="tabs">
          {TABS.map(({ id }, i) => (
            <button
              key={id}
              ref={(el) => {
                buttons.current[id] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              tabIndex={tab === id ? 0 : -1}
              onClick={() => setTab(id)}
              onKeyDown={(e) => onKey(e, i)}
            >
              {t(`tabs.${id}`)}
            </button>
          ))}
        </div>
        {TABS.map(({ id, Panel }) => (
          <div key={id} role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} hidden={tab !== id}>
            {tab === id && <Panel />}
          </div>
        ))}
      </main>
    </div>
  );
}
